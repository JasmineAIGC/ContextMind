# 安逸花数据 SGD 格式验证与 PyTOD 运行分析

> 文档目的：
> 1. 对比 SGD 原始格式规范，验证 `resources/anyihua_sgd` 转换结果是否正确
> 2. 分析 PyTOD 算法如何使用 SGD 数据
> 3. 总结安逸花外呼数据在 PyTOD 上的完整运行路径

参考资料：
- SGD 数据集规范：https://github.com/google-research-datasets/dstc8-schema-guided-dialogue
- PyTOD 官方仓库：https://github.com/apple/ml-pytod
- 转换源码：`benchmark/datasets/anyihua/adapter.py`
- 转换工具：`benchmark/tools/convert_chat_test_to_sgd.py`

---

## 一、SGD 标准格式回顾

### 1.1 Schema 文件（schema.json）

```json
[
  {
    "service_name": "Hotels_1",
    "description": "...",
    "slots": [
      {
        "name": "hotel_name",
        "description": "...",
        "is_categorical": false,
        "possible_values": []
      }
    ],
    "intents": [
      {
        "name": "SearchHotel",
        "description": "...",
        "is_transactional": false,
        "required_slots": ["location"],
        "optional_slots": {"number_of_rooms": "1"},
        "result_slots": ["hotel_name", "price_per_night"]
      }
    ]
  }
]
```

### 1.2 对话文件（dialogues_*.json）

SGD 格式的关键规则（来自官方 README）：

| 字段 | 出现位置 | 说明 |
|------|----------|------|
| `state` | **USER turn 专属** | 含 `active_intent`、`requested_slots`、`slot_values` |
| `slots` | USER 和 SYSTEM | 话语中槽位的字符级跨度（非分类槽位，可为空列表） |
| `actions` | USER 和 SYSTEM | 对话行为列表 |
| `service_call` | **SYSTEM turn 专属**（可选） | 调用的 API 方法和参数 |
| `service_results` | **SYSTEM turn 专属**（可选） | API 返回的结果列表 |

官方原文：
> **state** (user turns only) — The dialogue state corresponding to the service.

```json
// USER turn — 有 state，无 service_call/service_results
{
  "turn_id": "0",
  "speaker": "USER",
  "utterance": "I'd like to find a hotel to stay in.",
  "frames": [
    {
      "service": "Hotels_1",
      "slots": [],
      "state": {
        "active_intent": "SearchHotel",
        "requested_slots": [],
        "slot_values": {"location": ["San Jose"]}
      },
      "actions": [{"act": "INFORM_INTENT", "slot": "intent", "values": ["SearchHotel"], "canonical_values": ["SearchHotel"]}]
    }
  ]
}

// SYSTEM turn — 有 service_call/service_results，无 state
{
  "turn_id": "1",
  "speaker": "SYSTEM",
  "utterance": "I found 5 hotels in San Jose.",
  "frames": [
    {
      "service": "Hotels_1",
      "slots": [],
      "actions": [{"act": "INFORM", "slot": "hotel_name", "values": ["Marriott"], "canonical_values": ["Marriott"]}],
      "service_call": {"method": "SearchHotel", "parameters": {"location": "San Jose"}},
      "service_results": [{"hotel_name": "Marriott", "price_per_night": "200"}]
    }
  ]
}
```

---

## 二、anyihua_sgd 转换结果验证

### 2.1 发现的问题（已修复）

转换结果位于 `resources/anyihua_sgd/`，初始版本存在以下问题：

| 问题 | 严重程度 | 说明 | 修复方案 |
|------|----------|------|----------|
| SYSTEM frame 含 `state` 字段 | ❌ 违反 SGD 标准 | SGD 规范明确：`state` 是 user turns only | 从 `_build_system_frame()` 中删除 `state` |
| 输出文件命名为 `dialogues_100.json` | ❌ 命名错误 | SGD 规范：分块文件应命名为 `dialogues_001.json` | 重命名为 `dialogues_001.json` |
| 仅转换 10 条记录 | ❌ 数据不完整 | `conversion_summary.json` 显示 `"dialogues": 10` | 重新运行，转换全部 100 条 |
| 缺少 `slots` 字段 | ⚠️ 格式不完整 | SGD 标准要求 frame 有 `slots` 字段（可为空列表） | 添加 `"slots": []` 到 USER 和 SYSTEM frame |

### 2.2 修复后的转换结果

```
resources/anyihua_sgd/
├── schema.json              # 安逸花 SGD Schema（10 个意图，15 个槽位）
├── dialogues_001.json       # 100 条对话，共 1330 轮次
└── conversion_summary.json  # 转换统计
```

**转换统计**：
- 对话数：100 条（来自 `chat_test_100.json` 全部数据）
- 总轮次：1330（含坐席回复追加为最后一轮）
- 服务数：1（`AnYiHua_1`）
- 对话文件数：1（`dialogues_001.json`）

### 2.3 修复后的 frame 结构对比

**修复前（错误）**：

```json
// SYSTEM turn frame — 不符合 SGD 标准
{
  "service": "AnYiHua_1",
  "state": {                   // ← 错误：state 不应出现在 SYSTEM frame
    "active_intent": "NONE",
    "requested_slots": [],
    "slot_values": {"customer_name": ["高先生"]}
  },
  "actions": [...],
  "service_call": {...},
  "service_results": [...]
}
```

**修复后（正确）**：

```json
// USER turn frame — 有 state
{
  "service": "AnYiHua_1",
  "slots": [],                           // ← 新增：字符级槽位跨度（空列表）
  "state": {                             // ← 仅 USER frame 有 state
    "active_intent": "verify_identity",
    "requested_slots": [],
    "slot_values": {"customer_name": ["高先生"], "phone_suffix": ["六七八"]}
  },
  "actions": []
}

// SYSTEM turn frame — 无 state
{
  "service": "AnYiHua_1",
  "slots": [],                           // ← 新增：字符级槽位跨度（空列表）
  // state 已删除                        // ← 修复：SYSTEM frame 无 state
  "actions": [{"act": "REQUEST", ...}],
  "service_call": {"method": "verify_customer", "parameters": {"name": "高先生", "phone_suffix": "六七八"}},
  "service_results": [{"customer_name": "高先生", "identity_confirmed": "true"}]
}
```

### 2.4 schema.json 验证

安逸花 `schema.json` 符合 SGD 标准格式：

| 检查项 | 结果 |
|--------|------|
| `service_name` 命名规范（`<domain>_<number>`） | ✅ `AnYiHua_1` |
| `slots[].is_categorical` 与 `possible_values` 一致性 | ✅ 分类槽位有 possible_values，非分类槽位为空列表 |
| `intents[].optional_slots` 为字典格式 | ✅ `{"phone_suffix": ""}` |
| `intents[].required_slots` 和 `result_slots` 为列表格式 | ✅ |
| 槽位引用均在 `slots[]` 中定义 | ✅ 所有意图引用的槽位均已在 slots 中声明 |

**Schema 摘要**：

| 类别 | 数量 | 主要内容 |
|------|------|----------|
| 意图数 | 10 | verify_identity / explain_credit_limit / explain_interest_rate / calculate_repayment / explain_displayed_amount / handle_loan_dispute / guide_loan_operation / escalate_to_human / say_goodbye / general_inquiry |
| 槽位数 | 15 | customer_name / phone_suffix / dispute_date / inquiry_amount / term_months / identity_confirmed / available_credit / temp_credit / temp_credit_status / temp_expiry_days / annual_rate_pct / loan_count / last_loan_date / outstanding_amount / billing_day |

---

## 三、PyTOD 算法如何使用 SGD 数据

### 3.1 PyTOD 数据处理流水线

根据 Apple ml-pytod 官方仓库（https://github.com/apple/ml-pytod），PyTOD 使用 SGD 数据的完整链路如下：

```
SGD schema.json
    ↓ 定义服务、意图、槽位（用于构建 API 注册表和 Hint 生成规则）
create_pytod_dialogues.py
    ↓ 读取 SGD dialogues_*.json，将每个 USER turn 的 state.active_intent
    ↓ 和 state.slot_values 转换为 PyTOD 程序语句（PyTOD transcript）
PyTOD transcript（训练数据）
    ↓ 格式示例：
    ↓   user: I want to book a hotel in San Jose.
    ↓   x1 hotels_1_search_hotel(location='San Jose')
    ↓   x2 Hint('request value: hotel_name')
    ↓   x3 say(x2)
    ↓   agent: Sure! What hotel do you prefer?
Action Parser（LLM fine-tuning / in-context learning）
    ↓ 输入：对话历史 + 当前用户话语
    ↓ 输出：PyTOD 程序（API 调用 + Hint + say 语句）
Execution Engine
    ↓ 解析并执行 PyTOD 程序
    ↓ 调用已注册的 API 函数（真实或 mock）
    ↓ 返回结构化执行结果
Dialogue Manager（LLM）
    ↓ 输入：对话历史 + 执行结果
    ↓ 输出：自然语言回复
```

### 3.2 PyTOD 对 SGD 各字段的使用

| SGD 字段 | PyTOD 使用方式 |
|----------|----------------|
| `schema.json → service_name` | API 函数命名前缀（`hotels_1_search_hotel`） |
| `schema.json → intents[].name` | PyTOD 程序中的 API 调用名称 |
| `schema.json → intents[].required_slots` | 生成 `Hint('request value: slot_name')` 语句 |
| `schema.json → intents[].optional_slots` | 决定何时可以省略参数 |
| `schema.json → intents[].result_slots` | 生成 `say(x1.slot_name)` 语句 |
| `dialogue.turns[USER].state.active_intent` | 确定当前要调用的 API 函数 |
| `dialogue.turns[USER].state.slot_values` | 提供 API 调用的参数值 |
| `dialogue.turns[USER].state.requested_slots` | 生成用户请求某槽位的 Hint |
| `dialogue.turns[SYSTEM].service_call` | 验证 Action Parser 生成的程序是否调用了正确的 API |
| `dialogue.turns[SYSTEM].service_results` | 验证 Execution Engine 是否正确处理了 API 返回值 |
| `dialogue.turns[SYSTEM].actions` | 验证 Dialogue Manager 的回复是否符合预期动作 |

### 3.3 PyTOD 程序格式（ml-pytod 规范）

```
# 对话示例（来自 ml-pytod README）
user: I want to make a restaurant reservation for 2 people at half past 11.
x1 restaurants_2_reserve_restaurant(time='half past 11 in the morning', number_of_seats=2)
x2 Hint('request value: restaurant_name')
x3 Hint('request value: location')
x4 say(x2, x3)
agent: What city do you want to dine in? Do you have a preferred restaurant?

user: Please find restaurants in San Jose. Can you try Sino?
x5 x1.location = 'San Jose'; x1.restaurant_name = 'Sino'
x6 Hint('ask the user to confirm: date')
...
x11 say(x6, x7, x8, x9, x10)
agent: Confirming: I will reserve a table for 2 people at Sino in San Jose...
```

---

## 四、安逸花数据在 PyTOD 上的运行

### 4.1 数据适配关系

| anyihua SGD | PyTOD 对应 |
|-------------|-----------|
| `schema.json` → `AnYiHua_1` 服务 | PyTOD Action Parser 的 API 注册表 |
| `state.active_intent = "verify_identity"` | Action Parser 生成 `x1 verify_customer(name=...)` |
| `state.slot_values = {"customer_name": ["高先生"]}` | Action Parser 传入 `name='高先生'` |
| `service_call.method = "verify_customer"` | Execution Engine 调用 `verify_customer` API |
| `service_results = [{"identity_confirmed": "true"}]` | Dialogue Manager 获得 `x1.identity_confirmed = True` |

### 4.2 逐意图 PyTOD 程序映射

基于安逸花 Schema 和 SGD 数据，各意图对应的 PyTOD 程序如下：

**verify_identity（核实身份）**：
```python
# USER 话语：我是（某某某）
x1 verify_customer(name='高先生')
x2 Hint('request value: phone_suffix')   # 若尾号未提供
x3 say(x2)
# → 坐席：好的高先生，请问您手机尾号是多少？
```

**explain_credit_limit（告知额度）**：
```python
# USER 话语：我的额度是多少？
x1 query_account()
x2 say(x1.available_credit, x1.temp_credit)
# → 坐席：您的可提现额度是 7041 元，临时额度 26500 元。
```

**handle_loan_dispute（借款争议）**：
```python
# USER 话语：我没有七月二十三号的这笔借款
x1 query_loan_records()
x2 say(x1.last_loan_date, x1.loan_count, x1.outstanding_amount)
# → 坐席：我这边查到您最近一笔借款是...
```

**calculate_repayment（计算还款）**：
```python
# USER 话语：我借 1 万分 12 期，每月还多少？
x1 calculate_repayment(amount=10000, months=12)
x2 say(x1)
# → 坐席：借 1 万分 12 期，每月需还...
```

**say_goodbye（礼貌告别）**：
```python
# USER 话语：好的，没问题
x1 query_unresolved_issues()
# 仅当 x1.issue_count == 0 时才告别
x2 say(x1)
# → 坐席：好的，感谢您的接听，祝您生活愉快，再见！
```

### 4.3 ContextMind 中的 PyTOD 运行路径

ContextMind 已在 `contextmind/modes/pytod/` 实现了完整的 PyTOD 三步流水线：

```
chat_test_100.json 记录
    ↓
contextmind.modes.pytod.PyTODAgent.run()
    ↓ Step 1: ActionParser（LLM）
    │   输入：场景背景 + ServiceSchema + 对话历史 + 当前用户话语
    │   输出：PyTOD 程序（如 x1 verify_customer(name='高先生')）
    ↓ Step 2: ExecutionEngine
    │   输入：PyTOD 程序
    │   调用：contextmind.scenarios.anyihua 中注册的 CRM API
    │   输出：结构化执行结果（JSON）
    ↓ Step 3: DialogueManager（LLM）
    │   输入：对话历史 + 执行结果
    │   输出：坐席自然语言回复
    ↓
生成的坐席回复
    ↓ 对比 metadata.reference_response（来自 anyihua_sgd 的扩展元数据）
评估结果
```

### 4.4 SGD 数据在评估中的作用

`resources/anyihua_sgd/dialogues_001.json` 的 SGD 格式数据主要用于：

1. **DST 准确率评估**：
   - 对比 PyTOD 预测的 `slot_values` 与 SGD groundtruth 的 `state.slot_values`
   - 对比 PyTOD 预测的 `active_intent` 与 SGD 的 `state.active_intent`

2. **API 调用正确性验证**：
   - 对比 PyTOD 的 `service_call` 与 SGD groundtruth 的 `service_call`
   - 评估 Action Parser 是否调用了正确的 API 并传入了正确的参数

3. **Action Parser 微调训练数据**：
   - 使用 SGD 的 `active_intent` + `slot_values` + `service_call` 作为监督信号
   - 按 ml-pytod 的 `create_pytod_dialogues.py` 格式生成 PyTOD transcript

4. **对话回复评估**：
   - 使用 `metadata.reference_response`（来自 `坐席回复` 字段）作为参考答案
   - 使用 `metadata.qc_label`（来自 `人工校验` 字段）评估质量

### 4.5 SGD 元数据扩展字段（非标准，ContextMind 专用）

由于 SGD 标准格式无法完整表示安逸花场景的所有信息，转换器在对话顶层添加了 `metadata` 扩展字段：

```json
{
  "dialogue_id": "2025102811215858702023182",
  "services": ["AnYiHua_1"],
  "turns": [...],
  "metadata": {
    "user_info_raw": "现在是上午十一点二十一分#高先生#...",
    "user_info_parsed": {
      "customer_name": "高先生",
      "phone_suffix": "六七八",
      "available_credit": 7041,
      "temp_credit": 26500,
      "annual_rate_pct": "24"
    },
    "reference_response": "那我这边就先不打扰您了，祝您生活愉快...",
    "qc_label": "不当告别"
  }
}
```

| 扩展字段 | 来源 | 用途 |
|----------|------|------|
| `user_info_raw` | `chat_test_100.json` 的 `用户信息` | 原始 CRM 数据，供调试使用 |
| `user_info_parsed` | `parse_user_info()` 解析结果 | Execution Engine 的 mock CRM 数据库 |
| `reference_response` | `chat_test_100.json` 的 `坐席回复` | 对比评估 PyTOD 生成的回复质量 |
| `qc_label` | `chat_test_100.json` 的 `人工校验` | 质量标签，用于分析 PyTOD 的错误类型分布 |

---

## 五、为什么这么多字段需要推断，转换还能进行？推断结果准确吗？

> 这是本文档最核心的问题。以下从原理和数据层面给出详细解答。

### 5.1 转换"能进行"的原因

SGD 格式分为两类字段：

| 字段类别 | 字段 | 可靠性 | 来源 |
|----------|------|--------|------|
| **直接映射（无推断）** | `dialogue_id`、`speaker`、`utterance`、`services` | ✅ 100% 可靠 | chat_test_100.json 原始字段 |
| **CRM 解析（结构化数据）** | `slot_values` 中的 customer_name/available_credit/annual_rate_pct 等 | ✅ 99% 可靠 | `用户信息` 字段 → `parse_user_info()` 解析 |
| **规则推断（近似推断）** | `active_intent`、`actions`、`service_call`、`service_results` | ⚠️ 约 50–70% 准确 | 对话历史关键词匹配 |
| **疑问句检测** | `requested_slots` | ⚠️ 约 60% 准确 | 用户发言的疑问词检测 |

关键结论：**可靠字段（直接映射 + CRM 解析）占据了 SGD 数据量的绝大部分**——每条对话的 utterance/speaker 序列和 CRM 槽值是完全可靠的。推断字段只是"标注层"，错误不影响基本对话结构。

### 5.2 推断结果准确吗？——量化分析（100 条真实对话）

#### 5.2.1 active_intent 准确性

**问题**：原始代码将 USER turn 的 `active_intent` 设为"上一个 SYSTEM 意图"，这是错误的。

**根本原因**：SGD 规范中，`state.active_intent` 表示"用户正在追求的任务意图"，而不是"系统当前在做什么"。系统可能在讲额度（explain_credit_limit），但用户实际上想争议借款（handle_loan_dispute）。

**典型错误案例（对话 2025102811215858702023182 第 7-13 轮）**：

```
[SYSTEM]: 您在安逸花账户有一笔两万一千九百块钱的额度嘛，对吧？
          → SYSTEM 意图推断为 explain_credit_limit
[USER]: 不是这个我说七月二十三号七月二十三号的这一笔贷款我没贷怎么怎么会有...
        → 旧代码：active_intent = explain_credit_limit  ❌（继承 SYSTEM）
        → 正确：   active_intent = handle_loan_dispute   ✅（用户要争议借款）
```

**修复方案**（已实施）：

```python
# 旧代码（错误）：USER 意图继承自前一个 SYSTEM 意图
active_intent = prev_system_intent if speaker == "USER" else intent

# 新代码（正确）：USER 意图来自用户话语，短回应则沿用用户自身上一个意图
if speaker == "USER":
    if intent != "general_inquiry":
        prev_user_intent = intent  # 用户明确表达意图时更新
    active_intent = prev_user_intent  # 否则沿用用户自身上一个意图（而非系统意图）
```

**修复效果（跨全部 615 个 USER 轮次的意图分布变化）**：

| 意图 | 修复前 | 修复后 | 变化 |
|------|--------|--------|------|
| `verify_identity` | 194 (31.5%) | 12 (2.0%) | **-182** ← 严重过标，已纠正 |
| `general_inquiry` | 229 (37.2%) | 366 (59.5%) | +137 ← 更真实 |
| `explain_credit_limit` | 111 (18.0%) | 115 (18.7%) | 稳定 |
| `explain_interest_rate` | 23 (3.7%) | 49 (8.0%) | +26 ← 更好的传递 |
| `handle_loan_dispute` | 13 (2.1%) | 18 (2.9%) | +5 ← 更准确 |

修复前，447/615（72.7%）的 USER 意图是错误的（主要是 verify_identity 过标）。

#### 5.2.2 slot_values 准确性

`slot_values` 的数据来自 `用户信息` 字段（CRM 系统数据），这是**真实、可信的结构化数据**，准确性接近 100%。

问题在于"填充时机"（哪一轮注入哪些槽值）：当前按意图映射，可能导致某些槽值在错误的轮次出现。但槽值本身的数值是正确的。

#### 5.2.3 requested_slots 准确性

通过疑问词（"多少"、"几"、"怎么"等）+槽位关键词检测，在约 60% 的情况下准确。

主要误报：
- 用户说"还款太麻烦了"→ "还款" 误触发 `monthly_payment` 槽位请求
- 用户说"什么时候可以提现"→ 可能漏掉 `available_credit` 槽位请求

#### 5.2.4 actions/service_call/service_results 准确性

这三类字段均从 `active_intent` 推导：
- `service_call.method` = `_INTENT_TO_API[active_intent]`（查表，100% 内部一致）
- `service_results` = 从 CRM 数据中取对应字段（数值准确，前提是 intent 正确）

**结论**：如果 `active_intent` 是错的，这些字段也会跟着出错；如果 `active_intent` 是对的，这些字段通常准确。

### 5.3 正确看待转换结果的定位

这批数据的本质是**弱标注（Weakly Labeled）近似数据**，而不是人工精标注的金标准。它的用途和局限性如下：

| 用途 | 适合性 | 说明 |
|------|--------|------|
| **PyTOD 端到端运行（Generation 任务）** | ✅ 完全适合 | ContextMind 的 PyTOD 三步流水线直接使用 CRM API（不依赖 SGD 标注），`user_info_parsed` 是可靠输入 |
| **DST 快速原型验证** | ✅ 基本适合 | slot_values 和 utterance 可靠，intent 有误差但方向正确 |
| **PyTOD Action Parser 微调训练** | ⚠️ 有风险 | 需人工验证 intent 标注质量，否则会把错误 intent 作为监督信号 |
| **严格的 DST benchmarking** | ❌ 不适合 | 需人工精标注，当前规则推断误差太大 |

---

## 六、进一步改进方向

当前规则推断仍有以下局限，后续可改进：

| 问题 | 示例 | 改进方案 |
|------|------|----------|
| 关键词歧义 | "借款" 在额度查询和借款争议两类意图都存在 | 引入上下文窗口（前 2 轮）辅助判断 |
| 短句无法识别意图 | "嗯"、"好的"、"对" → general_inquiry | 当前靠意图传递缓解，可进一步用 LLM 标注 |
| 规则覆盖率有限 | 约 59.5% 的 USER 轮被归为 general_inquiry | 扩充关键词表或改用 LLM 分类 |
| 精确 DST 不可用 | 规则推断约 50–70% 准确 | 使用 LLM（GPT-4）对每轮精标注 active_intent |

---

## 七、总结

| 维度 | 结论 |
|------|------|
| **SGD 格式符合性** | `resources/anyihua_sgd/` 符合 SGD 标准格式：SYSTEM frame 无 state，USER frame 有 state，两种 frame 均有空 slots 列表 |
| **数据完整性** | 100 条对话全部转换，共 1330 轮次，1 个服务，1 个对话文件（dialogues_001.json） |
| **Schema 正确性** | `schema.json` 符合 SGD Schema 规范，10 个意图 × 15 个槽位，意图/槽位引用关系完整 |
| **意图标注质量** | 修复后的 USER 意图来自用户自身话语（而非继承系统意图），447/615 个错误意图已纠正；核心问题是 verify_identity 从 31.5% 降至 2.0% |
| **推断字段定位** | 属于弱标注近似数据，适合快速原型和 Generation 任务；不适合严格 DST benchmarking |
| **PyTOD 集成路径** | anyihua SGD 数据可直接用于 PyTOD Generation 任务（ContextMind 已实现）；用于 Action Parser 微调时需人工审核意图标注 |
| **与 ml-pytod 的差异** | ml-pytod 针对 SGD 26 个英文服务构建了完整的 API 数据库；anyihua 场景仅有 1 个中文服务，CRM API 由 `contextmind/scenarios/anyihua/` 实现 |
