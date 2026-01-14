# ContextMind 架构设计文档

## 版本 2.0.0 - 纯上下文优化模块

### 概述

ContextMind 2.0 已重构为纯粹的上下文优化模块，实现了职责分离：
- **上下文层（ContextMind）**：专注于会话管理和记忆检索
- **应用层（Applications）**：负责业务逻辑、Prompt构建和LLM调用

---

## 核心架构

### 层次结构

```
┌─────────────────────────────────────────┐
│         应用层 (Application Layer)        │
│  - 业务逻辑 (user_profile, rules)        │
│  - Prompt 构建                           │
│  - LLM 调用                              │
│  - 响应后处理                            │
└──────────────┬──────────────────────────┘
               │ optimize() / update()
┌──────────────┴──────────────────────────┐
│      上下文优化层 (Context Layer)        │
│  - 会话管理 (Session)                    │
│  - 记忆检索 (Memory)                     │
│  - 上下文整合                            │
└─────────────────────────────────────────┘
```

---

## 核心组件

### 1. 数据模型 (`contextmind/data_models.py`)

#### Message
表示对话中的单条消息：
```python
@dataclass
class Message:
    role: str  # 'user' | 'assistant' | 'system'
    content: str
    timestamp: datetime
    metadata: Dict[str, Any]
```

#### Memory
表示长期记忆条目：
```python
@dataclass
class Memory:
    content: str
    source: str  # 'seed' | 'extracted' | 'summary'
    timestamp: datetime
    score: float  # 相关性分数
    metadata: Dict[str, Any]
```

#### ContextResult
上下文优化结果：
```python
@dataclass
class ContextResult:
    recent_history: List[Message]  # 最近对话历史
    long_term_memory: List[Memory]  # 相关长期记忆
    metadata: Dict[str, Any]  # 元数据（统计信息等）
```

---

### 2. 上下文引擎 (`contextmind/engine.py`)

#### 核心 API

**optimize()** - 优化上下文
```python
async def optimize(self, user_input: str, **kwargs) -> ContextResult:
    """
    根据用户输入，检索相关的对话历史和长期记忆。
    
    Args:
        user_input: 用户输入
        **kwargs: 额外参数（预留扩展）
    
    Returns:
        ContextResult: 包含优化后的上下文信息
    """
```

**update()** - 更新上下文状态
```python
async def update(
    self,
    user_input: str,
    assistant_response: str,
    metadata: Optional[dict] = None
) -> None:
    """
    将对话添加到会话历史，提取知识并持久化到长期记忆。
    
    Args:
        user_input: 用户输入
        assistant_response: 助手回复
        metadata: 额外元数据
    """
```

#### 关键特性

- ✅ **会话管理**：管理短期对话历史
- ✅ **记忆检索**：智能检索相关长期记忆
- ✅ **知识提取**：从对话中提取并存储知识
- ❌ **不包含**：业务逻辑、Prompt构建、LLM调用

---

### 3. 应用层基类 (`examples/applications/base.py`)

#### BaseApplication

定义标准的对话处理流程：

```python
class BaseApplication(ABC):
    async def process_turn(self, user_input: str) -> str:
        """处理一轮对话 - 标准流程"""
        # 1. 使用 ContextMind 优化上下文
        context_result = await self.context_engine.optimize(user_input)
        
        # 2. 应用层构建 Prompt
        prompt = self.build_prompt(user_input, context_result)
        
        # 3. 调用 LLM
        _, response = self.llm_client.generate(prompt)
        
        # 4. 后处理响应
        response = self.post_process_response(response)
        
        # 5. 更新上下文
        await self.context_engine.update(user_input, response)
        
        return response
    
    @abstractmethod
    def build_prompt(
        self,
        user_input: str,
        context: ContextResult
    ) -> str:
        """构建最终 Prompt - 由子类实现具体业务逻辑"""
        pass
```

---

### 4. 客服应用示例 (`examples/applications/callcenter.py`)

#### CallCenterApp

展示如何在应用层管理业务逻辑：

```python
class CallCenterApp(BaseApplication):
    def __init__(
        self,
        context_engine,
        llm_client,
        user_profile: Optional[Dict] = None,
        business_rules: Optional[Dict] = None,
        **config
    ):
        # 业务信息由应用层管理
        self.user_profile = user_profile or {}
        self.business_rules = business_rules or {}
    
    def build_prompt(
        self,
        user_input: str,
        context: ContextResult
    ) -> str:
        """构建客服专用的 Prompt"""
        parts = []
        
        # 1. 系统角色
        parts.append(f"# 系统角色\n{self.system_prompt}")
        
        # 2. 用户画像
        if self.user_profile:
            profile_lines = [f"- {k}: {v}" for k, v in self.user_profile.items()]
            parts.append(f"\n# 用户画像\n" + "\n".join(profile_lines))
        
        # 3. 业务规则
        if self.business_rules:
            rules_lines = [f"- {k}: {v}" for k, v in self.business_rules.items()]
            parts.append(f"\n# 业务规则\n" + "\n".join(rules_lines))
        
        # 4. 长期记忆（来自 ContextMind）
        if context.long_term_memory:
            memory_lines = [
                f"- {mem.content} (相关性: {mem.score:.2f})"
                for mem in context.long_term_memory
            ]
            parts.append(f"\n# ⚠️ 重要记忆（必读）\n" + "\n".join(memory_lines))
        
        # 5. 对话历史（来自 ContextMind）
        if context.recent_history:
            history_lines = [
                f"{msg.role}: {msg.content}"
                for msg in context.recent_history
            ]
            parts.append(f"\n# 对话历史\n" + "\n".join(history_lines))
        
        # 6. 当前用户输入
        parts.append(f"\n# 当前用户输入\n{user_input}")
        
        return "\n".join(parts)
```

---

## 使用示例

### 基础用法

```python
from contextmind import ContextEngine
from contextmind.client import Client
from examples.applications import CallCenterApp
from google.adk.memory import InMemoryMemoryService

# 1. 创建上下文引擎
engine = ContextEngine(
    app_name="my-app",
    user_id="user-123",
    max_recent_events=6,
    memory_service=InMemoryMemoryService(),
)

# 2. 创建应用层
app = CallCenterApp(
    context_engine=engine,
    llm_client=Client(),
    user_profile={"姓名": "张三", "年龄": "30"},
    business_rules={"合规要求": "必须礼貌"},
)

# 3. 处理对话
response = await app.process_turn("你好")
print(response)
```

### 种子记忆

```python
# 添加预设知识到长期记忆
await engine.seed_memory([
    "用户多次要求停止推销并威胁报警。",
    "用户对重复来电极度反感，情绪长期处于愤怒状态。",
])
```

---

## 迁移指南

### 从 1.x 到 2.0

#### 主要变化

1. **ContextEngine 不再接受业务参数**
   ```python
   # ❌ 旧版
   engine = ContextEngine(
       llm_client=client,
       base_system_prompt="...",
       user_profile={...},
       business_rules={...},
   )
   
   # ✅ 新版
   engine = ContextEngine(
       app_name="my-app",
       user_id="user-123",
       max_recent_events=6,
   )
   
   app = CallCenterApp(
       context_engine=engine,
       llm_client=client,
       user_profile={...},
       business_rules={...},
   )
   ```

2. **process_turn() 移到应用层**
   ```python
   # ❌ 旧版
   result = await engine.process_turn(user_input)
   print(result.response)
   
   # ✅ 新版
   response = await app.process_turn(user_input)
   print(response)
   ```

3. **使用新的 optimize() 和 update() API**
   ```python
   # ✅ 新版 - 直接使用引擎
   context_result = await engine.optimize(user_input)
   # ... 应用层处理 ...
   await engine.update(user_input, response)
   ```

---

## 设计原则

### 1. 职责分离

- **上下文层**：只负责上下文优化（会话、记忆）
- **应用层**：负责业务逻辑、Prompt、LLM调用

### 2. 可复用性

- ContextEngine 可嵌入任何对话系统
- 通过应用层适配不同业务场景

### 3. 可扩展性

- 数据模型清晰，便于扩展
- 应用层可以灵活定制

---

## 常见问题

### Q: 为什么要分离应用层？

**A:** 提高代码可复用性和可维护性。ContextMind 专注于上下文优化，业务逻辑由应用层管理，两者可以独立演化。

### Q: 如何实现自定义应用？

**A:** 继承 `BaseApplication` 并实现 `build_prompt()` 方法：

```python
class MyApp(BaseApplication):
    def build_prompt(self, user_input: str, context: ContextResult) -> str:
        # 自定义 Prompt 构建逻辑
        return f"User: {user_input}\nHistory: {context.recent_history}"
```

### Q: 如何访问原始引擎方法？

**A:** 通过 `app.context_engine` 访问：

```python
session = await app.context_engine.get_current_session()
await app.context_engine.seed_memory([...])
```

---

## 参考资料

- [数据模型文档](./data_models.md)
- [应用层开发指南](./application_development.md)
- [示例代码](../examples/)
