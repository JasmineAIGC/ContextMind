# PyTOD 模式（可编程任务型对话）

## 概述

PyTOD（Programmable Task-Oriented Dialogue）将对话理解建模为**程序执行问题**。基于 Apple 研究院的同名论文，本模式通过三步流水线将用户意图转化为程序语句，并对接真实 API 获取结构化结果，最终生成自然语言回复。

---

## 三步流水线

```
用户输入
  ↓
① 动作解析器（Action Parser）
    → 生成程序语句 restaurants_1_find(city='San Jose')
  ↓
② 执行引擎（Execution Engine）
    → 安全解析并执行程序语句
    → 调用已注册的 API / 数据库
    → 返回结构化结果 [{"name": "海底捞", "rating": 4.8}]
  ↓
③ 对话管理器（Dialogue Manager）
    → 基于执行结果生成自然语言回复
  ↓
系统输出
```

---

## 文件说明

| 文件 | 类 / 对象 | 作用 |
|------|-----------|------|
| `tracker.py` | `PyTODTracker`, `PyTODTurnResult` | **主追踪器**：协调三步流水线，实现 `BaseTracker` 协议 |
| `prompts.py` | `PyTODPromptBuilder`, `ConversationTurn`, `FewShotExample` | **Prompt 构建器**：为动作解析器和对话管理器生成 prompt 消息列表 |
| `execution_engine.py` | `ExecutionEngine`, `ProgramStatement`, `ExecutionResult`, `ProgramBlock`, `ProgramExecutionResult` | **执行引擎**：安全解析程序语句并调用注册 API，返回执行结果 |
| `schemas.py` | `ServiceSchema`, `IntentDefinition`, `SlotDefinition`, `load_schema_from_dict` | **Schema 数据模型**：可选的服务/意图/槽位预定义结构，用于 schema 驱动模式 |
| `validator.py` | `ActionValidator`, `ValidationResult` | **动作校验器**：校验 LLM 生成的动作合法性，提供反馈用于重试 |
| `api_registry.py` | `SCENARIO_API_REGISTRY`, `get_scenario_key` | **API 注册表**：按场景注册 API 函数，供执行引擎调用 |
| `data_models.py` | _(各场景专用模型)_ | **数据模型**：各场景专属的输入/输出数据类 |
| `__init__.py` | — | 模块入口，导出所有公共接口 |

---

## 两种运行模式

### 1. Schema 驱动模式（生产环境推荐）

预先定义意图、槽位和枚举值，LLM 必须在 schema 约束下生成动作：

```python
from contextmind.modes.pytod import PyTODTracker, ServiceSchema, load_schema_from_dict

schema_dict = {
    "service_name": "hotel",
    "intents": [
        {"name": "hotel_search", "slots": [{"name": "city", "type": "string"}, ...]}
    ]
}
schema = load_schema_from_dict(schema_dict)
tracker = PyTODTracker(llm_client=llm_client, schema=schema)
```

`ActionValidator` 会根据 schema 约束：
- 意图必须在预定义列表中
- 枚举槽位值必须合法
- 生成违规时提供重试反馈

### 2. 开放域模式（快速原型）

不需要任何预定义，LLM 自由命名意图和槽位：

```python
tracker = PyTODTracker(llm_client=llm_client)  # schema=None（默认）
```

适用于：意图/槽位尚未确定的早期阶段，或完全开放的对话场景。

---

## 快速使用

```python
import asyncio
from contextmind.modes.pytod import PyTODTracker
from contextmind.infra.llm_client import SimpleLLMClient

async def demo():
    tracker = PyTODTracker(llm_client=SimpleLLMClient())
    result = await tracker.process_turn("查一下北京今天的天气")
    print(result)  # PyTODTurnResult 含 actions、execution results、response

asyncio.run(demo())
```

---

## 工厂方法

```python
# 推荐方式：从场景配置创建
from contextmind.modes.pytod import PyTODTracker
from contextmind.scenarios import get_callcenter_scenario
from contextmind.infra.llm_client import SimpleLLMClient

tracker = PyTODTracker.from_scenario(
    llm_client=SimpleLLMClient(),
    scenario_config=get_callcenter_scenario()
)
```

---

## Few-Shot 示例

`PyTODPromptBuilder` 支持通过 `FewShotExample` 注入 few-shot 示例：

```python
from contextmind.modes.pytod.prompts import PyTODPromptBuilder, FewShotExample, ConversationTurn

example = FewShotExample(
    conversation=[ConversationTurn(role="user", content="订一家北京的酒店")],
    program="hotel_1_search(city='北京')",
    execution_result=[{"name": "万豪酒店", "price": 888}],
)
builder = PyTODPromptBuilder(few_shot_examples=[example])
```

---

## 与其他模式的对比

| 特性 | DST | FnCTOD | PyTOD |
|------|-----|--------|-------|
| 输出格式 | 槽位-值 JSON | 函数调用 | 程序语句 |
| API 集成 | ❌ | ❌ | ✅ 支持真实 API |
| 意图预定义 | 可选 | 可选 | 可选（开放域模式无需预定义）|
| 复杂度 | 低 | 中 | 高（三步流水线）|
| 适用场景 | 结构化信息提取 | 函数调用场景 | 需要真实数据查询 |

---

## 参考

- 原始论文：[PyTOD: Programmable Task-Oriented Dialogue via a Large Language Model](https://arxiv.org/abs/2212.09571)（Apple 研究院）
- 相关模式：[DST 模式](../dst/README.md)、[FnCTOD 模式](../fnctod/README.md)
