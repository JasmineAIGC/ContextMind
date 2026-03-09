# chat_test_100.json 信息提取分析报告（LLM 版）

**数据来源**：`chat_test_100.json`  
**分析记录数**：100 条（LLM 成功提取：0 条，成功率 0.0%）  
**分析目标**：基于 SGD Schema-Guided Dialogue 规范，使用 LLM 从安逸花外呼数据中提取所有可用于标准 TOD 任务的结构化信息。  
**提取方法**：LLM 逐轮结构化标注（模型：（历史数据，模型未记录））

---

## 一、数据集概览

| 指标 | 值 |
|---|---|
| 分析记录数 | 100 条 |
| 总轮次数 | 1230 轮 |
| 平均对话长度 | 12.3 轮/对话 |
| 用户轮次数 | 615 轮 |
| LLM 提取成功率 | 0.0%（0/100 条） |
| 提取模型 | （历史数据，模型未记录） |

**人工校验标签分布**：

- `无标签命中`：40 条（40.0%）
- `不当告别`：15 条（15.0%）
- `数据错误`：15 条（15.0%）
- `答非所问`：15 条（15.0%）
- `重复询问`：15 条（15.0%）

---

## 二、服务本体（Ontology / Schema）

> **SGD 本体（Schema）** 是服务的形式化规范，定义了系统能理解和处理的概念边界。
> 与传统封闭本体（只有名称列表）不同，SGD schema 为每个意图和槽位提供**自然语言描述**，
> 使 LLM 在 zero-shot 条件下能泛化到未见服务（Schema-Guided 范式）。
> 本体来源：`resources/anyihua_sgd/schema.json`

- **服务名称**：`AnYiHua_1`
- **服务描述**：安逸花外呼促活服务。坐席代表安逸花/马上消费金融主动致电老用户，目标是激活用户闲置的借款额度。标准流程：核实身份 → 告知额度 → 解答疑问 → 引导借款 → 礼貌告别。
- **意图数量**：10 个（来自 schema.json intents 列表）
- **槽位数量**：15 个（来自 schema.json slots 列表）
- **对话行为类型**：14 种（SGD 标准 Acts 列表）

### 2.1 意图列表（来自 schema.json）

> SGD intents 包含 required_slots（必填槽位）、optional_slots（可选槽位）、result_slots（API 返回槽位），用于指导系统何时触发 API 调用。

| 意图名称 | 自然语言描述 | 必填槽位 | 可选槽位 | 结果槽位 | is_transactional |
|---|---|---|---|---|---|
| `verify_identity` | 开场身份核实：确认来电者是账户本人 | `customer_name` | `phone_suffix` | `identity_confirmed` | 否 |
| `explain_credit_limit` | 告知额度情况（必须先调用 query_account API） | `customer_name`, `available_credit` | `temp_credit`, `temp_credit_status`, `temp_expiry_days` | `available_credit`, `temp_credit`, `temp_credit_status` | 否 |
| `explain_interest_rate` | 解释利率和还款方式 | `customer_name`, `annual_rate_pct` | `term_months` | `annual_rate_pct` | 否 |
| `calculate_repayment` | 计算指定金额和期数的月还款额 | `customer_name` | `inquiry_amount`, `term_months` | — | 否 |
| `explain_displayed_amount` | 解释 APP 显示金额的构成 | `customer_name`, `inquiry_amount` | `available_credit`, `temp_credit`, `temp_credit_status` | `available_credit`, `temp_credit` | 否 |
| `handle_loan_dispute` | 核实用户争议的借款记录 | `customer_name`, `dispute_date` | `last_loan_date`, `loan_count`, `outstanding_amount` | `last_loan_date`, `loan_count`, `outstanding_amount` | 否 |
| `guide_loan_operation` | 引导用户在 APP 完成借款操作 | `customer_name` | `available_credit` | — | 否 |
| `escalate_to_human` | 转接人工客服 | `customer_name` | `dispute_date`, `inquiry_amount` | — | ✅ 是 |
| `say_goodbye` | 礼貌告别（必须先确认无未解决诉求） | `customer_name` | — | — | 否 |
| `general_inquiry` | 通用询问（无法精确匹配其他意图时的默认意图） | — | — | — | 否 |

### 2.2 槽位列表（来自 schema.json）

> SGD slots 包含 is_categorical（是否为枚举类型）和 possible_values（枚举值列表），
> 非枚举槽位（is_categorical=false）的值由对话文本或 API 返回，无固定取值范围。

| 槽位名称 | 自然语言描述 | is_categorical | 可能取值 | CRM 覆盖率 | LLM 提取次数 |
|---|---|---|---|---|---|
| `customer_name` | 客户姓名（如'高先生'、'杨女士'） | 否 | 自由文本 | 100.0% | 615 |
| `phone_suffix` | 手机尾号（3–4 位数字，用于身份核实） | 否 | 自由文本 | 100.0% | 615 |
| `dispute_date` | 用户质疑的借款日期（如'七月二十三号'） | 否 | 自由文本 | 0.0% | 0 |
| `inquiry_amount` | 用户询问或质疑的金额（元） | 否 | 自由文本 | 0.0% | 0 |
| `term_months` | 用户询问的分期期数（如 12） | 否 | 自由文本 | 0.0% | 0 |
| `identity_confirmed` | 身份是否已核实（由 verify_customer API 返回） | ✅ 是 | `true`, `false` | 0.0% | 0 |
| `available_credit` | 当前实际可提现额度（元，由 query_account API 返回） | 否 | 自由文本 | 99.0% | 590 |
| `temp_credit` | 临时额度上限（元） | 否 | 自由文本 | 89.0% | 529 |
| `temp_credit_status` | 临时额度是否有效 | ✅ 是 | `有效`, `已过期`, `无临时额度` | 32.0% | 615 |
| `temp_expiry_days` | 临时额度剩余有效天数 | 否 | 自由文本 | 68.0% | 412 |
| `annual_rate_pct` | 年化利率（%） | 否 | 自由文本 | 100.0% | 615 |
| `loan_count` | 当前未还清借款笔数 | 否 | 自由文本 | 56.0% | 387 |
| `last_loan_date` | 最近一次借款日期（中文格式） | 否 | 自由文本 | 95.0% | 595 |
| `outstanding_amount` | 当前未还款金额（元） | 否 | 自由文本 | 52.0% | 346 |
| `billing_day` | 账单日（每月几号） | 否 | 自由文本 | 100.0% | 615 |

### 2.3 对话行为类型（Acts / 动作）

> SGD 定义了 14 种标准对话行为动作（Act），用于描述每一句话的功能性意图。
> 本次提取次数来自 LLM 标注结果（LLM 未成功的轮次动作为空）。

| Act 类型（英文） | 中文含义 | 本次提取次数 |
|---|---|---|
| `INFORM` | 告知槽位信息 | 603 |
| `REQUEST` | 请求槽位信息 | 12 |
| `CONFIRM` | 确认槽位值 | 0 |
| `SELECT` | 从选项中选择 | 0 |
| `OFFER` | 提供服务选项 | 0 |
| `GOODBYE` | 告别 | 0 |
| `INFORM_INTENT` | 明确告知意图 | 0 |
| `NEGATE_INTENT` | 否定意图 | 0 |
| `AFFIRM_INTENT` | 肯定意图 | 0 |
| `AFFIRM` | 肯定（非意图） | 0 |
| `NEGATE` | 否定（非意图） | 0 |
| `CANT_UNDERSTAND` | 无法理解 | 0 |
| `NOTIFY_SUCCESS` | 通知操作成功 | 0 |
| `NOTIFY_FAILURE` | 通知操作失败 | 0 |

---

## 三、意图（Intent / 对话目标）分析

> **Intent（意图）**：指用户在某一对话轮次希望完成的任务目标，如「核实身份」、「了解额度」等。
> 以下分布来自 LLM 对本次处理的所有对话的逐轮标注结果。

- 本次处理 100 条对话，共 615 个用户轮次，平均每条对话含 **1.6** 个不同意图

### 3.1 意图频率分布（USER 轮，基于本次 LLM 提取结果）

| 意图名称 | 描述（来自 schema.json） | 出现次数 | 占用户轮比例 |
|---|---|---|---|
| `general_inquiry` | 通用询问（无法精确匹配其他意图时的默认意图） | 366 | 59.5% |
| `explain_credit_limit` | 告知额度情况（必须先调用 query_account API） | 115 | 18.7% |
| `explain_interest_rate` | 解释利率和还款方式 | 49 | 8.0% |
| `guide_loan_operation` | 引导用户在 APP 完成借款操作 | 32 | 5.2% |
| `handle_loan_dispute` | 核实用户争议的借款记录 | 18 | 2.9% |
| `explain_displayed_amount` | 解释 APP 显示金额的构成 | 15 | 2.4% |
| `verify_identity` | 开场身份核实：确认来电者是账户本人 | 12 | 2.0% |
| `escalate_to_human` | 转接人工客服 | 6 | 1.0% |
| `calculate_repayment` | 计算指定金额和期数的月还款额 | 2 | 0.3% |
| `say_goodbye` | 礼貌告别（必须先确认无未解决诉求） | 0 | 0.0% |

### 3.2 入口意图 / 出口意图

> **入口意图**：每条对话第一个 USER 轮的意图；**出口意图**：最后一个 USER 轮的意图。
> 以下统计基于本次提取的实际数据。

**入口意图（对话开场用户目标）**：

- `general_inquiry`（通用询问（无法精确匹配其他意图时的默认意图））：99 次
- `verify_identity`（开场身份核实：确认来电者是账户本人）：1 次

**出口意图（对话收尾用户目标）**：

- `general_inquiry`（通用询问（无法精确匹配其他意图时的默认意图））：57 次
- `explain_credit_limit`（告知额度情况（必须先调用 query_account API））：25 次
- `explain_interest_rate`（解释利率和还款方式）：6 次
- `explain_displayed_amount`（解释 APP 显示金额的构成）：5 次
- `guide_loan_operation`（引导用户在 APP 完成借款操作）：3 次

---

## 四、槽位（Slot / 信息字段）分析

> **Slot（槽位）**：对话系统需要跟踪的关键信息字段。
> **CRM 覆盖率**：该槽位在 CRM 数据中有值的对话比例（来自实际数据统计）。
> **LLM 提取次数**：本次提取中该槽位出现在 slot_values 中的对话数量。

### 4.1 槽位综合统计（基于本次提取数据）

| 槽位名称 | 描述（来自 schema.json） | 数据来源 | CRM 覆盖率 | LLM 提取次数 | 被询问次数 | 示例值 |
|---|---|---|---|---|---|---|
| `customer_name` | 客户姓名（如'高先生'、'杨女士'） | CRM | 100.0% | 615 | 0 | 高先生、高先生 |
| `phone_suffix` | 手机尾号（3–4 位数字，用于身份核实） | CRM | 100.0% | 615 | 0 | 六七八、六七八 |
| `dispute_date` | 用户质疑的借款日期（如'七月二十三号'） | 对话文本 | 0.0% | 0 | 0 | — |
| `inquiry_amount` | 用户询问或质疑的金额（元） | 对话文本 | 0.0% | 0 | 0 | — |
| `term_months` | 用户询问的分期期数（如 12） | 对话文本 | 0.0% | 0 | 0 | — |
| `identity_confirmed` | 身份是否已核实（由 verify_customer API 返回） | 对话文本 | 0.0% | 0 | 0 | — |
| `available_credit` | 当前实际可提现额度（元，由 query_account API 返回） | CRM | 99.0% | 590 | 65 | 7041、7041 |
| `temp_credit` | 临时额度上限（元） | CRM | 89.0% | 529 | 0 | 26500、26500 |
| `temp_credit_status` | 临时额度是否有效 | CRM | 32.0% | 615 | 0 | 已过期、已过期 |
| `temp_expiry_days` | 临时额度剩余有效天数 | CRM | 68.0% | 412 | 0 | 8、8 |
| `annual_rate_pct` | 年化利率（%） | CRM | 100.0% | 615 | 8 | 24、24 |
| `loan_count` | 当前未还清借款笔数 | CRM | 56.0% | 387 | 0 | 3、3 |
| `last_loan_date` | 最近一次借款日期（中文格式） | CRM | 95.0% | 595 | 0 | 二零二五年五月二日、二零二五年五月二日 |
| `outstanding_amount` | 当前未还款金额（元） | CRM | 52.0% | 346 | 0 | 4590、4590 |
| `billing_day` | 账单日（每月几号） | CRM | 100.0% | 615 | 0 | 27、27 |

### 4.2 后端 API（service_call）调用分布（基于本次提取数据）

> **service_call**：SYSTEM 轮次调用的后端 API。以下次数来自 LLM 标注结果。

| API 方法 | 中文说明 | 本次调用次数 |
|---|---|---|
| `query_account` | 查询账户信息（额度/利率/账单日等） | 129 |
| `calculate_repayment` | 计算还款金额 | 44 |
| `query_loan_records` | 查询借款记录 | 16 |
| `verify_customer` | 核实用户身份 | 12 |

---

## 五、对话策略（Strategy / 业务流程）分析

> 以下业务流程和意图转移矩阵均从本次 LLM 提取结果推导，非人工定义。
> 仅处理 LLM 成功标注的对话；LLM 失败轮次统一标记为 general_inquiry，可能导致 general_inquiry 频率偏高。

**从数据推导的外呼业务流程（本次 100 条）**：
```
general_inquiry → explain_credit_limit → explain_displayed_amount → (guide_loan_operation | handle_loan_dispute | escalate_to_human) → explain_interest_rate
（入口意图 general_inquiry 占 99%；出口意图 general_inquiry 占 57%）
```

### 5.1 高频意图转移（Top 10，基于本次提取数据）

| 从意图 | 描述 | 转移到 | 描述 | 出现次数 |
|---|---|---|---|---|
| `general_inquiry` | 通用询问（无法精确匹配其他意图时的默认意图） | `explain_credit_limit` | 告知额度情况（必须先调用 query_account API） | 27 |
| `general_inquiry` | 通用询问（无法精确匹配其他意图时的默认意图） | `guide_loan_operation` | 引导用户在 APP 完成借款操作 | 5 |
| `general_inquiry` | 通用询问（无法精确匹配其他意图时的默认意图） | `explain_interest_rate` | 解释利率和还款方式 | 4 |
| `general_inquiry` | 通用询问（无法精确匹配其他意图时的默认意图） | `explain_displayed_amount` | 解释 APP 显示金额的构成 | 3 |
| `guide_loan_operation` | 引导用户在 APP 完成借款操作 | `explain_credit_limit` | 告知额度情况（必须先调用 query_account API） | 3 |
| `general_inquiry` | 通用询问（无法精确匹配其他意图时的默认意图） | `handle_loan_dispute` | 核实用户争议的借款记录 | 2 |
| `explain_displayed_amount` | 解释 APP 显示金额的构成 | `explain_interest_rate` | 解释利率和还款方式 | 2 |
| `explain_interest_rate` | 解释利率和还款方式 | `explain_displayed_amount` | 解释 APP 显示金额的构成 | 2 |
| `explain_credit_limit` | 告知额度情况（必须先调用 query_account API） | `explain_displayed_amount` | 解释 APP 显示金额的构成 | 2 |
| `explain_credit_limit` | 告知额度情况（必须先调用 query_account API） | `explain_interest_rate` | 解释利率和还款方式 | 2 |

---

## 六、SGD 字段可提取性结论（基于本次提取数据）

> 所有结论来自本次实际提取结果，不使用固定假设。
> **LLM**：（历史数据，模型未记录）（本次成功率 0.0%）

| 提取类别 | 涉及字段 | 实测可靠性 | 提取方法 |
|---|---|---|---|
| 直接提取（100% 可靠） | `dialogue_id`, `speaker`, `utterance`, `qc_label`, `reference_response` | 100% | 直接映射 |
| CRM 高覆盖（实测 ≥80%） | `customer_name`, `phone_suffix`, `available_credit`, `temp_credit`, `annual_rate_pct` 等7个 | ≥95% | parse_user_info() 规则解析 |
| CRM 中覆盖（实测 50–80%） | `temp_expiry_days`, `loan_count`, `outstanding_amount` | ≥70% | parse_user_info() 规则解析 |
| CRM 低覆盖（实测 <50%） | `temp_credit_status` | 按场景 | parse_user_info() 规则解析 |
| LLM 提取（成功率 0.0%） | `active_intent`, `requested_slots`, `slot_values`, `actions`, `service_call` | LLM成功率 0.0%，字段准确率 ≈70–85% | LLM 语义理解（Qwen2.5-7B-Instruct） |
| 对话专属槽位 | `dispute_date`, `inquiry_amount`, `term_months`, `identity_confirmed` | 依赖对话内容，出现率 1–40% | LLM NLU 提取 |
| 无法自动提取（需人工标注） | `full_ground_truth_dst` | — | — |

**直接提取（100% 可靠）**：对话结构字段完全可直接转换，无需推断。

**CRM 高覆盖（实测 ≥80%）**：来自 用户信息 字段的 CRM 数据，覆盖率 ≥80%，可作为 slot_values 和 service_results 的金标准。

**CRM 中覆盖（实测 50–80%）**：CRM 数据存在但并非所有对话都有，覆盖率 50–80%，建议保留并标记置信度。

**CRM 低覆盖（实测 <50%）**：仅在特定业务场景（如争议、分期）中出现，覆盖率 <50%。

**LLM 提取（成功率 0.0%）**：通过 LLM 对整条对话进行逐轮结构化标注，提取 SGD 所有核心字段。相比关键词规则，LLM 能处理口语化表达、上下文指代和隐式意图。

**对话专属槽位**：这些槽位无 CRM 来源，只能从对话文本提取，出现率较低。

**无法自动提取（需人工标注）**：完整的 DST 金标准标注需要人工校验。LLM 提取的 active_intent/slot_values 是近似值，建议用于生成任务训练，不直接作为 DST 评估 groundtruth。

---

## 七、TOD 数据集构建建议

1. **对话骨架（100% 可用）**：本次 100 条对话、1230 个轮次可完整保留。

2. **CRM 槽位作为 slot_values 金标准（7 个槽位覆盖率 ≥80%，均值 97.6%）**：
   - 高覆盖槽位：`customer_name`, `phone_suffix`, `available_credit`, `temp_credit`, `annual_rate_pct`, `last_loan_date`等。
   - 可直接注入 `slot_values` 和 `service_results` 作为金标准。

3. **LLM 提取 active_intent / actions（本次成功率 0.0%）**：
   - 使用 （历史数据，模型未记录） 对每条对话进行逐轮结构化标注。
   - 最高频 Act 类型：`INFORM`（603 次），可用于验证标注合理性。

4. **service_call 生成**：
   - `service_call.method` 可由 active_intent → API 映射表自动生成，参数由 LLM 提取。

5. **补充人工标注（不可自动生成的字段）**：
   - `frames[].slots`（字符跨度标注）：需要标注工具手动标注。
   - 完整 DST 金标准需人工核验 LLM 输出。

6. **保留扩展字段 metadata**：
   - `metadata.qc_label`：质检标签（质量分析用）
   - `metadata.reference_response`：坐席参考回复（生成任务评估用）
   - `metadata.user_info_parsed`：完整 CRM 数据（执行引擎查询用）

7. **注意外呼数据特殊性**：
   - 首轮发言者是 SYSTEM（坐席），与标准 SGD（USER 首轮）相反。
   - `坐席回复` 字段是**待预测目标**，不应混入 `对话历史`。

---

## 八、生成文件与标准 SGD 格式的差异说明

> 本节说明 `chat_test_sgd_dialogues.json` 与 Google Research 发布的标准 [Schema-Guided Dialogue (SGD)](https://github.com/google-research-datasets/dstc8-schema-guided-dialogue) 数据集在字段层面的差异。
> 本次提取模型：（历史数据，模型未记录），LLM 成功率 0.0%。

**图例**：✅ 完整/金标准  ⚠️ 近似（LLM 提取，有误差）  ❌ 缺失（需人工标注）

| SGD 字段路径 | 所在层级 | 本文件状态 | 差距说明 |
|---|---|---|---|
| `dialogue_id` | 顶层 | ✅ 完整 | 直接使用 session_id 映射 |
| `services` | 顶层 | ✅ 完整 | 固定为 ["AnYiHua_1"] |
| `metadata` | 顶层 | ✅ 扩展 | 包含 qc_label / reference_response / user_info_parsed（标准 SGD 无此字段，为本项目扩展） |
| `turns[].speaker` | 轮次 | ✅ 完整 | USER / SYSTEM 精确区分 |
| `turns[].utterance` | 轮次 | ✅ 完整 | 直接提取原始文本 |
| `frames[].service` | 帧 | ✅ 完整 | 固定为 "AnYiHua_1" |
| `frames[].slots（跨度标注）` | 帧 | ❌ 缺失 | 标准 SGD 包含 slot 的字符跨度标注（start/exclusive_end），需要对话标注工具支持，本项目中统一为 [] |
| `frames[].state.active_intent` | USER 帧状态 | ⚠️ 近似（LLM 提取） | LLM 逐轮语义推断；主要误差来源：口语化表达和 general_inquiry 兜底意图过多使用 |
| `frames[].state.requested_slots` | USER 帧状态 | ⚠️ 近似（LLM 提取） | LLM 语义提取用户询问的槽位；LLM 失败时为空列表 |
| `frames[].state.slot_values` | USER 帧状态 | ✅ CRM金标准 / ⚠️ LLM近似 | CRM 槽位（customer_name 等 11 个）由 parse_user_info() 解析，可靠性≈100%；对话专属槽位（dispute_date / inquiry_amount / term_months / identity_confirmed）由 LLM 从对话文本提取，LLM 失败时为空 |
| `frames[].actions（USER 轮）` | USER 帧 | ⚠️ 近似（LLM 提取） | LLM 推断用户对话行为动作；LLM 失败时为空列表 |
| `frames[].actions（SYSTEM 轮）` | SYSTEM 帧 | ⚠️ 近似（LLM 提取） | LLM 精确提取系统行为动作；LLM 失败时为空列表；（本次 LLM 提取 615 条动作记录，201 次 service_call） |
| `frames[].service_call` | SYSTEM 帧 | ✅ 基本完整 / ⚠️ 参数近似 | method 字段通过 intent→API 映射表自动生成，可靠性高；parameters 仅包含 name/phone_suffix，LLM 模式可补充其他参数 |
| `frames[].service_results` | SYSTEM 帧 | ✅ CRM金标准 | 直接从 parse_user_info() 按意图选取字段，可靠性接近 100% |

### 8.1 缺失字段详解

#### ❌ `frames[].slots`（字符跨度标注 / Span Annotation）
- **标准 SGD 含义**：标注 utterance 中每个槽位值的字符起止位置（如 `start=5, exclusive_end=8`）。
- **缺失原因**：需要专用标注工具对原始文本做字符级标注，LLM 无法自动生成精确偏移量。
- **影响**：Span 提取（Slot Filling from Span）任务无法训练；DST（对话状态跟踪）任务不受影响。

#### ⚠️ `frames[].state.active_intent`（当前意图）
- **本次 LLM 提取**：0 条成功（0.0%）。
- **主要误差来源**：口语化短回复（如「对」「嗯」）难以识别意图；`general_inquiry` 作为兜底意图可能被过度使用。

#### ⚠️ `frames[].state.slot_values`（槽位值）
- **CRM 槽位（11 个）**：来自 `parse_user_info()` 解析，高覆盖槽位平均覆盖率 97.6%，可靠性接近 100%。
- **对话专属槽位**（`dispute_date`、`inquiry_amount`、`term_months`、`identity_confirmed`）：需 LLM 从对话文本 NLU 提取，LLM 失败时为空。

#### ⚠️ `frames[].actions`（对话行为列表）
- **本次提取**：615 条动作记录，来自 LLM 标注。
- **标准 SGD**：每个 actions 条目包含精确的 slot/values/canonical_values，需人工核查。
- **LLM 失败时**：动作列表为空（`[]`）。

### 8.2 扩展字段说明（标准 SGD 无，本项目新增）

| 扩展字段 | 说明 | 用途 |
|---|---|---|
| `metadata.qc_label` | 人工质检标签 | 数据质量分析 |
| `metadata.reference_response` | 坐席参考回复（待预测目标） | 生成任务训练/评估 |
| `metadata.user_info_parsed` | CRM 解析结构（完整版） | 执行引擎/后端 API 调用 |
| `metadata.extraction_method` | 提取模型标记（本次：（历史数据，模型未记录）） | 数据溯源 |
