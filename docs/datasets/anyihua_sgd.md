# 安逸花外呼 SGD 数据集说明

## 概述

本文档说明由 `examples/anyihua_knowledge_extraction_demo.py` 运行后生成的 **安逸花外呼 SGD 格式数据集**（目录 `data/anyihua_sgd/`）的完整结构与字段含义。

该数据集以 [Google SGD（Schema-Guided Dialogue）](https://github.com/google-research-datasets/dstc8-schema-guided-dialogue) 格式组织，将原始电话录音对话经 LLM 知识提取后转换为结构化、可用于任务型对话研究的数据集。

### 生成方式

```
原始电话对话 (chat_test_100.json)
        │
        ▼
AnyihuaKnowledgeExtractor（LLM 信息提取）
        │
        ▼
save_as_sgd()（SGD 格式转换器）
        │
        ▼
data/anyihua_sgd/
    ├── schema.json             ← 服务 Schema 定义
    ├── dialogues_001.json      ← 对话数据
    └── conversion_summary.json ← 转换统计
```

---

## 目录结构

```
data/anyihua_sgd/
├── schema.json             # 服务定义（槽位 + 意图）
├── dialogues_001.json      # 对话数据（每文件最多 1000 条，不足则只有一个文件）
├── dialogues_002.json      # 如对话数超过 1000 条则自动分文件
└── conversion_summary.json # 转换统计与覆盖率报告
```

---

## 文件说明

### 1. `schema.json`

定义本服务（`AnYiHua_1`）的所有槽位（slots）和意图（intents）。这是信息提取的**"词表"**——LLM 在开放模式下新发现的项目也会被合并进来。

#### 顶层结构

```json
[
  {
    "service_name": "AnYiHua_1",
    "description": "安逸花外呼促活服务。坐席代表安逸花/马上消费金融主动致电老用户……",
    "slots": [ ... ],
    "intents": [ ... ]
  }
]
```

> **注意**：文件是一个 JSON 数组，索引 0 为 `AnYiHua_1` 服务定义。

#### `slots` 字段

每个槽位的结构：

```json
{
  "name": "available_credit",
  "description": "当前实际可提现额度（元，由 query_account API 返回）",
  "is_categorical": false,
  "possible_values": []
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | `string` | 槽位名称（英文下划线命名），用于槽位标注和状态跟踪 |
| `description` | `string` | 槽位含义描述，提示 LLM 如何理解和识别该槽位 |
| `is_categorical` | `bool` | `true` = 枚举型（只能取 `possible_values` 中的值）；`false` = 自由文本型 |
| `possible_values` | `list[str]` | 枚举型槽位的合法取值列表；自由文本型为空数组 `[]` |

**当前预定义槽位（24 个）**：

| 槽位名 | 含义 | 类型 | 枚举值 |
|--------|------|------|--------|
| `customer_name` | 客户姓名（如"高先生"、"杨女士"） | 自由文本 | — |
| `phone_suffix` | 手机尾号（3–4 位数字，用于身份核实） | 自由文本 | — |
| `identity_confirmed` | 身份是否已核实（true / false） | 枚举 | `true`、`false` |
| `available_credit` | 当前实际可提现额度（元，由 query_account API 返回） | 自由文本 | — |
| `credit_limit` | 账户授信总额度（元） | 自由文本 | — |
| `temp_credit` | 临时额度上限（元） | 自由文本 | — |
| `temp_credit_status` | 临时额度是否有效（有效 / 已过期 / 无临时额度） | 枚举 | `有效`、`已过期`、`无临时额度` |
| `temp_credit_expiry_date` | 临时额度到期日期（如"十月二十六号"） | 自由文本 | — |
| `temp_expiry_days` | 临时额度剩余有效天数 | 自由文本 | — |
| `annual_rate_pct` | 年化利率（%，如 24 表示 24%） | 自由文本 | — |
| `daily_rate_pct` | 日利率（%，如 0.065 表示 0.065%） | 自由文本 | — |
| `monthly_payment` | 用户询问或坐席告知的月还款额（元） | 自由文本 | — |
| `total_interest` | 用户询问或坐席告知的总利息（元） | 自由文本 | — |
| `term_months` | 用户询问的分期期数（如 12） | 自由文本 | — |
| `billing_day` | 账单日（每月几号） | 自由文本 | — |
| `repayment_date` | 还款日（如"十一月一号"） | 自由文本 | — |
| `loan_count` | 当前未还清借款笔数 | 自由文本 | — |
| `last_loan_date` | 最近一次借款日期（中文格式） | 自由文本 | — |
| `outstanding_amount` | 当前未还款金额（元） | 自由文本 | — |
| `dispute_date` | 用户质疑的借款日期（如"七月二十三号"） | 自由文本 | — |
| `inquiry_amount` | 用户询问或质疑的金额（元） | 自由文本 | — |
| `overdue_days` | 逾期天数 | 自由文本 | — |
| `user_expected_interest` | 用户对合理利息的期望金额（元），如"一万块一年应该八九百" | 自由文本 | — |
| `user_complaint_reason` | 用户抱怨或拒绝的具体原因（如还款太麻烦、利率太高等） | 自由文本 | — |

#### `intents` 字段

每个意图的结构：

```json
{
  "name": "explain_credit_limit",
  "description": "【坐席】告知用户当前可提现额度及授信额度情况",
  "is_transactional": false,
  "required_slots": ["customer_name", "available_credit"],
  "optional_slots": {"credit_limit": "", "temp_credit": "", "temp_credit_status": "", "temp_expiry_days": ""},
  "result_slots": ["available_credit", "temp_credit", "temp_credit_status"]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | `string` | 意图名称（英文下划线命名） |
| `description` | `string` | 意图含义描述，含发起方角色（`【坐席】`/`【用户】`）和关键词 |
| `is_transactional` | `bool` | `true` = 事务性意图（调用 API 后状态不可逆，如转接人工）；`false` = 信息性意图 |
| `required_slots` | `list[str]` | 执行该意图必须提供的槽位名 |
| `optional_slots` | `dict[str, str]` | 可选槽位及其默认值（空字符串表示无默认） |
| `result_slots` | `list[str]` | 该意图成功执行后会返回的槽位（来自 API 结果） |

**当前预定义意图（21 个）**：

| 意图名 | 含义简述 | 事务性 | 必填槽位 |
|--------|---------|--------|---------|
| `verify_identity` | 【坐席】开场身份核实 | ❌ | `customer_name` |
| `explain_credit_limit` | 【坐席】告知额度情况 | ❌ | `customer_name`, `available_credit` |
| `explain_interest_rate` | 【坐席】解释利率和还款方式 | ❌ | `customer_name`, `annual_rate_pct` |
| `calculate_repayment` | 【坐席】计算月还款额及总利息 | ❌ | `customer_name` |
| `explain_displayed_amount` | 【坐席】解释 APP 显示金额 | ❌ | `customer_name`, `inquiry_amount` |
| `handle_loan_dispute` | 【坐席】核实争议借款记录 | ❌ | `customer_name`, `dispute_date` |
| `guide_loan_operation` | 【坐席】引导 APP 借款操作 | ❌ | `customer_name` |
| `promote_loan_offer` | 【坐席】推介借款优惠 | ❌ | `customer_name` |
| `explain_temp_credit` | 【坐席】解释临时额度规则 | ❌ | `customer_name`, `temp_credit` |
| `escalate_to_human` | 【坐席/用户】转接人工客服 | ✅ | `customer_name` |
| `say_goodbye` | 【坐席/用户】礼貌告别 | ❌ | `customer_name` |
| `complain_repayment` | 【用户】抱怨还款太麻烦或月供太高 | ❌ | 无 |
| `complain_interest_rate` | 【用户】质疑利率偏高 | ❌ | 无 |
| `express_interest_expectation` | 【用户】表达对合理利息的期望 | ❌ | 无 |
| `confirm_information` | 【用户】确认坐席信息 | ❌ | 无 |
| `reject_offer` | 【用户】明确拒绝借款方案 | ❌ | 无 |
| `ask_for_clarification` | 【用户】要求进一步解释 | ❌ | 无 |
| `dispute_loan_record` | 【用户】质疑某笔借款记录 | ❌ | 无 |
| `inquire_repayment_method` | 【用户】询问还款方式 | ❌ | 无 |
| `express_hesitation` | 【用户】表示犹豫或需要考虑 | ❌ | 无 |
| `general_inquiry` | 【用户·兜底】无法归类时的默认意图 | ❌ | 无 |

---

### 2. `dialogues_001.json`（对话数据文件）

包含所有转换后的结构化对话，格式为 JSON 数组，每个元素是一条完整对话。

#### 单条对话顶层结构

```json
{
  "dialogue_id": "2025102811215858702023182",
  "services": ["AnYiHua_1"],
  "metadata": {
    "qc_label":           "无问题",
    "reference_response": "您好，感谢您的配合……",
    "user_info_raw":      "高先生|13801234678|额度20000……",
    "user_info_parsed":   {
      "name": "高先生",
      "phone": "13801234678",
      "credit": 20000
    }
  },
  "turns": [ ... ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `dialogue_id` | `string` | 原始对话的唯一 ID（来自 `chat_test_100.json`）|
| `services` | `list[str]` | 本次对话涉及的服务列表，固定为 `["AnYiHua_1"]` |
| `metadata` | `dict` | 原始附加信息（仅原始数据中存在时才有） |
| `metadata.qc_label` | `string` | 人工质检标签 |
| `metadata.reference_response` | `string` | 坐席参考回复脚本 |
| `metadata.user_info_raw` | `string` | 原始 CRM 用户信息字符串 |
| `metadata.user_info_parsed` | `dict` | 结构化 CRM 用户信息（parse_user_info 解析结果） |
| `turns` | `list` | 对话轮次列表，按时间顺序排列 |

#### `turns` 中每个轮次的结构

```json
{
  "speaker": "USER",
  "utterance": "利息有点高啊。",
  "frames": [ ... ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `speaker` | `string` | 发言者：`"SYSTEM"`（坐席）或 `"USER"`（用户） |
| `utterance` | `string` | 话语原文 |
| `frames` | `list` | 该轮次的结构化标注帧（每个涉及服务一个帧） |

#### `frames` 中每个帧的结构

**USER 轮次的帧**（含 `state`）：

```json
{
  "service": "AnYiHua_1",
  "slots": [],
  "state": {
    "active_intent": "complain_interest_rate",
    "requested_slots": [],
    "slot_values": {
      "customer_name": ["高先生"],
      "annual_rate_pct": ["24"]
    }
  },
  "actions": [
    {
      "act": "INFORM",
      "slot": "annual_rate_pct",
      "values": ["24"],
      "canonical_values": ["24"]
    }
  ]
}
```

**SYSTEM 轮次的帧**（含 `service_call` 和 `service_results`）：

```json
{
  "service": "AnYiHua_1",
  "slots": [],
  "actions": [
    {
      "act": "INFORM",
      "slot": "annual_rate_pct",
      "values": ["24"],
      "canonical_values": ["24"]
    }
  ],
  "service_call": {
    "method": "explain_interest_rate",
    "parameters": {
      "customer_name": "高先生",
      "annual_rate_pct": "24"
    }
  },
  "service_results": [
    {
      "customer_name": "高先生",
      "phone_suffix": "678",
      "available_credit": "20000"
    }
  ]
}
```

**帧字段说明**：

| 字段 | USER 轮 | SYSTEM 轮 | 说明 |
|------|---------|----------|------|
| `service` | ✅ | ✅ | 当前帧对应的服务名，固定为 `"AnYiHua_1"` |
| `slots` | ✅（通常为 `[]`）| ✅（通常为 `[]`）| 话语中槽位的字符级跨度标注（标准 SGD 中用到，本数据集暂未填充）|
| `state` | ✅ | ❌（不存在）| 对话当前累积状态（见下表）|
| `actions` | ✅ | ✅ | 对话行为标注列表 |
| `service_call` | ❌ | ✅（可为 `null`）| 本轮坐席实际调用的 API 名称和参数 |
| `service_results` | ❌ | ✅（可为 `[]`）| API 返回的结果数据（来自 CRM 解析）|

**`state` 字段（USER 轮专有）**：

| 子字段 | 类型 | 说明 |
|--------|------|------|
| `active_intent` | `string` | 本轮用户的主要意图名（来自 LLM 提取，未识别时默认 `"general_inquiry"`） |
| `requested_slots` | `list[str]` | 用户明确请求坐席提供的槽位（本数据集暂为空）|
| `slot_values` | `dict[str, list[str]]` | 累积槽位状态：本轮及所有之前轮次中已识别的槽位及其值列表 |

**`actions` 中每个动作的结构**：

| 字段 | 说明 |
|------|------|
| `act` | 对话行为类型（如 `"INFORM"`, `"REQUEST"`, `"OFFER"`, `"CONFIRM"`） |
| `slot` | 涉及的槽位名（无槽位时为空字符串 `""`） |
| `values` | 槽位值的原始表述 |
| `canonical_values` | 槽位值的规范化表述（本数据集与 `values` 相同）|

**`service_call` 字段（SYSTEM 轮专有）**：

| 子字段 | 说明 |
|--------|------|
| `method` | 调用的 API 方法名（对应 `schema.json` 中意图名，经 intent → method 映射）|
| `parameters` | 调用参数（当前已知槽位值的快照）|

---

### 3. `conversion_summary.json`

记录本次转换的统计信息和 Schema 覆盖率报告。

```json
{
  "output_dir": "data/anyihua_sgd",
  "dialogues": 100,
  "turns": 1330,
  "failed": 0,
  "dialogue_files": 1,
  "services": ["AnYiHua_1"],
  "converted_at": "2025-10-28T11:21:58.123456",
  "discovered_schema_items": 0,
  "schema_coverage": {
    "extracted_slots": ["customer_name", "annual_rate_pct", ...],
    "extracted_intents": ["verify_identity", "complain_interest_rate", ...],
    "schema_slots": ["customer_name", "phone_suffix", ...],
    "schema_intents": ["verify_identity", "explain_credit_limit", ...],
    "uncovered_slots": [],
    "uncovered_intents": [],
    "slot_coverage_pct": 100.0,
    "intent_coverage_pct": 100.0,
    "note": "所有提取结果中出现的槽位和意图均已在 schema.json 中预定义，无需开放模式新增。"
  }
}
```

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `output_dir` | `string` | 输出目录路径 |
| `dialogues` | `int` | 成功转换的对话总数 |
| `turns` | `int` | 转换后的对话轮次总数 |
| `failed` | `int` | 转换失败的对话数（异常抛出） |
| `dialogue_files` | `int` | 生成的 `dialogues_*.json` 文件数量 |
| `services` | `list[str]` | 涉及的服务列表 |
| `converted_at` | `string` | 转换完成时间（ISO 8601 格式）|
| `discovered_schema_items` | `int` | 开放模式下 LLM 新发现并合并进 schema 的槽位/意图数量；0 表示完全由预定义覆盖 |
| `schema_coverage` | `dict` | Schema 覆盖率分析（见下表）|

**`schema_coverage` 子字段**：

| 子字段 | 类型 | 说明 |
|--------|------|------|
| `extracted_slots` | `list[str]` | 所有提取结果中实际出现过的槽位名（去重后排序）|
| `extracted_intents` | `list[str]` | 所有提取结果中实际出现过的意图名（去重后排序）|
| `schema_slots` | `list[str]` | `schema.json` 中预定义的槽位名列表 |
| `schema_intents` | `list[str]` | `schema.json` 中预定义的意图名列表 |
| `uncovered_slots` | `list[str]` | 提取结果中出现但 **未在 schema 中预定义** 的槽位名 |
| `uncovered_intents` | `list[str]` | 提取结果中出现但 **未在 schema 中预定义** 的意图名 |
| `slot_coverage_pct` | `float` | 槽位覆盖率（%）= 提取槽位中被 schema 覆盖的比例 |
| `intent_coverage_pct` | `float` | 意图覆盖率（%）= 提取意图中被 schema 覆盖的比例 |
| `note` | `string` | 覆盖率人类可读摘要 |

> **理想状态**：`uncovered_slots` 和 `uncovered_intents` 均为空列表，`slot_coverage_pct` 和 `intent_coverage_pct` 均为 `100.0`，表示 schema 预定义完全覆盖了实际信息提取所需的所有标签，无需开放模式补充。

---

## Schema 设计原则

1. **单一来源（Single Source of Truth）**：`schema.json` 的内容由代码中的 `_default_schema()` 函数生成，不依赖外部静态文件。每次运行 `save_as_sgd()` 时都从 `_default_schema()` 出发，确保 schema 版本与代码同步。

2. **预定义优先，开放模式补充**：`_default_schema()` 中预定义了 24 个槽位和 21 个意图，覆盖安逸花外呼的常见业务场景。若设置了 `--slot-open-ended` 或 `--intent-open-ended`，LLM 新发现的项目会被合并追加，但不会覆盖已有预定义。

3. **角色标注**：每个意图的 `description` 均包含发起方角色前缀（`【坐席】`、`【用户】`、`【坐席/用户】`），帮助 LLM 区分"坐席主导"和"用户主导"的意图。

4. **兜底意图**：`general_inquiry` 作为最后兜底，LLM 在无法归类时使用，降低"幻觉意图"出现的概率。

---

## 相关源文件

| 文件 | 说明 |
|------|------|
| `contextmind/scenarios/anyihua/knowledge_extraction/sgd_converter.py` | SGD 格式转换器主体，含 `save_as_sgd()` 和 `_default_schema()` |
| `contextmind/scenarios/anyihua/knowledge_extraction/extractor.py` | LLM 知识提取器，输出 `ExtractionResult` |
| `examples/anyihua_knowledge_extraction_demo.py` | 端到端演示脚本 |
| `data/anyihua_sgd/` | 生成的数据集输出目录 |
