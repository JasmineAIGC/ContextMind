# ADK Agent 集成 - 记忆库和槽位处理完整指南

## 概述

本文档详细说明了 ContextMind v0.4.1 中基于 google-adk 的 Agent 实现，以及记忆库和槽位处理的集成方案。

**版本**: v0.4.1  
**更新日期**: 2026-02-03

---

## 架构设计

### 整体架构

```
ContextMind v0.4.1 (完全基于 google-adk)

┌─────────────────────────────────────────────────────────────┐
│                        应用层                                │
│  gradio_demo, interactive_demo, apps/*                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────────┐
│                      模式层                                  │
├────────────────────────────┬────────────────────────────────┤
│    DST 模式                │    Evolution 模式               │
│  ┌──────────────────┐     │  ┌─────────────────────────┐   │
│  │  DSTAgent        │     │  │  EvolutionAgent         │   │
│  │  (ADK Agent)     │     │  │  (ADK Agent)            │   │
│  └────────┬─────────┘     │  └──────────┬──────────────┘   │
│           │               │             │                   │
│  ┌────────┴─────────┐     │  ┌──────────┴──────────────┐   │
│  │ DialogueState    │     │  │  EvolutionEngine       │   │
│  │ Tracker          │     │  │  - SessionManager      │   │
│  │ - 槽位提取 [自研]│     │  │  - MemoryBank         │   │
│  │ - Prompt工程     │     │  │  - Pipeline [自研]     │   │
│  │ - 状态追踪       │     │  │  - Evolution [自研]    │   │
│  └──────────────────┘     │  └────────────────────────┘   │
└────────────────────────────┴────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────────┐
│                    ADK 框架层                                │
│              google.adk.agents.Agent                        │
│              google.adk.models.openai.OpenAI                │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────────┐
│                   LLM API 层                                 │
│              Qwen API (OpenAI 兼容接口)                     │
└─────────────────────────────────────────────────────────────┘
```

### 关键设计原则

1. **ADK 负责**: Agent 框架、LLM 调用、模型管理
2. **本地实现**: SessionManager、MemoryBank（更符合需求）
3. **自研算法**: DST 槽位提取、Evolution Pipeline、记忆进化

---

## 核心组件详解

### 1. DSTAgent - DST 模式的 Agent

**文件**: `dst/adk_agent.py`

**基于**: `google.adk.agents.Agent`

**核心代码**:
```python
from google.adk import agents
from utils.adk_config import create_qwen_model

class DSTAgent:
    def __init__(self, config=None):
        self.config = config or QwenADKConfig.from_env()
        
        # 创建 ADK 的 OpenAI 模型（指向 Qwen API）
        self.model = create_qwen_model(self.config)
        
        # 创建 ADK Agent
        self.agent = agents.Agent(
            model=self.model,
            name="dst_agent",
            instruction="You are a dialog state tracking assistant..."
        )
    
    async def chat_async(self, messages: List[Dict], **kwargs) -> str:
        """调用 ADK Agent"""
        prompt = self._build_prompt(messages)
        result = await self.agent.run_async(prompt)
        return str(result.content if hasattr(result, 'content') else result)
```

**使用场景**:
- DialogueStateTracker 调用 `chat_async(messages)` 进行槽位提取
- 支持同步和异步两种调用方式

### 2. EvolutionAgent - Evolution 模式的 Agent

**文件**: `evolution/agent.py`

**基于**: `google.adk.agents.Agent`

**核心代码**:
```python
from google.adk import agents
from utils.adk_config import create_qwen_model

class EvolutionAgent:
    def __init__(self, config=None):
        self.config = config or QwenADKConfig.from_env()
        
        # 创建 ADK 的 OpenAI 模型（指向 Qwen API）
        self.model = create_qwen_model(self.config)
        
        # 创建 ADK Agent
        self.agent = agents.Agent(
            model=self.model,
            name="evolution_agent",
            instruction="You are an AI assistant with evolutionary memory..."
        )
    
    async def chat_async(self, messages: List[Dict], **kwargs) -> str:
        """聊天接口"""
        prompt = self._build_prompt(messages)
        result = await self.agent.run_async(prompt)
        return str(result.content if hasattr(result, 'content') else result)
    
    async def generate_async(self, prompt: str, **kwargs) -> tuple:
        """生成接口 - 返回元组以保持兼容性"""
        response = await self.chat_async([{"role": "user", "content": prompt}])
        return (None, response)  # reasoning 为 None
```

**使用场景**:
- Apps 调用 `generate_async(prompt)` 生成对话回复
- Pipeline 组件调用 `generate_async(prompt)` 生成摘要

**为什么返回元组**:
- Apps 期望 `(reasoning, response)` 格式
- ADK 不提供推理过程，所以 reasoning 为 None
- 保持向后兼容性

### 3. DialogueStateTracker - 槽位提取

**文件**: `dst/dialogue_state_tracker.py`

**核心职责**: DST 模式的所有自研逻辑

**自研部分** ✅:
1. **槽位提取算法**
   - 动态槽位识别
   - 槽位值归一化
   - 分类槽位验证

2. **Prompt 工程**
   - PromptManager 构建槽位提取 prompt
   - 支持自定义模板
   - 历史对话管理

3. **状态追踪**
   - 累积状态更新
   - 意图追踪
   - 历史摘要

4. **响应解析**
   - 多策略解析（JSON、正则、LLM）
   - 槽位过滤和验证

**ADK 集成点**:
```python
# 调用 LLM（通过 ADK Agent）
raw_response = await self.llm_client.chat_async(
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ],
    temperature=0.1
)

# 自研的响应解析
state_update = self.response_parser.parse(raw_response)
```

**数据流**:
```
用户输入 + 系统回复
    ↓
PromptManager.build_prompt() [自研]
    ↓
DSTAgent.chat_async() [ADK]
    ↓
ResponseParser.parse() [自研]
    ↓
状态更新 [自研]
```

### 4. SessionManager - 会话管理

**文件**: `evolution/memory/session.py`

**实现方式**: 本地实现（不使用 google-adk.memory）

**为什么不使用 ADK memory**:
1. `google-adk.memory` 主要用于**语义搜索**，不是会话历史管理
2. SessionManager 需要**简单的消息列表**存储和检索
3. 当前实现**更符合需求**且**更简洁**

**核心功能**:
```python
class SessionManager:
    def __init__(self, app_name: str, user_id: str, ...):
        self.app_name = app_name
        self.user_id = user_id
        self._session_id = str(uuid.uuid4())
        self._messages: List[Message] = []  # 本地缓存
    
    async def add_message(self, role: MessageRole, content: str):
        """添加消息到会话"""
        message = Message(
            role=role,
            content=content,
            timestamp=datetime.now(),
            metadata={}
        )
        self._messages.append(message)
    
    async def get_recent_history(self, limit: Optional[int] = None) -> List[Message]:
        """获取最近的对话历史"""
        if limit:
            return self._messages[-limit:]
        return self._messages
```

**使用场景**:
- EvolutionEngine 调用 `add_message()` 添加对话
- EvolutionEngine 调用 `get_recent_history()` 获取历史
- 用于构建 context 和 prompt

### 5. MemoryBank - 记忆库

**文件**: `evolution/memory/bank.py`

**实现方式**: 本地实现（不使用 google-adk.memory）

**为什么不使用 ADK memory**:
1. 需要**自定义的记忆结构**（适应度、演化等）
2. 集成**自研的记忆进化算法**
3. 更**灵活的存储和检索策略**

**核心功能**:
```python
class MemoryBank:
    def __init__(self, app_name: str, user_id: str, ...):
        self.memory_cache: List[Memory] = []
        self.embedding_model = None  # 可选的嵌入模型
    
    async def add_memory(self, memory: Memory):
        """添加记忆"""
        self.memory_cache.append(memory)
    
    async def search_memory(self, query: str, top_k: int = 5) -> List[Memory]:
        """搜索相关记忆"""
        # 使用嵌入模型或关键词匹配
        ...
    
    def get_memory_cache(self) -> List[Memory]:
        """获取所有缓存的记忆"""
        return self.memory_cache
```

**自研的记忆进化系统** ✅:
1. **记忆适应度计算** (`memory_fitness.py`)
   - 基于相关性、新鲜度、重要性等计算适应度
   
2. **进化更新器** (`evolutionary_updater.py`)
   - 记忆选择和淘汰
   - 记忆合并和更新
   
3. **反馈系统** (`feedback_system.py`)
   - 根据对话效果调整记忆权重

### 6. Apps - 应用层

**文件**: `apps/chat_app.py`, `apps/callcenter_app.py`, `apps/insurance_app.py`

**修复前的问题**:
```python
# ❌ 错误：llm_client 设置为 None
self.llm_client = None  # LLM client passed via context_engine
```

**修复后**:
```python
# ✅ 正确：从 context_engine 获取
self.llm_client = context_engine.llm_client

# 验证
if self.llm_client:
    logger.info("[App] ✓ LLM 客户端初始化成功")
else:
    logger.warning("[App] ⚠ LLM 客户端为 None，使用模拟回复")
    self.use_real_llm = False
```

**使用流程**:
```python
# 1. 优化上下文
context_result = await self.context_engine.optimize(user_input)

# 2. 构建 Prompt
prompt = await self.build_prompt(user_input, context_result)

# 3. 调用 LLM（现在使用真实的 ADK Agent）
reasoning, response = await self.llm_client.generate_async(prompt)

# 4. 更新上下文
await self.context_engine.update(user_input, response)

# 5. 提取知识
await self.context_engine.extract_knowledge(auto_store=True)
```

---

## 配置管理

### ADK 配置模块

**文件**: `utils/adk_config.py`

**核心代码**:
```python
from google.adk.models.openai import OpenAI
from dataclasses import dataclass
import os

@dataclass
class QwenADKConfig:
    """Qwen API 配置（ADK OpenAI 兼容）"""
    api_key: str
    base_url: str
    model: str = "Qwen2.5-7B-Instruct"
    max_tokens: int = 8192
    temperature: float = 0.7
    
    @classmethod
    def from_env(cls):
        """从环境变量加载配置"""
        return cls(
            api_key=os.getenv("QWEN3_API_KEY", ""),
            base_url=os.getenv("QWEN3_BASE_URL", ""),
            model=os.getenv("QWEN3_MODEL", "Qwen2.5-7B-Instruct"),
            max_tokens=int(os.getenv("QWEN3_MAX_TOKENS", "8192")),
            temperature=float(os.getenv("QWEN3_TEMPERATURE", "0.7")),
        )

def create_qwen_model(config: QwenADKConfig = None):
    """创建配置为 Qwen API 的 ADK OpenAI 模型"""
    config = config or QwenADKConfig.from_env()
    
    return OpenAI(
        model=config.model,
        api_key=config.api_key,
        base_url=config.base_url,  # 关键：指向 Qwen API
        temperature=config.temperature,
        max_tokens=config.max_tokens
    )
```

**关键点**:
- Qwen API 是 OpenAI 兼容接口
- 通过 `base_url` 指向 Qwen API 端点
- google-adk 的 OpenAI 模型可以无缝调用 Qwen

### 环境变量

**.env 文件**:
```ini
# ==========================================
# Qwen3 API 配置
# ==========================================
QWEN3_API_KEY=sk-your-api-key
QWEN3_BASE_URL=http://10.112.172.30:18023/v1
QWEN3_MODEL=Qwen2.5-7B-Instruct
QWEN3_MAX_TOKENS=8192
QWEN3_TEMPERATURE=0.7

# ==========================================
# Embedding 配置（用于记忆检索）
# ==========================================
EMBEDDING_MODEL_PATH=/path/to/bge-large-zh-v1.5
EMBEDDING_MODEL=bge-large-zh-v1.5
```

---

## 完整数据流

### DST 模式数据流

```
┌─────────────────┐
│   用户输入      │
│   系统回复      │
└────────┬────────┘
         │
         ▼
┌──────────────────────────────────┐
│  DialogueStateTracker           │
│  .process_turn()                │
└────────┬─────────────────────────┘
         │
         ▼
┌──────────────────────────────────┐
│  PromptManager                   │
│  .build_prompt()        [自研]   │
│  - 构建槽位提取 prompt           │
│  - 包含历史对话                  │
│  - 包含槽位定义                  │
└────────┬─────────────────────────┘
         │
         ▼
┌──────────────────────────────────┐
│  DSTAgent                        │
│  .chat_async()          [ADK]    │
│  ↓                                │
│  google.adk.agents.Agent         │
│  ↓                                │
│  google.adk.models.openai.OpenAI │
│  ↓                                │
│  Qwen API                        │
└────────┬─────────────────────────┘
         │
         ▼
┌──────────────────────────────────┐
│  ResponseParser                  │
│  .parse()               [自研]   │
│  - JSON 解析                     │
│  - 正则提取                      │
│  - 槽位过滤                      │
│  - 值归一化                      │
└────────┬─────────────────────────┘
         │
         ▼
┌──────────────────────────────────┐
│  状态更新                         │
│  - 累积状态              [自研]   │
│  - 意图追踪                      │
│  - 历史摘要                      │
└──────────────────────────────────┘
```

### Evolution 模式数据流

```
┌─────────────────┐
│   用户输入      │
└────────┬────────┘
         │
         ▼
┌────────────────────────────────────────┐
│  App.process_turn()                   │
└────────┬───────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────┐
│  EvolutionEngine.optimize()   [自研]   │
│  ┌──────────────────────────────────┐  │
│  │  SessionManager                  │  │
│  │  .get_recent_history()  [本地]  │  │
│  └──────────────────────────────────┘  │
│  ┌──────────────────────────────────┐  │
│  │  MemoryBank                      │  │
│  │  .search_memory()       [本地]  │  │
│  └──────────────────────────────────┘  │
│  ┌──────────────────────────────────┐  │
│  │  Pipeline 组件          [自研]   │  │
│  │  - Preprocessor                  │  │
│  │  - Compressor                    │  │
│  │  - Reorderer                     │  │
│  └──────────────────────────────────┘  │
│  ↓                                      │
│  ContextResult                         │
└────────┬───────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────┐
│  App.build_prompt()          [自研]    │
│  - 系统提示词                          │
│  - 相关记忆                            │
│  - 对话历史/摘要                       │
│  - 当前输入                            │
└────────┬───────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────┐
│  EvolutionAgent.generate_async() [ADK] │
│  ↓                                      │
│  google.adk.agents.Agent               │
│  ↓                                      │
│  Qwen API                              │
└────────┬───────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────┐
│  EvolutionEngine.update()     [自研]   │
│  ┌──────────────────────────────────┐  │
│  │  SessionManager                  │  │
│  │  .add_message()         [本地]  │  │
│  └──────────────────────────────────┘  │
└────────┬───────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────┐
│  EvolutionEngine                       │
│  .extract_knowledge()        [自研]    │
│  ┌──────────────────────────────────┐  │
│  │  Knowledge Extractor             │  │
│  │  - 规则提取 / LLM 提取   [自研] │  │
│  └──────────────────────────────────┘  │
│  ┌──────────────────────────────────┐  │
│  │  MemoryBank                      │  │
│  │  .add_memory()          [本地]  │  │
│  └──────────────────────────────────┘  │
│  ┌──────────────────────────────────┐  │
│  │  Evolution System       [自研]   │  │
│  │  - Memory Fitness                │  │
│  │  - Evolutionary Updater          │  │
│  │  - Feedback System               │  │
│  └──────────────────────────────────┘  │
└────────────────────────────────────────┘
```

---

## 测试和验证

### 基本导入测试

```bash
# 测试 DST Agent
$ python3 -c "
from dst import DSTAgent
agent = DSTAgent()
print('✅ DSTAgent 初始化成功')
"

# 测试 Evolution Agent
$ python3 -c "
from evolution import EvolutionAgent
agent = EvolutionAgent()
print('✅ EvolutionAgent 初始化成功')
"

# 测试 Apps
$ python3 -c "
from evolution import EvolutionAgent, EvolutionEngine
from apps.chat_app import ChatApplication

agent = EvolutionAgent()
engine = EvolutionEngine(app_name='test', user_id='test', llm_client=agent)
app = ChatApplication(context_engine=engine)
print('✅ ChatApplication 初始化成功')
print(f'✅ App LLM 客户端: {app.llm_client is not None}')
"
```

### 功能测试

**DST 模式**:
```bash
$ python interactive_demo.py --scenario chat --mode dst

# 验证点：
# 1. DSTAgent 初始化成功
# 2. 槽位正确提取
# 3. 状态正确追踪
# 4. 历史正确管理
```

**Evolution 模式**:
```bash
$ python interactive_demo.py --scenario chat --mode evolution

# 验证点：
# 1. EvolutionAgent 初始化成功
# 2. App LLM 客户端不为 None
# 3. SessionManager 正常工作
# 4. MemoryBank 正常工作
# 5. 使用真实 LLM（不是模拟回复）
```

### Gradio UI 测试

```bash
$ python gradio_demo.py

# 在浏览器中访问 http://localhost:7860
# 
# 验证点：
# 1. 两种模式都能正常初始化
# 2. DST 模式：槽位提取正常
# 3. Evolution 模式：对话回复正常（真实 LLM）
# 4. 切换场景正常工作
```

---

## 常见问题

### Q1: 为什么不使用 google-adk.memory？

**A**: 
1. `google-adk.memory` 主要用于**语义搜索**，不是会话历史管理
2. SessionManager 需要**简单的消息列表**存储和检索
3. MemoryBank 需要集成**自研的记忆进化算法**
4. 当前实现**更符合需求**且**更简洁**

### Q2: generate_async() 为什么返回元组？

**A**:
1. Apps 期望 `(reasoning, response)` 格式
2. ADK 不提供推理过程，所以 reasoning 为 None
3. 保持向后兼容性，避免修改大量代码

### Q3: 如何验证 Apps 使用了真实 LLM？

**A**:
```python
# 检查日志
[ChatApplication] ✓ 初始化完成 (真实LLM: True, ...)

# 或在代码中检查
app = ChatApplication(context_engine=engine)
assert app.llm_client is not None
assert app.use_real_llm == True
```

### Q4: 槽位提取是如何工作的？

**A**:
1. PromptManager 构建槽位提取 prompt（自研）
2. DSTAgent 调用 ADK Agent 获取 LLM 响应
3. ResponseParser 解析响应提取槽位（自研）
4. 状态追踪器更新累积状态（自研）

---

## 总结

### 核心成就 ✅

1. **完全基于 google-adk**
   - DSTAgent 使用 `google.adk.agents.Agent`
   - EvolutionAgent 使用 `google.adk.agents.Agent`
   - 通过 OpenAI 兼容接口调用 Qwen

2. **保留所有自研算法**
   - DST: 槽位提取、Prompt 工程、状态追踪
   - Evolution: Pipeline 算法、记忆进化、适应度计算

3. **正确的架构分层**
   - ADK 层: Agent 框架、LLM 调用
   - 基础设施层: SessionManager、MemoryBank（本地实现）
   - 算法层: 所有自研的核心算法

4. **Apps 正确工作**
   - 从 context_engine 获取 LLM 客户端
   - 使用真实 LLM 而不是模拟回复
   - 接口兼容性良好

### 技术亮点 ⭐

1. **Qwen + ADK 集成**：通过 OpenAI 兼容接口，让 ADK 调用 Qwen
2. **务实的架构选择**：在合适的地方使用 ADK，在不合适的地方使用本地实现
3. **保持核心价值**：所有自研的上下文工程和记忆进化算法完全保留
4. **清晰的职责划分**：ADK、基础设施、算法三层分明

---

**版本**: v0.4.1  
**状态**: ✅ 完全集成完成  
**维护者**: ContextMind Team  
**最后更新**: 2026-02-03
