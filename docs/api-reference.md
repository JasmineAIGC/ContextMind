# API 参考文档

本文档提供 ContextMind 主要 API 的详细说明。

## 核心导入

```python
# 主包导入（推荐方式）
import contextmind

# 共享接口协议
from contextmind.modes.base import BaseTracker

# 追踪器导入
from contextmind.modes.dst import DialogueStateTracker
from contextmind.modes.fnctod import FnCTODTracker
from contextmind.modes.pytod import PyTODTracker
from contextmind.modes.evolve import EvolveEngine, create_app_for_scenario

# 场景导入
from contextmind.scenarios import (
    get_chat_scenario,
    get_callcenter_scenario,
    get_insurance_scenario
)

# 基础设施导入
from contextmind.infra.llm_client import SimpleLLMClient
from contextmind.infra.logger import get_logger
from contextmind.config.registry import scenario_registry
```

---

## 共享接口：BaseTracker 协议

### BaseTracker

`contextmind.modes.base.BaseTracker` 是一个 [结构子类型](https://mypy.readthedocs.io/en/stable/protocols.html) Protocol，定义所有对话追踪器的公共接口。内置的 `DialogueStateTracker`、`FnCTODTracker`、`PyTODTracker` 均满足此协议。

```python
from contextmind.modes.base import BaseTracker

# 以统一类型提示接收任意追踪器
async def run_conversation(tracker: BaseTracker, user_msg: str) -> None:
    result = await tracker.process_turn(user_msg)
    state = tracker.get_current_state()
    print(state)
```

#### 方法

| 方法 | 说明 |
|------|------|
| `from_scenario(llm_client, scenario_config, **kwargs)` | 工厂方法，从场景配置创建实例 |
| `async process_turn(user_utterance, **kwargs) -> Dict` | 处理单轮对话，返回本轮更新的状态 |
| `get_current_state() -> Dict` | 返回累积的完整对话状态 |
| `reset() -> None` | 清空历史和状态，开始新会话 |

#### 实现新追踪器

新增追踪模式时，实现这四个方法即可与 ContextMind 生态兼容，**无需继承**：

```python
class MyTracker:
    """自定义追踪器，结构上满足 BaseTracker 协议。"""

    @classmethod
    def from_scenario(cls, llm_client, scenario_config, **kwargs):
        return cls(llm_client=llm_client, ...)

    async def process_turn(self, user_utterance: str, **kwargs):
        # 调用 LLM，提取结构化信息
        return {"slot_a": "value"}

    def get_current_state(self):
        return self._state

    def reset(self):
        self._state = {}

# 运行时协议检查
from contextmind.modes.base import BaseTracker
assert isinstance(MyTracker(), BaseTracker)
```

---

## DST 模式 API

### DialogueStateTracker

对话状态追踪器，用于提取意图和槽位。

#### 初始化

```python
from contextmind.modes.dst import DialogueStateTracker
from contextmind.infra.llm_client import SimpleLLMClient

# 方式1: 使用工厂方法（推荐）
tracker = DialogueStateTracker.from_scenario(
    llm_client=llm_client,
    scenario_config=config
)

# 方式2: 直接初始化
from contextmind.modes.dst import PromptManager

prompt_manager = PromptManager(domain="restaurant")
tracker = DialogueStateTracker(
    llm_client=llm_client,
    prompt_manager=prompt_manager
)
```

#### 主要方法

**process_turn(user_utterance: str) -> Dict[str, Any]**

处理单轮对话。

- 参数:
  - `user_utterance`: 用户输入文本
- 返回: 包含提取状态的字典

```python
await tracker.process_turn("我想订一个明天的桌子")
```

**get_state() -> Dict[str, Any]**

获取当前对话状态。

```python
current_state = tracker.get_state()
```

**reset() -> None**

重置对话状态。

```python
tracker.reset()
```

---

## FnCTOD 模式 API

### FnCTODTracker

函数调用对话追踪器，兼容 OpenAI function calling 格式。

#### 初始化

```python
from contextmind.modes.fnctod import FnCTODTracker
from contextmind.infra.llm_client import SimpleLLMClient

# 使用工厂方法（推荐）
tracker = FnCTODTracker.from_scenario(
    llm_client=llm_client,
    scenario_config=config,
    use_two_stage=True  # 启用两阶段处理
)
```

#### 主要方法

**process_turn(user_utterance: str) -> Dict[str, Any]**

处理单轮对话，返回函数调用和自然语言响应。

- 参数:
  - `user_utterance`: 用户输入文本
- 返回: 包含 state, response, function_call 的字典

```python
result = await tracker.process_turn("我想了解保险")
print(result['function_call'])  # Function call 对象
print(result['response'])       # 自然语言回复
```

**reset() -> None**

重置对话状态。

```python
tracker.reset()
```

---

## Evolve 模式 API

### EvolveEngine

演化式上下文引擎，支持记忆和进化学习。

#### 初始化

```python
from contextmind.modes.evolve import EvolveEngine
from contextmind.infra.llm_client import SimpleLLMClient

engine = EvolveEngine(
    app_name="my_app",
    user_id="user123",
    llm_client=llm_client,
    system_prompt="你是一个友好的助手",
    enable_memory=True,      # 启用记忆系统
    enable_evolution=True,   # 启用进化学习
    memory_limit=50,         # 记忆库大小限制
    evolution_interval=10    # 进化学习间隔（轮数）
)
```

#### 主要方法

**process_turn(user_message: str, enable_plugins: bool = True) -> str**

处理单轮对话。

- 参数:
  - `user_message`: 用户消息
  - `enable_plugins`: 是否启用插件系统
- 返回: 助手回复

```python
response = await engine.process_turn("你好")
```

**reset_session() -> None**

重置当前会话。

```python
engine.reset_session()
```

### create_app_for_scenario

工厂函数，创建场景特定的应用实例。

```python
from contextmind.modes.evolve import create_app_for_scenario

app = create_app_for_scenario(
    scenario_name="chat",
    llm_client=llm_client,
    scenario_config=config,
    app_name_prefix="demo"
)
```

---

## 场景配置 API

### ScenarioConfig

场景配置数据类。

```python
from contextmind.scenarios.config import ScenarioConfig

config = ScenarioConfig(
    scenario_name="custom",
    system_prompt="系统提示词",
    dst_slots={
        "slot_name": "槽位描述"
    },
    enable_memory=True,
    enable_evolution=False
)
```

### 预定义场景

**get_chat_scenario() -> ScenarioConfig**

获取闲聊场景配置。

**get_callcenter_scenario() -> ScenarioConfig**

获取客服场景配置。

**get_insurance_scenario() -> ScenarioConfig**

获取保险场景配置。

---

## 基础设施 API

### SimpleLLMClient

简单的 LLM 客户端封装。

```python
from contextmind.infra.llm_client import SimpleLLMClient

client = SimpleLLMClient(
    api_key="your_key",
    base_url="https://api.openai.com/v1",
    model="gpt-3.5-turbo"
)

# 同步调用
response = client.chat(messages=[
    {"role": "user", "content": "你好"}
])

# 异步调用
response = await client.chat_async(messages=[
    {"role": "user", "content": "你好"}
])
```

### Logger

日志工具。

```python
from contextmind.infra.logger import get_logger

logger = get_logger(__name__)
logger.info("信息日志")
logger.warning("警告日志")
logger.error("错误日志")
```

### 场景注册表

```python
from contextmind.config.registry import scenario_registry

# 列出所有场景
scenarios = scenario_registry.list_scenarios()

# 获取应用类
app_class = scenario_registry.get_app_class("chat")

# 获取Schema
schema = scenario_registry.get_schema("chat")
```

---

## 数据模型

### DialogueTurn

对话轮次数据模型（DST/FnCTOD）。

```python
from contextmind.modes.dst.data_models import DialogueTurn

turn = DialogueTurn(
    user_utterance="用户输入",
    system_utterance="系统回复",
    state={"slot": "value"}
)
```

### FunctionCall

函数调用数据模型（FnCTOD）。

```python
from contextmind.modes.fnctod.data_models import FunctionCall

call = FunctionCall(
    function_name="get_weather",
    arguments={"location": "北京"}
)
```

### Message

消息数据模型（Evolve）。

```python
from contextmind.modes.evolve.core.data_models import Message

message = Message(
    role="user",
    content="消息内容",
    turn=1
)
```

---

## 错误处理

所有主要方法都可能抛出以下异常：

- `ValueError`: 参数错误
- `RuntimeError`: 运行时错误
- `Exception`: 其他未预期的错误

建议使用 try-except 处理：

```python
try:
    response = await tracker.process_turn(user_input)
except ValueError as e:
    logger.error(f"参数错误: {e}")
except Exception as e:
    logger.error(f"未知错误: {e}")
```

---

## 类型提示

ContextMind 使用 Python 类型提示。建议在您的代码中也使用：

```python
from typing import Dict, Any, Optional
from contextmind.modes.dst import DialogueStateTracker

async def process_dialogue(
    tracker: DialogueStateTracker,
    user_input: str
) -> Dict[str, Any]:
    return await tracker.process_turn(user_input)
```

---

## 更多信息

- [快速开始](quick-start.md)
- [配置指南](configuration.md)
- [示例代码](examples.md)
