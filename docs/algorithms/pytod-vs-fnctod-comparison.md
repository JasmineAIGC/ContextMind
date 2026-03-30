# PyTOD 与 FnCTOD 深度对比分析

> **文档目的**：系统梳理 ContextMind 中已实现的两种任务型对话框架——PyTOD 与 FnCTOD——在设计哲学、
> 架构实现、性能特点与适用场景上的本质差异，为选型决策提供完整依据。

---

## 目录

1. [框架概述](#1-框架概述)
2. [设计哲学对比](#2-设计哲学对比)
3. [架构组件对比](#3-架构组件对比)
4. [Schema 与预定义要求](#4-schema-与预定义要求)
5. [LLM 调用模式对比](#5-llm-调用模式对比)
6. [执行与状态管理对比](#6-执行与状态管理对比)
7. [输出格式对比](#7-输出格式对比)
8. [失败降级与容错对比](#8-失败降级与容错对比)
9. [性能特征对比](#9-性能特征对比)
10. [实际应用：安逸花质检场景](#10-实际应用安逸花质检场景)
11. [选型决策指南](#11-选型决策指南)
12. [核心结论](#12-核心结论)

---

## 1. 框架概述

| 维度 | PyTOD | FnCTOD |
|------|-------|--------|
| **全称** | Programmable Task-Oriented Dialogue（可编程任务型对话） | Function Calling for Task-Oriented Dialogue（函数调用任务型对话） |
| **学术来源** | Apple Research，arxiv:2508.15456 | Meta AI，ACL 2024，arxiv:2405.02568 |
| **核心隐喻** | **程序执行**——对话管理器生成可执行程序，引擎真实运行它 | **函数调用**——LLM 像调用函数一样填充 Schema 定义的参数 |
| **ContextMind 实现路径** | `contextmind/modes/pytod/` | `contextmind/modes/fnctod/` |
| **入口追踪器** | `AdkPyTODTracker` | `FnCTODTracker` |
| **已知测试数据集** | SGD（Schema-Guided Dialogue）、安逸花外呼质检 | TransferTOD、安逸花外呼质检 |

---

## 2. 设计哲学对比

### 2.1 PyTOD：执行反馈优先

PyTOD 的核心洞见是：**LLM 生成的回复容易产生幻觉，而真实 API 调用返回的结果不会**。

```
传统 TOD 缺陷：
  用户: 我想查北京的天气
  LLM: 北京今天晴，18~25℃，东南风。      ← 幻觉！LLM 根本没有实时天气数据

PyTOD 解法：
  用户: 我想查北京的天气
  动作解析器 → get_weather(city='北京')    ← 程序语句，不是幻觉
  执行引擎   → {"condition":"晴","temp_high":12,...}  ← 真实 API 调用
  对话管理器 → 北京今天晴，2~12℃...       ← 基于真实数据，无幻觉
```

**设计原则**：
- LLM 只负责「意图识别 + 参数提取」，不负责「数据生成」
- 数据由真实 API/DB 提供，LLM 仅做自然语言翻译
- 对话管理与执行逻辑分离（三层架构）

### 2.2 FnCTOD：结构化约束优先

FnCTOD 的核心洞见是：**预先定义好 Schema，让 LLM 在约束框架内填充，比自由发挥准确得多**。

```
传统 DST 缺陷：
  "请从以下对话中提取槽位信息（JSON格式）..."
  LLM 自由发挥 → {"hotelName": "...", "checkin": "..."} ← 槽位名称不稳定

FnCTOD 解法：
  预定义 Schema: hotel_name(string), check_in_date(YYYY-MM-DD), room_type(enum)
  LLM 在约束内填充 → {"hotel_name": "希尔顿", "check_in_date": "2026-03-15", "room_type": "大床房"}
                     ← 名称统一，格式稳定
```

**设计原则**：
- Schema 是第一公民，LLM 是填充工具
- 所有可能的领域和槽位必须提前定义
- LLM 的创造力被约束在有意义的范围内

---

## 3. 架构组件对比

### 3.1 PyTOD 三层架构

```
用户输入
  ↓
┌─────────────────────────────────────────┐
│ 层一：动作解析器（Action Parser）         │
│  · 组件：PyTODPromptBuilder              │
│  · 职责：LLM 根据 API 列表 + 对话历史    │
│          生成多行 PyTOD 程序语句          │
│  · 输出：x1 api_name(param='value')      │
│          x2 Hint('request: slot')        │
│          x3 say(x2)                      │
└──────────────────┬──────────────────────┘
                   ↓ 程序语句
┌─────────────────────────────────────────┐
│ 层二：执行引擎（Execution Engine）        │
│  · 组件：ExecutionEngine                 │
│  · 职责：AST 安全解析程序，调用注册 API   │
│  · 安全：不使用 eval()；仅允许注册函数   │
│  · 输出：{"city":"北京","temp_high":12}  │
└──────────────────┬──────────────────────┘
                   ↓ 执行结果
┌─────────────────────────────────────────┐
│ 层三：对话管理器（Dialogue Manager）      │
│  · 组件：PyTODPromptBuilder              │
│  · 职责：LLM 根据执行结果生成自然语言     │
│  · 输出："北京今天晴，2~12℃，西北风3级"  │
└─────────────────────────────────────────┘
```

**关键组件清单**：

| 组件 | 文件 | 职责 |
|------|------|------|
| `ExecutionEngine` | `execution_engine.py` | 程序解析与安全执行 |
| `PyTODPromptBuilder` | `prompt_builder.py` | Action Parser / DM 的 Prompt 构建 |
| `ServiceSchema` / `SlotDefinition` | `schema.py` | 可选 Schema 数据结构 |
| `ActionValidator` | `validator.py` | 动作合法性校验 |
| `AdkPyTODTracker` | `tracker.py` | 三步流程编排，接口统一 |

### 3.2 FnCTOD 两层架构

```
用户输入
  ↓
┌─────────────────────────────────────────┐
│ [两阶段模式] Stage 1：域选择             │
│  · 组件：FunctionManager                 │
│  · LLM 选择匹配的 Domain                 │
│  · 输出：<domain>酒店</domain>           │
└──────────────────┬──────────────────────┘
                   ↓ 目标 Domain
┌─────────────────────────────────────────┐
│ Stage 2：函数调用（参数填充）             │
│  · 组件：FunctionManager + LLM           │
│  · LLM 根据 Schema 填充参数              │
│  · 输出：<function_call name="酒店">     │
│          {"hotel_name":"希尔顿",...}     │
│          </function_call>               │
│          您好，我来为您预订希尔顿酒店... │
└──────────────────┬──────────────────────┘
                   ↓ 状态 + 自然语言
┌─────────────────────────────────────────┐
│ 状态累积（Cumulative State）             │
│  · 组件：FnCTODTracker                  │
│  · 新参数合并到历史状态                  │
│  · 最终状态即为完整的对话状态追踪结果    │
└─────────────────────────────────────────┘
```

**关键组件清单**：

| 组件 | 文件 | 职责 |
|------|------|------|
| `FnCTODTracker` | `fnctod_tracker.py` | 两阶段流程编排 |
| `FunctionManager` | `function_manager.py` | Schema 加载、验证、Prompt 生成 |
| `FnCTODResponseParser` | `response_parser.py` | 从 LLM 输出提取 function_call JSON |
| `DomainSpec` / `FunctionParameter` | `data_models.py` | Schema 数据结构 |
| `fnctod_prompts.yaml` | — | 系统提示词模板（外置 YAML） |

---

## 4. Schema 与预定义要求

这是两个框架**最根本的差异**。

### 4.1 PyTOD：Schema 可选，支持开放域

```python
# 开放域模式（默认）：无需任何预定义
tracker = AdkPyTODTracker(
    llm_client=llm,
    execution_engine=engine,   # 注册了哪些 API 函数就能用哪些
    prompt_builder=PyTODPromptBuilder(schema=None),  # schema=None 开放域
)
# LLM 自由命名意图（如 get_weather、search_info）
# 和槽位（city、date、topic），无需事先声明

# Schema 约束模式（生产环境）：可选注入，增强 LLM 理解
tracker = AdkPyTODTracker(
    ...
    prompt_builder=PyTODPromptBuilder(schema=my_service_schema),
)
```

**开放域模式的工作原理**：
1. `PyTODPromptBuilder` 将执行引擎已注册函数的函数签名自动列出
2. LLM 根据函数名和参数名（加上 docstring）理解 API 语义
3. LLM 以自然方式生成调用语句，即使没有枚举约束也能工作

```python
# ExecutionEngine 注册即可用，无需 Schema：
@engine.register
def get_weather(city=None, date=None):
    """查询天气预报。支持今天/明天，或指定城市。"""
    ...

# PyTOD prompt 自动注入：
# "可用 API：get_weather(city, date) — 查询天气预报。支持今天/明天，或指定城市。"
```

### 4.2 FnCTOD：必须预定义 Schema

```python
# ❌ 无法在没有 Schema 的情况下运行
tracker = FnCTODTracker(llm_client=llm, function_manager=FunctionManager())
# 缺少 Domain 定义，无法生成系统提示词，LLM 不知道要填充什么

# ✅ 必须预先定义 DomainSpec
function_manager = FunctionManager()
function_manager.add_domain_from_slots(
    domain_name="酒店",
    domain_description="酒店预订场景",
    slots={"hotel_name": "酒店名称", "check_in_date": "入住日期"},
    categorical_slots={"room_type": ["标准间", "大床房", "套房"]},
    required_slots=["hotel_name"]
)
tracker = FnCTODTracker(llm_client=llm, function_manager=function_manager)
```

**FnCTOD 对 Schema 的依赖原因**：
1. 系统提示词由 `FunctionManager.generate_system_prompt()` 动态生成，**没有 Schema 就没有提示词**
2. `FnCTODResponseParser` 需要知道合法的函数名来验证 `<function_call name="xxx">` 的 xxx
3. 枚举约束（`enum_values`）必须在 Schema 中声明才能注入 prompt

### 4.3 Schema 对比摘要

| 特性 | PyTOD | FnCTOD |
|------|-------|--------|
| **是否必须预定义** | ❌ 可选 | ✅ 必须 |
| **Schema 数据结构** | `ServiceSchema` + `SlotDefinition` | `DomainSpec` + `FunctionParameter` |
| **开放域运行** | ✅ 支持（schema=None） | ❌ 不支持 |
| **枚举约束** | Schema 提供，但不强制 | Schema 提供，LLM 必须遵守 |
| **函数/API 定义** | 通过 `@engine.register` 注册 Python 函数 | 通过 `DomainSpec` 声明 JSON Schema |
| **新领域扩展** | 注册新函数即可，无需修改 Schema | 必须更新 DomainSpec |

---

## 5. LLM 调用模式对比

### 5.1 PyTOD：两次 LLM 调用（标准）+ 优化路径

```
标准流程（有 API 执行结果时）：
  LLM 调用①：动作解析器  → 生成程序语句
  ────────── 执行引擎 ──────────
  LLM 调用②：对话管理器  → 生成自然语言回复

优化路径①（say() 语句直接给出回复）：
  LLM 调用①：动作解析器  → 生成 say(hint_message)
  ────────── 执行引擎 ──────────
  直接输出 say_output，跳过 LLM 调用②

优化路径②（NONE() 后备）：
  LLM 调用①：动作解析器  → NONE()（无动作）
  LLM 调用②：后备对话管理器 → 纯对话回复（无执行结果）
```

**典型每轮 LLM 调用次数**：
- 有 API 调用 + 需要翻译：**2 次**
- say() 输出路径：**1 次**（节省 1 次）
- NONE() 后备路径：**2 次**（但第二次是轻量后备 prompt）

### 5.2 FnCTOD：1~2 次 LLM 调用

```
两阶段模式（多 domain 时）：
  LLM 调用①：域选择     → <domain>酒店</domain>
  LLM 调用②：函数调用   → <function_call>{"hotel_name":"希尔顿"}</function_call> + 自然语言

单阶段模式（单 domain 或 domain 已知时）：
  LLM 调用①：函数调用   → <function_call>{"hotel_name":"希尔顿"}</function_call> + 自然语言
  （跳过域选择，节省约 30% 时间）
```

**FnCTOD 每次函数调用 LLM 响应同时包含两部分**：
- `<function_call>` 标签内的 JSON（结构化状态）
- 标签外的自然语言（面向用户的回复）

因此 FnCTOD 的"自然语言生成"不是单独一次 LLM 调用，而是与"参数提取"合并在同一次调用中完成。

### 5.3 调用次数对比

| 场景 | PyTOD | FnCTOD（两阶段） | FnCTOD（单阶段） |
|------|-------|----------------|----------------|
| 标准路径 | **2 次** | **2 次** | **1 次** |
| 最优路径 | **1 次**（say() 直接输出） | **1 次**（单阶段） | **1 次** |
| 最差路径 | **2 次**（NONE 后备） | **2 次** | **1 次** |
| 自然语言生成 | 独立的第 2 次调用 | 与参数提取合并 | 与参数提取合并 |

---

## 6. 执行与状态管理对比

### 6.1 PyTOD：真实 API 执行 + 变量空间状态

PyTOD 执行引擎维护一个**变量空间**（variable space），每个 API 调用的结果绑定到变量名：

```python
# 程序执行后的变量空间：
exec_result.variable_values = {
    "x1": {"city": "北京", "condition": "晴", "temp_high": 12, ...},  # get_weather 返回值
    "x2": "request value: check_in_date",                             # Hint 文本
}
exec_result.say_output = "request value: check_in_date"               # say(x2) 的输出
```

**状态累积机制**：AdkPyTODTracker 将执行结果中有意义的字段合并到 `current_state`：

```python
# current_state 随对话推进逐渐积累：
# 第 1 轮：{"city": "北京"}
# 第 2 轮：{"city": "北京", "check_in_date": "2026-03-15"}
# 第 3 轮：{"city": "北京", "check_in_date": "2026-03-15", "hotel_name": "希尔顿"}
```

**执行安全保证**：
- 使用 Python `ast` 模块解析程序，**不使用 `eval()`**
- 参数类型限制为 `str`、`int`、`float`、`bool`、`None`
- 只允许调用已在引擎注册表中的函数
- 拒绝执行任意代码

### 6.2 FnCTOD：Schema 驱动的累积状态

FnCTOD 的状态是 LLM 每轮输出的 function_call 参数的**累积合并**：

```python
# 第 1 轮 function_call：{"hotel_name": "希尔顿"}
# 第 2 轮 function_call：{"hotel_name": "希尔顿", "check_in_date": "2026-03-15"}
# 第 3 轮 function_call：{"hotel_name": "希尔顿", "check_in_date": "2026-03-15", "room_type": "大床房"}

# current_state 即为第 3 轮 function_call.arguments（含所有历史参数）
# FnCTOD 论文设计：每次输出时携带全量参数（不是增量），天然具有累积能力
```

**状态来源的本质差异**：

| | PyTOD | FnCTOD |
|---|-------|--------|
| **状态数据来源** | 真实 API 调用返回值 | LLM 从对话中提取的参数 |
| **数据可靠性** | 高（来自真实系统） | 中（LLM 提取，可能出错） |
| **状态字段约束** | 无约束（任意 API 返回值） | 严格约束（Schema 中定义的槽位） |
| **跨轮一致性** | 依赖执行引擎正确性 | 依赖 LLM 遵循 Schema + 累积策略 |

---

## 7. 输出格式对比

### 7.1 PyTOD 程序语句

动作解析器生成的程序（LLM 输出，执行引擎解析执行）：

```
x1 get_weather(city='北京', date='明天')
x2 Hint('request value: 出行目的')
x3 say(x1, x2)
```

支持的语句类型：
- **API 函数调用**：`x1 func_name(key='value')`
- **槽位赋值**：`x1.param = 'value'`（补充参数）
- **Hint 语句**：`x2 Hint('request value: slot_name')`
- **say 语句**：`x3 say(x1, x2)`（组合输出）
- **NONE()**：无需调用任何 API

### 7.2 FnCTOD 函数调用 + 自然语言

LLM 的完整输出（单次 LLM 响应包含两部分）：

```xml
<function_call name="酒店预订">
{"hotel_name": "希尔顿", "check_in_date": "2026-03-15", "room_type": "大床房"}
</function_call>
好的，我已为您记录预订信息：希尔顿酒店，入住日期 3 月 15 日，大床房。请问需要几位入住？
```

解析器提取：
- `function_call.name` → 函数名（Domain）
- `function_call.arguments` → 参数字典（状态更新）
- 标签后内容 → 自然语言回复

### 7.3 输出格式设计哲学

| 维度 | PyTOD | FnCTOD |
|------|-------|--------|
| **结构化输出** | 程序代码风格（`x1 func(arg='val')`） | XML 标签包裹 JSON（`<function_call>`） |
| **自然语言来源** | 独立第三步 LLM 调用生成 | 与结构化输出合并在同一 LLM 响应中 |
| **错误处理** | 执行引擎返回错误，DM 解释原因 | 解析失败时宽松模式提取，降级处理 |
| **对 LLM 格式要求** | 较宽松（程序语法相对容忍） | 较严格（需要 XML + 合法 JSON） |

---

## 8. 失败降级与容错对比

### 8.1 PyTOD 容错机制

```python
# 动作解析器失败 → 使用 NONE()
try:
    program_text = await llm.chat_async(ap_messages)
except Exception:
    program_text = "NONE()"   # 安全后备

# 执行引擎失败 → exec_result = None，走后备对话路径
try:
    exec_result = engine.execute_program(program_text)
except Exception:
    exec_result = None

# 对话管理器失败 → 固定兜底回复
try:
    response = await llm.chat_async(dm_messages)
except Exception:
    response = "抱歉，处理您的请求时出现了问题，请稍后重试。"

# NONE() 情况 → 使用轻量后备 prompt（不含执行结果）
if program_text == "NONE()":
    dm_messages = builder.build_fallback_messages(...)
    response = await llm.chat_async(dm_messages)
```

**PyTOD 失败路径**：执行引擎失败不会导致整轮崩溃，会降级为纯 LLM 对话模式。

### 8.2 FnCTOD 容错机制

```python
# 响应解析器支持多种宽松模式匹配：
# 1. 标准格式：<function_call name="xxx">{json}</function_call>
# 2. 宽松格式：function_call: {...}（各种变体）
# 3. 纯 JSON 格式：{"hotel_name": "希尔顿"}（直接提取）

# 域选择失败 → 降级使用第一个 Domain
if not domains:
    domains = [function_manager.get_domain_names()[0]]

# 函数调用解析失败 → 返回空状态，保留历史状态不变
# LLM 调用失败 → 场景降级为所有 Domain（宽泛匹配）
```

**FnCTOD 失败的主要风险**：如果 LLM 不遵循 `<function_call>` 格式，状态更新会失败，但自然语言回复仍可用。

### 8.3 容错能力对比

| 失败类型 | PyTOD | FnCTOD |
|--------|-------|--------|
| **API 执行失败** | 明确降级路径（exec_result=None） | N/A（无真实 API 执行） |
| **LLM 格式不合规** | 程序解析容忍度较高 | 响应解析器有宽松模式 |
| **Domain 识别失败** | N/A（不需要域选择） | 降级为第一个 Domain |
| **整轮崩溃风险** | 低（多层兜底） | 中（依赖 LLM 格式遵从） |

---

## 9. 性能特征对比

### 9.1 响应时间

基于 ContextMind 实现中记录的典型耗时数据：

| 步骤 | PyTOD | FnCTOD（两阶段） | FnCTOD（单阶段） |
|------|-------|----------------|----------------|
| 历史/Prompt 准备 | ~0.01s | ~0.01s | ~0.01s |
| Prompt 构建 | ~0.05s | ~0.05s | ~0.05s |
| LLM 调用①（解析/选域） | ~0.5–1.5s | ~0.5–1.0s | — |
| 执行引擎 | ~0.01s | N/A | N/A |
| LLM 调用②（回复/填充） | ~0.5–1.5s | ~1.0–1.5s | ~1.0–1.5s |
| 响应解析 | ~0.01s | ~0.03s | ~0.03s |
| **总计（典型）** | **~1.1–3.1s** | **~1.6–2.6s** | **~1.1–1.6s** |

> **注**：LLM 调用耗时取决于模型规模和网络延迟，以上为参考估算。

### 9.2 LLM Token 消耗

| 维度 | PyTOD | FnCTOD |
|------|-------|--------|
| **System prompt 大小** | 中（API 函数签名 + 格式说明） | 大（完整 JSON Schema + few-shot 示例） |
| **每轮输入 tokens** | 中（~800–1500） | 大（~1000–2500，含完整 Schema） |
| **每轮输出 tokens** | 中（程序语句 + 自然语言分两次） | 中（function_call JSON + 自然语言合一次） |
| **Schema 越大影响** | 小（只列出函数签名） | 大（JSON Schema 全量注入） |

### 9.3 准确率特征

基于 ContextMind 文档中记录的评测数据：

| 场景 | PyTOD（安逸花质检） | FnCTOD（TransferTOD） |
|------|-------------------|--------------------|
| **总体准确率** | 71%（修复后目标） | ~85–90%（TransferTOD 槽位准确率） |
| **机械性错误检测** | P=87% R=87%（数据错误、重复询问） | 依赖 Schema 覆盖度 |
| **语义性错误** | LLM 语义推理，规则辅助 | LLM 槽位填充 |
| **新领域扩展** | 注册新 API 即可 | 需更新 Schema |

---

## 10. 选型决策指南

### 11.1 应选 PyTOD 的场景

```
✅ 需要调用真实 API（CRM 查询、数据库查询、计算）
✅ 数据准确性要求极高（金额、状态、日期不能有幻觉）
✅ 业务逻辑需要 Python 代码执行（复杂计算、字符串匹配）
✅ 快速原型阶段（无需 Schema，直接注册函数就能运行）
✅ 意图/槽位边界尚未确定（开放域模式探索）
✅ 已有业务 API 函数，希望直接接入
✅ 质检、数据验证等规则与语义混合场景
```

**典型案例**：
- 银行余额查询（必须调真实 API，LLM 不能"猜"余额）
- 外呼质检（需要字符串匹配、金额偏差计算）
- 天气播报（需要实时数据 API）
- 订单查询（需要数据库查询）

### 11.2 应选 FnCTOD 的场景

```
✅ 对话状态追踪（DST）任务，Schema 稳定清晰
✅ 槽位名称、类型、枚举值需要高度一致性
✅ 无需调用外部 API，只需"理解和提取"用户意图
✅ 多领域单次对话（两阶段模式自动选域）
✅ 与下游系统的接口是"结构化参数 JSON"
✅ LLM 能力强，指令遵循性好
✅ TransferTOD 等标准 DST 评测场景
```

**典型案例**：
- 酒店/餐厅/机票预订（提取用户偏好，传给后端）
- 客服工单创建（收集结构化信息）
- 保险咨询（提取意图类型、险种、客户信息）

### 11.3 决策流程图

```
                    需要执行真实 Python 代码 / 调用 API？
                          ↙ 是              ↘ 否
                      PyTOD                槽位边界是否已明确定义？
                                                ↙ 是        ↘ 否
                                            FnCTOD        PyTOD（开放域）
                                              ↓
                                        多领域？ → 两阶段
                                        单领域？ → 单阶段（快 30%）
```

### 11.4 关键取舍汇总

| 决策维度 | 选 PyTOD | 选 FnCTOD |
|---------|--------|---------|
| 启动成本 | 低（注册函数即可） | 高（需设计 Schema） |
| 数据可靠性需求 | 高（有真实执行） | 中（LLM 提取） |
| Schema 稳定性 | 不要求 | 要求高（槽位不能频繁变动） |
| LLM 质量要求 | 中（程序语法容忍度高） | 高（必须遵循 XML+JSON 格式） |
| 扩展新功能 | 注册新函数 | 更新 Schema + 代码 |
| 标准 DST 评测 | 不适合（程序执行范式不同） | 适合 |
| 生产 API 集成 | 原生支持 | 需要额外适配层 |

---

## 12. 核心结论

### 12.1 本质区别一句话

> **PyTOD = 程序员写函数，LLM 调用它们**
> **FnCTOD = 设计师定义 Schema，LLM 填充它**

### 12.2 三个最重要的差异

1. **执行反馈（PyTOD 独有）**  
   PyTOD 的执行引擎真实运行代码，返回客观数据；FnCTOD 的"函数调用"只是 LLM 输出的格式约定，不真正执行代码。这一差异在数据准确性上至关重要。

2. **Schema 依赖（FnCTOD 必须）**  
   FnCTOD 在没有 Schema 的情况下无法运行；PyTOD 可以在 schema=None 模式下工作，通过函数签名自动理解 API 语义。

3. **LLM 调用中的职责分配**  
   PyTOD 将"理解意图"和"生成回复"拆成两次 LLM 调用，中间插入真实执行；FnCTOD 将"提取参数"和"生成回复"合并在一次 LLM 调用中，更高效但无真实执行。

### 12.3 互补关系

两个框架并非竞争关系，而是**互补**的：

```
                PyTOD                     FnCTOD
         ────────────────         ────────────────────
         真实数据 + 执行           Schema 约束 + 效率
              ↓                          ↓
         ──────────────────────────────────────
                    最优架构建议
              混合使用：PyTOD 执行引擎提供可靠
              事实数据，FnCTOD Schema 约束输出格式
              （如安逸花 QC 的 Hybrid 模式）
```

安逸花 QC 场景已经证明：PyTOD 执行引擎（事实提取）+ LLM 语义推理（classify_session_llm）的组合，比单独使用任何一方都更准确和高效。

---

*文档版本：2026-03-02 | 基于 ContextMind 实现代码逐行分析*
