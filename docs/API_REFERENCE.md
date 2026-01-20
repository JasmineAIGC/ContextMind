# ContextMind v6.0 API Reference

## 核心类

### ContextEngine

上下文引擎核心入口。

#### 初始化

```python
from contextmind.core import ContextEngine
from google.adk.memory import InMemoryMemoryService
from google.adk.sessions import InMemorySessionService

engine = ContextEngine(
    app_name="my-app",
    user_id="user-123",
    llm_client=client,
    session_service=InMemorySessionService(),
    memory_service=InMemoryMemoryService(),
    max_recent_events=10,
)
```

#### 方法

##### `optimize()`

优化上下文。

```python
context_result = await engine.optimize(
    user_input="你好",
    include_session=True,
    include_memory=True,
    include_knowledge=False,
    max_context_length=None,
)
```

##### `update()`

更新上下文。

```python
await engine.update(
    user_input="你好",
    assistant_response="你好，有什么可以帮助你的？"
)
```

##### `extract_knowledge()`

提取知识。

```python
knowledge_list = await engine.extract_knowledge(
    auto_store=True
)
```

##### `seed_memory()`

植入记忆种子。

```python
await engine.seed_memory([
    "产品名称：智能助手",
    "服务时间：7x24小时",
])
```

##### `clear_session()`

清空会话。

```python
await engine.clear_session()
```

---

## 数据模型

### Message

对话消息。

```python
from contextmind.core import Message, MessageRole
from datetime import datetime

msg = Message(
    role=MessageRole.USER,
    content="你好",
    timestamp=datetime.now(),
    metadata={}
)
```

### ContextItem

上下文条目。

```python
from contextmind import ContextItem, ContextSource

item = ContextItem(
    content="用户偏好：喜欢简洁的回答",
    source=ContextSource.MEMORY,
    score=0.9,
    timestamp=datetime.now(),
    metadata={}
)
```

### ContextResult

上下文优化结果。

```python
# 从 engine.optimize() 返回
context_result: ContextResult = await engine.optimize("你好")

# 访问数据
context_result.recent_history       # List[Message]
context_result.long_term_memory     # List[ContextItem]
context_result.external_knowledge   # List[ContextItem]
context_result.metadata             # Dict[str, Any]

# 辅助方法
all_items = context_result.get_all_items()          # 获取所有上下文项
text = context_result.get_all_context_text()        # 获取格式化文本
dict_data = context_result.to_dict()                # 转换为字典
```

### Knowledge

提取的知识。

```python
from contextmind import Knowledge, KnowledgeType

knowledge = Knowledge(
    content="用户喜欢简洁的回答",
    type=KnowledgeType.PREFERENCE,
    confidence=0.8,
    timestamp=datetime.now(),
    metadata={}
)
```

---

## 应用层

### BaseApplication

应用基类，定义了标准的对话处理模式。

```python
from examples.applications import BaseApplication
from contextmind import ContextEngine, Client, ContextResult

class MyApp(BaseApplication):
    def build_prompt(self, user_input: str, context: ContextResult) -> str:
        # 实现Prompt构建逻辑
        parts = [self.system_prompt]
        
        # 添加上下文
        if context.recent_history:
            parts.append("## 对话历史")
            for msg in context.recent_history:
                parts.append(f"{msg.role.value}: {msg.content}")
        
        # 添加当前输入
        parts.append(f"用户: {user_input}")
        
        return "\n".join(parts)

# 使用
app = MyApp(
    context_engine=engine,
    llm_client=client,
    system_prompt="你是一个助手",
)

response = await app.process_turn("你好")
```

---

## 策略

### RetrievalStrategy

检索策略基类。

```python
from contextmind.strategies import RetrievalStrategy
from contextmind import ContextItem

class MyRetrievalStrategy(RetrievalStrategy):
    async def retrieve(self, query: str, limit: int = 5, **kwargs):
        # 实现检索逻辑
        items = []
        # ... 检索逻辑 ...
        return items
```

### IntegrationStrategy

整合策略基类。

```python
from contextmind.strategies import IntegrationStrategy
from contextmind import ProcessedContext

class MyIntegrationStrategy(IntegrationStrategy):
    async def integrate(self, context: ProcessedContext):
        # 实现整合逻辑
        # ... 去重、排序等 ...
        return context
```

### OptimizationStrategy

优化策略基类。

```python
from contextmind.strategies import OptimizationStrategy

class MyOptimizationStrategy(OptimizationStrategy):
    async def optimize(self, context: ProcessedContext):
        # 实现优化逻辑
        # ... 压缩、截断等 ...
        return context
```

### ExtractionStrategy

提取策略基类。

```python
from contextmind.strategies import ExtractionStrategy
from contextmind import Message, Knowledge

class MyExtractionStrategy(ExtractionStrategy):
    async def extract(self, messages: List[Message]):
        # 实现提取逻辑
        knowledge = []
        # ... 提取逻辑 ...
        return knowledge
```

---

## 客户端

### Client

LLM客户端，支持OpenAI兼容的API。

```python
from contextmind import Client, ClientConfig

# 从环境变量加载
client = Client(config=ClientConfig.from_env())

# 手动配置
config = ClientConfig(
    api_key="your-api-key",
    model="Qwen3-32B",
    base_url="https://api.example.com",
    temperature=0.6,
    max_tokens=8192,
)
client = Client(config=config)

# 使用
reasoning, response = client.generate("你好")
```

---

## 日志

### setup_logging

配置日志系统。

```python
from contextmind import setup_logging, INFO, DEBUG

setup_logging(
    level=INFO,                # 日志级别
    log_file="app.log",        # 日志文件（可选）
    log_to_console=True,       # 是否输出到控制台
    auto_create_file=True,     # 是否自动创建日志文件
)
```

### get_logger

获取logger实例。

```python
from contextmind import get_logger

logger = get_logger(__name__)
logger.info("这是一条日志")
```

---

## 完整示例

```python
import asyncio
from contextmind import (
    ContextEngine,
    Client,
    ClientConfig,
    setup_logging,
    INFO,
)
from google.adk.memory import InMemoryMemoryService
from google.adk.sessions import InMemorySessionService
from examples.applications.callcenter import CallCenterApplication

async def main():
    # 设置日志
    setup_logging(level=INFO)
    
    # 初始化客户端
    client = Client(config=ClientConfig.from_env())
    
    # 初始化引擎
    engine = ContextEngine(
        app_name="my-app",
        user_id="user-123",
        llm_client=client,
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
    )
    
    # 植入知识
    await engine.seed_memory([
        "产品名称：智能助手",
        "服务时间：7x24小时",
    ])
    
    # 初始化应用
    app = CallCenterApplication(
        context_engine=engine,
        llm_client=client,
        business_info="产品介绍...",
    )
    
    # 对话
    response = await app.process_turn("你好")
    print(f"助手: {response}")

if __name__ == "__main__":
    asyncio.run(main())
```
