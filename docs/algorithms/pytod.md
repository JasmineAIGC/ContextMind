# pyTOD 算法文档

## 概述

**pyTOD**（Programmable Task-Oriented Dialogue，可编程任务型对话）已在 ContextMind 中完整实现。它由 Apple 研究院提出，将任务型对话建模为**程序执行**问题：对话管理器生成可执行的程序语句，由执行引擎实际调用 API 并返回执行反馈。

- **实现状态**: ✅ 已实现
- **官方源码**: https://github.com/apple/ml-pytod
- **论文**: [PyTOD: Programmable Task-Oriented Dialogue with Execution Feedback](https://arxiv.org/pdf/2508.15456)（2025）
- **使用数据集**: SGD（Schema-Guided Dialogue），详见 [`docs/datasets/sgd.md`](../datasets/datasets.md)

### 三步框架依赖

| 步骤 | 是否需要 | 说明 |
|------|:-------:|------|
| **① 建立知识库** | ✅ 可选 | 可从原始对话自动生成 `schema.json`，也可使用预定义 SGD Schema |
| **② Schema 数据生成** | ✅ 可选 | 将 `schema.json` 自动生成 PyTOD API 代码文件（`xxx_pytod_apis.py`） |
| **③ 算法执行（PyTOD）** | ✅ 必须 | AP→EE→DM 三步程序执行流程 |

PyTOD 是唯一可以完整利用三步框架的算法：第一步生成 Schema，第二步自动生成 API 实现代码，第三步驱动程序执行型对话。当然也可以跳过前两步，直接手写 API 进入第三步。

---

## 核心思想

pyTOD 的创新在于引入了**执行反馈（Execution Feedback）**机制：

```
传统 TOD 流程：
  用户输入 → LLM 生成系统回复 → 输出

pyTOD 流程：
  用户输入
    ↓
  动作解析器（Action Parser）
    → 生成程序语句（如：hotels_1_search_hotel(city='San Jose')）
    ↓
  执行引擎（Execution Engine）
    → 实际调用 API / 数据库查询
    → 返回执行结果（如：[{"name": "Sino", "rating": 4.5}]）
    ↓
  对话管理器（Dialogue Manager）
    → 基于执行结果生成系统回复
    ↓
  系统输出
```

**核心优势**：真实的 API 调用结果替代 LLM 幻觉，大幅提升事实准确性。

---

## 与 DST / FnCTOD 的对比

| 维度 | DST | FnCTOD | pyTOD |
|------|-----|--------|-------|
| **对话范式** | 槽位填充 | 函数调用格式 | 程序执行 |
| **输出类型** | 对话状态（JSON） | 函数调用（XML） | 可执行程序语句 |
| **API 集成** | ❌ 无 | ❌ 无 | ✅ 真实 API 调用 |
| **执行反馈** | ❌ 无 | ❌ 无 | ✅ 真实执行结果 |
| **数据集** | TransferTOD、RiSAWOZ | TransferTOD | SGD |
| **实现复杂度** | ⭐⭐ 简单 | ⭐⭐⭐ 中等 | ⭐⭐⭐⭐⭐ 复杂 |
| **准确性** | 中 | 高 | 最高（有执行验证） |

---

## 算法架构

pyTOD 包含以下核心组件（来自官方源码）：

### 1. 动作解析器（Action Parser）

将用户输入解析为结构化程序语句：

```
用户输入：
  "I want to make a restaurant reservation for 2 people at half past 11 in the morning."

动作解析器输出（PyTOD 程序）：
  x1 restaurants_2_reserve_restaurant(time='half past 11 in the morning', number_of_seats=2)
  x2 Hint('request value: restaurant_name')
  x3 Hint('request value: location')
  x4 say(x2, x3)
```

### 2. 执行引擎（Execution Engine）

执行程序语句，调用真实 API/数据库：

```
输入：x1 restaurants_2_reserve_restaurant(location='San Jose', restaurant_name='Sino')

执行过程：
  1. 查询数据库（mongoquery 模拟）
  2. 验证 API 参数
  3. 执行事务（预订确认）
  4. 返回执行结果

输出：
  - phone_number: '408-247-8880'
  - address: '377 Santana Row #1000'
  - has_vegetarian_options: True
```

### 3. 模拟环境（Simulation）

基于 SGD 数据集实现的 API 模拟：

- **SearchCommand**：搜索类 API（如 `FindHotels`、`FindRestaurants`）
- **ConfirmedCommand**：事务类 API（如 `BookHotel`、`BuyTickets`）
- **Database**：基于 `mongoquery` 的内存数据库模拟
- **Policy Graph**：SGD 策略图，指导系统行为

### 4. 提示词模块（Prompting）

将结构化程序转换为 text-to-text 格式，用于 LLM 微调：

```
输入（source）：
  [HISTORY] user: I want to book a hotel...
  [CURRENT] user: In San Jose, please.

输出（target）：
  x1.location = 'San Jose'
  x6 Hint('ask the user to confirm: date')
  x7 say(x6)
```

---

## SGD 数据集集成

pyTOD 使用 SGD（Schema-Guided Dialogue）数据集，详细说明见 [SGD 数据集文档](../datasets/datasets.md)。

关键特性：
- 20 个服务，16 个领域
- 16,000+ 标注对话（train/dev/test）
- 每个对话包含 API Schema、对话状态、服务调用记录
- pyTOD 在此基础上增加了可执行 API 模拟

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

基准评测所需组件尚未实现：

| 阶段 | 内容 | 状态 |
|------|------|------|
| P0 | SGD 数据集适配 | ⏳ 待实现 |
| P0 | pyTOD 评测指标（`benchmark/evaluators/pytod.py`） | ⏳ 待实现 |
| P1 | 评测命令（`python benchmark/run_benchmark.py --algorithm pytod`） | ⏳ 待实现 |
| P2 | 与 DST/FnCTOD 对比实验 | ⏳ 待实现 |

### 评测指标（待实现）

除标准 DST 指标外，pyTOD 还将引入：

| 指标 | 说明 |
|------|------|
| **动作准确率**（Action Accuracy） | 预测动作序列与标注一致的比例 |
| **API 调用成功率** | 成功调用 API 并获得有效结果的比例 |
| **端到端任务完成率** | 整个任务（包括 API 调用）完成的比例 |
| **执行反馈准确率** | 基于执行结果生成正确系统回复的比例 |

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

- [pyTOD 官方 GitHub](https://github.com/apple/ml-pytod)
- [PyTOD 论文：PyTOD: Programmable Task-Oriented Dialogue with Execution Feedback](https://arxiv.org/pdf/2508.15456)（2025）
- [SGD 数据集文档](../datasets/datasets.md)
- [SGD 原始论文](https://arxiv.org/abs/1909.05855)
- [DST 算法文档](dst.md)
- [FnCTOD 算法文档](fnctod.md)
