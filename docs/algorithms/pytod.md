# pyTOD 算法文档

## 概述

**pyTOD**（Programmable Task-Oriented Dialogue，可编程任务型对话）已在 ContextMind 中完整实现。它由 Apple 研究院提出，将任务型对话建模为**程序执行**问题：对话管理器生成可执行的程序语句，由执行引擎实际调用 API 并返回执行反馈。

- **实现状态**: ✅ 已实现
- **官方源码**: https://github.com/apple/ml-pytod
- **论文**: [PyTOD: Programmable Task-Oriented Dialogue with Execution Feedback](https://arxiv.org/abs/2508.15456)
- **使用数据集**: SGD（Schema-Guided Dialogue），详见 [`docs/datasets/sgd.md`](../datasets/sgd.md)

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

pyTOD 使用 SGD（Schema-Guided Dialogue）数据集，详细说明见 [SGD 数据集文档](../datasets/sgd.md)。

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
├── tracker.py            # PyTODTracker — 主追踪器（三步流程协调）
├── prompt_builder.py     # PyTODPromptBuilder — 动作解析器和对话管理器 prompt 构建
├── execution_engine.py   # ExecutionEngine — 安全解析并执行程序语句
├── schema.py             # ServiceSchema / IntentDefinition / SlotDefinition
└── validator.py          # ActionValidator — 动作合法性校验
```

### 待完成（评测集成）

基准评测所需组件尚未实现：

| 阶段 | 内容 | 状态 |
|------|------|------|
| P0 | SGD 数据集适配（`benchmark/datasets/sgd/adapter.py`） | ⏳ 待实现 |
| P0 | pyTOD 评测指标（`benchmark/algorithms/pytod.py`） | ⏳ 待实现 |
| P1 | 评测脚本（`run_pytod_sgd.py`） | ⏳ 待实现 |
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

## 参考实现

pyTOD 官方源码的核心文件结构：

```
ml-pytod/src/pytod/
├── simulation/              # API 模拟环境
│   ├── api_driver.py        # SGD 事务型 API 模拟
│   ├── database.py          # 数据库模拟（mongoquery）
│   └── services/            # 具体服务实现
│       ├── hotels.py
│       ├── restaurants.py
│       └── ...
├── execution/               # 执行引擎
│   └── execute_instructions.py
├── interpreter/             # SGD → PyTOD 程序转换
├── parser/                  # 程序解析器（pydantic 验证）
├── prompting/               # text-to-text 格式转换
└── evaluation/              # DSTC8 评估代码
```

### 快速体验官方实现

```bash
# 克隆官方源码
git clone https://github.com/apple/ml-pytod.git
cd ml-pytod

# 安装依赖
pipenv install

# 下载 SGD 数据集
chmod +x scripts/fetch_data.sh && bash scripts/fetch_data.sh

# 初始化 pyTOD 环境（构建数据库、API 模拟等）
chmod +x scripts/pytod_setup.sh && bash scripts/pytod_setup.sh

# 转换 SGD 对话为 pyTOD 格式
pipenv run python scripts/create_pytod_dialogues.py \
    filters=v0.6.1 version=v0.9.1 interpreter=v0.5 \
    split=train --config-name=v3

# 查看示例对话
pipenv run display_pytod split=dev ids="['1_00000']" version=v0.9.1

# 在测试集上评测
pipenv run python scripts/evaluate_pytod.py split=dev version=v0.9.1
```

---

## 快速使用

### 开放域模式（无需预定义意图）

```python
from contextmind.modes.pytod import PyTODTracker
from contextmind.infra.llm_client import SimpleLLMClient

tracker = PyTODTracker(llm_client=SimpleLLMClient())
response = await tracker.process_turn("查一下北京今天的天气")
```

### Schema 驱动模式（预定义意图和槽位）

```python
from contextmind.modes.pytod import PyTODTracker, ServiceSchema, load_schema_from_dict
from contextmind.infra.llm_client import SimpleLLMClient

schema = load_schema_from_dict({...})  # 加载 JSON schema
tracker = PyTODTracker(llm_client=SimpleLLMClient(), schema=schema)
response = await tracker.process_turn("我要预订一家餐厅")
```

---

## 开发计划

### ContextMind 中的 pyTOD 评测集成优先级

| 阶段 | 内容 | 优先级 | 状态 |
|------|------|--------|------|
| P0 | SGD 数据集适配（`SGDAdapter`） | 高 | ⏳ 待实现 |
| P0 | pyTOD 评测指标实现（`PyTODEvaluator`） | 高 | ⏳ 待实现 |
| P1 | 微调数据生成 | 低 | ⏳ 待实现 |
| P2 | 与 DST/FnCTOD 对比实验 | 低 | ⏳ 待实现 |

---

## 参考资料

- [pyTOD 官方 GitHub](https://github.com/apple/ml-pytod)
- [PyTOD 论文](https://arxiv.org/abs/2508.15456)
- [SGD 数据集文档](../datasets/sgd.md)
- [SGD 原始论文](https://arxiv.org/abs/1909.05855)
- [DST 算法文档](dst.md)
- [FnCTOD 算法文档](fnctod.md)
