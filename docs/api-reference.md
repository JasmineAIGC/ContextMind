# API 参考文档

本文档提供 ContextMind 主要 API 的详细说明。

## 核心导入

```python
# 推荐方式：通过主包统一导入
from contextmind import (
    ContextPipeline,         # 统一上下文工程流水线（推荐入口）
    KnowledgeBaseBuilder,    # 知识库构建（Phase 1）
    AdkLLMClient,            # LLM 客户端
    # 追踪器
    DialogueStateTracker,
    FnCTODTracker,
    AdkPyTODTracker,
    EvolveEngine,
    create_app_for_scenario,
    # Schema 数据模型
    ServiceSchema,
    load_schema_from_dict,
)

# 底层导入（高级用法）
from contextmind.modes.base import BaseTracker
from contextmind.scenarios.registry import scenario_registry
from contextmind.infra.logger import get_logger
```

---

## ContextPipeline（统一流水线，推荐入口）

### ContextPipeline

`contextmind.pipeline.ContextPipeline` 是框架推荐的统一入口，将知识库构建（Phase 1）和对话上下文提取（Phase 2）整合为一个简洁 API。

```python
from contextmind import ContextPipeline, AdkLLMClient

pipeline = ContextPipeline(
    llm_client=AdkLLMClient(),
    mode="pytod",       # 执行模式：pytod（默认）、fnctod、dst、evolve
    scene_name="银行贷款外呼",
)
```

#### 初始化参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `llm_client` | `AdkLLMClient` | LLM 客户端 |
| `mode` | `str` | 执行模式，默认 `"pytod"` |
| `scene_name` | `str` | 场景名称 |
| `scene_description` | `str` | 场景描述（可选） |

#### 主要方法

| 方法 | 说明 |
|------|------|
| `build_kb(dialogues, scene_name, ...)` | Phase 1：从原始对话构建知识库 |
| `load_kb(path)` | 从已保存的 `schema.json` 加载知识库 |
| `set_schema(schema_dict)` | 直接从 schema 字典加载（Phase 1→2 直通） |
| `register_api(name)(fn)` | 注册 API 函数（PyTOD 模式，装饰器用法） |
| `async process_turn(user_utterance, ...)` | 处理单轮对话，返回上下文 |
| `reset()` | 重置对话状态，开始新会话 |

#### 示例

```python
import asyncio
from contextmind import ContextPipeline, AdkLLMClient

pipeline = ContextPipeline(llm_client=AdkLLMClient())

# Phase 1: 构建知识库
pipeline.build_kb(
    dialogues=my_dialogues,
    scene_name="银行贷款外呼",
    scene_description="银行客服主动致电老客户推介个人贷款产品",
)

# 注册业务 API（PyTOD 模式）
@pipeline.register_api("query_loan_info")
def query_loan_info(customer_name: str) -> dict:
    return {"credit_limit": 50000, "interest_rate": 0.12}

# Phase 2: 处理对话
async def main():
    result = await pipeline.process_turn("我是李明，想查询贷款额度")
    print(result["response"])           # 系统回复
    print(result["context"])            # 本轮提取的上下文
    print(result["cumulative_context"]) # 累积的全量上下文

asyncio.run(main())
```

---

## 知识库构建 API（Phase 1）

### KnowledgeBaseBuilder

`contextmind.knowledge.KnowledgeBaseBuilder` 接受任意格式的对话数据，经过两阶段 LLM 处理，生成标准 SGD `schema.json`。

```python
from contextmind.knowledge import KnowledgeBaseBuilder

builder = KnowledgeBaseBuilder(
    scene_name="银行贷款外呼",
    scene_description="银行客服主动致电老客户推介个人贷款产品",
)
```

#### 主要方法

| 方法 | 说明 |
|------|------|
| `build(dialogues) -> dict` | 从对话数据构建 schema 字典（Phase 1：发现+合成） |
| `save(schema_dict, path)` | 保存 schema.json 及对话文件 |
| `build_dataset(dialogues)` | 构建完整 SGD 数据集（schema + 标注对话） |
| `save_dataset(output_dir)` | 保存数据集到指定目录 |
| `to_service_schema(schema_dict)` | 将 schema 字典转换为 `ServiceSchema`（Phase 1→2 桥接） |
| `load_schema(path)` | 从 `schema.json` 加载 `ServiceSchema` |
| `build_async(dialogues)` | 异步版 `build()` |
| `build_dataset_async(dialogues)` | 异步版 `build_dataset()` |

#### 支持的对话输入格式

- **chat_test 格式**：`{"对话历史": [{"机器人": "...", "用户": "..."}]}`
- **SGD 格式**：`{"turns": [{"speaker": "USER", "utterance": "..."}]}`
- **文本列表**：`["agent: 你好", "user: 你好"]`
- **平铺文本**：`"机器人：你好\n用户：你好"`
- **嵌套格式**：`{"label": "...", "query": {"对话历史": [...]}}`（chat_test_500.json）

---

---

## 共享接口：BaseTracker 协议

### BaseTracker

`contextmind.modes.base.BaseTracker` 是一个 [结构子类型](https://mypy.readthedocs.io/en/stable/protocols.html) Protocol，定义所有对话追踪器的公共接口。内置的 `DialogueStateTracker`、`FnCTODTracker`、`AdkPyTODTracker` 均满足此协议。

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
from contextmind.infra.llm_client import AdkLLMClient

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

**get_current_state() -> Dict[str, Any]**

获取当前对话状态。

```python
current_state = tracker.get_current_state()
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
from contextmind.infra.llm_client import AdkLLMClient

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
from contextmind.infra.llm_client import AdkLLMClient

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

### AdkLLMClient

基于 Google ADK（LiteLLM）的无状态 LLM 客户端，支持所有 OpenAI 兼容端点（Qwen、本地 vLLM、OpenAI 等）。配置通过 `.env` 文件或环境变量自动读取。

```python
from contextmind.infra.llm_client import AdkLLMClient, LLMConfig

# 方式1：从 .env 自动加载配置（推荐）
client = AdkLLMClient()

# 方式2：显式传入配置
client = AdkLLMClient(
    config=LLMConfig(
        api_key="your_key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen-plus",
    )
)

# 异步调用（主要接口）
response = await client.chat_async(messages=[
    {"role": "system", "content": "你是智能助手"},
    {"role": "user", "content": "你好"},
])
```

#### LLMConfig 环境变量

| 环境变量 | 说明 |
|----------|------|
| `QWEN3_API_KEY` / `LLM_API_KEY` | API 密钥（按优先级读取） |
| `QWEN3_BASE_URL` / `LLM_BASE_URL` | API 基础 URL |
| `QWEN3_MODEL` / `LLM_MODEL` | 模型名称 |
| `LLM_TEMPERATURE` | 温度（默认 0.3） |
| `LLM_MAX_TOKENS` | 最大 token 数（默认 4096） |

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
from contextmind.scenarios.registry import scenario_registry

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
- [示例代码](quick-start.md)
