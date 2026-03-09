# 安逸花外呼数据 → SGD 转换报告

- **数据文件**：`chat_test_100.json`（100 条对话，1230 轮，平均 12.3 轮/对话）
- **提取模型**：（历史数据，模型未记录）（LLM 成功率 0.0%，0/100 条）
- **本体来源**：`resources/anyihua_sgd/schema.json`（10 个意图，15 个槽位）

---

## 一、转换后 SGD 字段：具备哪些 / 缺少哪些

### ✅ 具备字段

| SGD 字段 | 质量 | 说明 |
|---|---|---|
| `dialogue_id` / `services` | 完整 | session_id 直接映射；services 固定为 AnYiHua_1 |
| `turns[].speaker` / `utterance` | 完整 | 原文直接保留，USER/SYSTEM 精确区分 |
| `metadata`（扩展字段） | 完整 | qc_label / reference_response / user_info_parsed（SGD 标准无此字段，为本项目扩展）|
| `frames[].service` | 完整 | 固定为 AnYiHua_1 |
| `frames[].state.slot_values`（CRM 槽位） | 金标准 | 11 个 CRM 槽位来自 parse_user_info()，覆盖率 32%–100% |
| `frames[].service_results` | 金标准 | CRM 数据按意图选取，可靠性 ≈100% |
| `frames[].service_call.method` | 高可靠 | intent→API 映射表自动生成 |
| `frames[].state.active_intent` | LLM 近似 | 成功率 0.0%；失败时兜底为 general_inquiry |
| `frames[].state.requested_slots` | LLM 近似 | 成功率 0.0%；失败时为空列表 |
| `frames[].state.slot_values`（对话专属槽位） | LLM 近似 | 4 个槽位（dispute_date / inquiry_amount / term_months / identity_confirmed）仅 LLM 可提取；失败时为空 |
| `frames[].actions` | LLM 近似 | 成功率 0.0%；失败时为空列表 |

### ❌ 缺少字段

| 缺失字段 | 原因 |
|---|---|
| `frames[].slots`（字符跨度标注） | 需标注工具手动标注字符级 start/exclusive_end 偏移量，LLM 无法自动生成 |
| `frames[].actions[].canonical_values` | 标准 SGD 要求规范化值，需额外后处理 |
| DST 金标准（完整 ground truth） | 需人工逐轮核验 LLM 标注结果 |

---

## 二、服务本体（Schema）

> 服务：`AnYiHua_1`　安逸花外呼促活服务。坐席代表安逸花/马上消费金融主动致电老用户，目标是激活用户闲置的借款额度。标准流程：核实身份 → 告知额度 → 解答疑问 → 引导借款 → 礼貌告别。

**意图列表**

| 意图 | 描述 | 必填槽位 | 结果槽位 |
|---|---|---|---|
| `verify_identity` | 开场身份核实：确认来电者是账户本人 | customer_name | identity_confirmed |
| `explain_credit_limit` | 告知额度情况（必须先调用 query_account API） | customer_name / available_credit | available_credit / temp_credit / temp_credit_status |
| `explain_interest_rate` | 解释利率和还款方式 | customer_name / annual_rate_pct | annual_rate_pct |
| `calculate_repayment` | 计算指定金额和期数的月还款额 | customer_name | — |
| `explain_displayed_amount` | 解释 APP 显示金额的构成 | customer_name / inquiry_amount | available_credit / temp_credit |
| `handle_loan_dispute` | 核实用户争议的借款记录 | customer_name / dispute_date | last_loan_date / loan_count / outstanding_amount |
| `guide_loan_operation` | 引导用户在 APP 完成借款操作 | customer_name | — |
| `escalate_to_human` | 转接人工客服 | customer_name | — |
| `say_goodbye` | 礼貌告别（必须先确认无未解决诉求） | customer_name | — |
| `general_inquiry` | 通用询问（无法精确匹配其他意图时的默认意图） | — | — |

**槽位列表**

| 槽位 | 描述 | 来源 | CRM 覆盖率 |
|---|---|---|---|
| `customer_name` | 客户姓名（如'高先生'、'杨女士'） | CRM | 100.0% |
| `phone_suffix` | 手机尾号（3–4 位数字，用于身份核实） | CRM | 100.0% |
| `dispute_date` | 用户质疑的借款日期（如'七月二十三号'） | 对话文本 | — |
| `inquiry_amount` | 用户询问或质疑的金额（元） | 对话文本 | — |
| `term_months` | 用户询问的分期期数（如 12） | 对话文本 | — |
| `identity_confirmed` | 身份是否已核实（由 verify_customer API 返回） | 对话文本 | — |
| `available_credit` | 当前实际可提现额度（元，由 query_account API 返回） | CRM | 99.0% |
| `temp_credit` | 临时额度上限（元） | CRM | 89.0% |
| `temp_credit_status` | 临时额度是否有效 | CRM | 32.0% |
| `temp_expiry_days` | 临时额度剩余有效天数 | CRM | 68.0% |
| `annual_rate_pct` | 年化利率（%） | CRM | 100.0% |
| `loan_count` | 当前未还清借款笔数 | CRM | 56.0% |
| `last_loan_date` | 最近一次借款日期（中文格式） | CRM | 95.0% |
| `outstanding_amount` | 当前未还款金额（元） | CRM | 52.0% |
| `billing_day` | 账单日（每月几号） | CRM | 100.0% |

---

## 三、数据统计

**质检标签分布**

- `无标签命中`：40 条（40.0%）
- `不当告别`：15 条（15.0%）
- `数据错误`：15 条（15.0%）
- `答非所问`：15 条（15.0%）
- `重复询问`：15 条（15.0%）

**意图频率分布（USER 轮，仅显示出现次数 > 0）**

| 意图 | 出现次数 | 占用户轮比例 |
|---|---|---|
| `general_inquiry` | 366 | 59.5% |
| `explain_credit_limit` | 115 | 18.7% |
| `explain_interest_rate` | 49 | 8.0% |
| `guide_loan_operation` | 32 | 5.2% |
| `handle_loan_dispute` | 18 | 2.9% |
| `explain_displayed_amount` | 15 | 2.4% |
| `verify_identity` | 12 | 2.0% |
| `escalate_to_human` | 6 | 1.0% |
| `calculate_repayment` | 2 | 0.3% |

**槽位覆盖率与提取次数**

| 槽位 | 来源 | CRM 覆盖率 | LLM 提取次数 |
|---|---|---|---|
| `customer_name` | CRM | 100.0% | 615 |
| `phone_suffix` | CRM | 100.0% | 615 |
| `dispute_date` | 对话文本 | — | 0 |
| `inquiry_amount` | 对话文本 | — | 0 |
| `term_months` | 对话文本 | — | 0 |
| `identity_confirmed` | 对话文本 | — | 0 |
| `available_credit` | CRM | 99.0% | 590 |
| `temp_credit` | CRM | 89.0% | 529 |
| `temp_credit_status` | CRM | 32.0% | 615 |
| `temp_expiry_days` | CRM | 68.0% | 412 |
| `annual_rate_pct` | CRM | 100.0% | 615 |
| `loan_count` | CRM | 56.0% | 387 |
| `last_loan_date` | CRM | 95.0% | 595 |
| `outstanding_amount` | CRM | 52.0% | 346 |
| `billing_day` | CRM | 100.0% | 615 |

**后端 API 调用次数（service_call）**

| API 方法 | 调用次数 |
|---|---|
| `query_account` | 129 |
| `calculate_repayment` | 44 |
| `query_loan_records` | 16 |
| `verify_customer` | 12 |

**对话行为（Act）分布（仅出现过的类型）**

| Act | 提取次数 |
|---|---|
| `INFORM` | 603 |
| `REQUEST` | 12 |

---

## 四、对话业务流程（从数据推导）

```
general_inquiry → explain_credit_limit → explain_displayed_amount → (guide_loan_operation | handle_loan_dispute | escalate_to_human) → explain_interest_rate
（入口意图 general_inquiry 占 99%；出口意图 general_inquiry 占 57%）
```

**高频意图转移（Top 10）**

| 从意图 | 转移到 | 次数 |
|---|---|---|
| `general_inquiry` | `explain_credit_limit` | 27 |
| `general_inquiry` | `guide_loan_operation` | 5 |
| `general_inquiry` | `explain_interest_rate` | 4 |
| `general_inquiry` | `explain_displayed_amount` | 3 |
| `guide_loan_operation` | `explain_credit_limit` | 3 |
| `general_inquiry` | `handle_loan_dispute` | 2 |
| `explain_displayed_amount` | `explain_interest_rate` | 2 |
| `explain_interest_rate` | `explain_displayed_amount` | 2 |
| `explain_credit_limit` | `explain_displayed_amount` | 2 |
| `explain_credit_limit` | `explain_interest_rate` | 2 |

---

## 五、提取方法说明

- **模型**：（历史数据，模型未记录）
- **方式**：LLM 逐轮结构化标注（每条对话整体输入，逐轮输出 active_intent / requested_slots / slot_values / actions / service_call）
- **CRM 数据**：通过 `parse_user_info()` 解析，直接注入 slot_values 和 service_results，可靠性 ≈100%
- **LLM 成功率**：0.0%（0/100 条）；失败时意图为 general_inquiry，动作/槽位为空
- **不使用**：关键词规则、正则匹配等规则方法，所有语义字段均由 LLM 推断
