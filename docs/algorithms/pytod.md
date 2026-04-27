# PyTOD 算法文档

## 概述

**PyTOD**（Task-Oriented Dialogue as Dataflow Synthesis，数据流合成驱动的任务型对话）已在 ContextMind 中完整实现。该方法将任务型对话建模为**数据流程序合成**问题：每一轮对话由动作解析器（AP）生成可执行的 Python-like 程序，执行引擎（EE）真实调用 API，对话管理器（DM）基于执行结果生成回复。

- **实现状态**: ✅ 已实现
- **论文**: [Task-Oriented Dialogue as Dataflow Synthesis](https://arxiv.org/abs/2009.11423)（TACL 2020 / NAACL 2021）
- **官方源码**: https://github.com/microsoft/task_oriented_dialogue_as_dataflow_synthesis
- **使用数据集**: SGD（Schema-Guided Dialogue），详见 [`docs/datasets/sgd.md`](../datasets/datasets.md)

### 三步框架依赖

| 步骤 | 是否需要 | 说明 |
|------|:-------:|------|
| **① 建立知识库** | ✅ 可选 | 可从原始对话自动生成 `schema.json`，也可手写 Schema |
| **② Schema 数据生成** | ✅ 可选 | 将 `schema.json` 自动生成 PyTOD API 代码文件（`xxx_pytod_apis.py`） |
| **③ 算法执行（PyTOD）** | ✅ 必须 | AP→EE→DM 三步数据流程序执行流程 |

PyTOD 是唯一可以完整利用三步框架的算法：第一步生成 Schema，第二步自动生成 API 实现代码，第三步驱动程序执行型对话。也可以跳过前两步，直接手写 API 进入第三步。

---

## 核心思想

PyTOD 将任务型对话建模为**数据流程序合成**（Dataflow Synthesis）：每一轮对话产生一个可执行的 Python-like 程序，程序执行结果驱动回复生成。

```
用户: "帮我查一下账户余额"
↓ AP（动作解析器）
x1 = query_balance(account_id="ACC-001")
say(x1.balance)
↓ EE（执行引擎）
x1 = {"balance": "¥8,230.00", "status": "正常"}
↓ DM（对话管理器）
"您的账户余额为 ¥8,230.00，账户状态正常。"
```

**核心优势**：跨轮次变量引用（`x2 = query_loan(user_id=x1.user_id)`）使对话管理器能精确传达 API 执行结果，大幅减少幻觉。

---

## 算法架构

### 1. 动作解析器（Action Parser）

AP 是核心 LLM 组件，输入对话历史 + ServiceSchema（函数签名 + 描述）+ 已计算变量（Dataflow Context），输出 PyTOD 程序：

```python
x1 = verify_identity(user_name="张三", phone="138xxxx5678")
x2 = query_account(user_id=x1.user_id)     # 引用上一轮变量
say(x2.balance, x2.due_date)               # 指定 DM 要传达的内容
```

**关键语句类型**：

| 语句 | 含义 |
|------|------|
| `xN = func(...)` | 调用 API，绑定结果 |
| `say(xN.field)` | 告诉 DM 要传达的内容 |
| `hint(msg)` | 向 DM 提供补充说明 |
| `confirm(xN.field, val)` | 请求用户确认某个值 |
| `xN.slot = val` | 槽位赋值 |

当 Schema 包含大量 API 时，AP 使用**多信号 BM25 意图检索**（top-K，默认 5），仅将最相关的意图注入 prompt，节省 Token。

### 2. 执行引擎（Execution Engine）

EE 是**无 LLM 的确定性组件**，通过正则 + AST 解析程序文本并安全执行（不使用 `eval()`）：
- 解析 `xN = func(kwargs)` 语句，查 registry 调用已注册的 API 函数
- 管理变量绑定表 `{x1: {...}, x2: {...}}`
- 收集 `say()`、`hint()` 内容传给 DM
- 支持模糊函数名匹配（`difflib`，cutoff=0.6）
- 对无法解析的语句降级为存根执行，保证流程不中断

### 3. 对话管理器（Dialogue Manager）

DM 接收对话历史、AP 程序文本、EE 执行结果，生成自然语言回复，**优先传达 `say()` 指定的内容**。

---

## ContextMind 中的实现状态

### 已完成

PyTOD 核心算法已在 `contextmind/modes/pytod/` 目录下完整实现：

```
contextmind/modes/pytod/
├── __init__.py           # 模块入口，导出所有公共接口
├── tracker.py            # AdkPyTODTracker — 主追踪器（三步流程协调）
├── prompts.py            # PyTODPromptBuilder — AP 和 DM 提示词构建
├── execution_engine.py   # ExecutionEngine — 解析并执行 PyTOD 程序语句
├── registry.py           # 意图注册表
└── schemas.py            # ServiceSchema / IntentDefinition / SlotDefinition
```

### 待完成（评测集成）

| 内容 | 状态 |
|------|------|
| SGD 数据集适配（`benchmark/datasets/sgd.py`） | ⏳ 待实现 |
| PyTOD 评测指标（`benchmark/evaluators/pytod.py`） | ⏳ 待实现 |
| 评测命令（`--algorithm pytod`） | ⏳ 待实现 |

---

## 快速使用

### 完整三步流程（推荐）

```python
import asyncio
from contextmind.knowledge import KnowledgeBaseBuilder
from contextmind.schema_builder import SchemaDataBuilder
from contextmind.modes.pytod import AdkPyTODTracker, ExecutionEngine
from contextmind.infra.llm_client import AdkLLMClient

llm = AdkLLMClient()

# 第一步：建立知识库（从原始业务对话生成 schema.json）
kb_builder = KnowledgeBaseBuilder(scene_name="餐厅预订", llm_client=llm)
schema_dict = kb_builder.build(my_dialogues)
kb_builder.save(schema_dict, "output/restaurant_schema.json")

# 第二步：Schema 数据生成（自动生成 PyTOD API 代码）
schema_builder = SchemaDataBuilder(
    llm_client=llm,
    schema_path="output/restaurant_schema.json",
    test_data_paths=["resources/data/restaurant_test.json"],  # 可选
)
schema_builder.build_pytod_apis(output_path="output/restaurant_apis.py")

# 第三步：算法执行（加载 API，运行 PyTOD 对话）
engine = ExecutionEngine()
from output.restaurant_apis import INTENT_REGISTRY
for name, fn in INTENT_REGISTRY.items():
    engine.register(name)(fn)

service_schema = KnowledgeBaseBuilder.load_schema("output/restaurant_schema.json")
tracker = AdkPyTODTracker(llm_client=llm, engine=engine, schema=service_schema)

async def main():
    result = await tracker.process_turn("我要预订一家餐厅")
    print(result["response"])

asyncio.run(main())
```

### 开放域模式（仅第三步，无需预定义意图）

```python
from contextmind.modes.pytod import AdkPyTODTracker
from contextmind.infra.llm_client import AdkLLMClient

tracker = AdkPyTODTracker(llm_client=AdkLLMClient())
response = await tracker.process_turn("查一下北京今天的天气")
```

### Schema 驱动模式（跳过第二步，使用预定义意图和槽位）

```python
from contextmind.modes.pytod import AdkPyTODTracker, ServiceSchema, load_schema_from_dict
from contextmind.infra.llm_client import AdkLLMClient

schema = load_schema_from_dict({...})  # 加载 JSON schema
tracker = AdkPyTODTracker(llm_client=AdkLLMClient(), schema=schema)
response = await tracker.process_turn("我要预订一家餐厅")
```

---

## 参考资料

- [PyTOD 论文：Task-Oriented Dialogue as Dataflow Synthesis](https://arxiv.org/abs/2009.11423)（TACL 2020）
- [SGD 数据集文档](../datasets/datasets.md)
- [SGD 原始论文](https://arxiv.org/abs/1909.05855)
- [DST 算法文档](dst.md)
- [FnCTOD 算法文档](fnctod.md)
