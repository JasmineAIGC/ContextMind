# chat_test_100.json 可提取信息分析报告

**数据来源**：`resources/data/chat_test_100.json`  

**分析目标**：评估从安逸花外呼数据中能够提取哪些信息，用于构建类似 SGD 的标准 TOD 任务。

---

## 一、数据集概览

| 指标 | 值 |
|---|---|
| 记录总数 | 100 条 |
| 总轮次数 | 1230 轮 |
| 平均轮次 | 12.3 轮/对话 |
| 最短对话 | 2 轮 |
| 最长对话 | 52 轮 |

**人工校验标签分布**：

- `不当告别`：15 条（15.0%）
- `数据错误`：15 条（15.0%）
- `无标签命中`：40 条（40.0%）
- `答非所问`：15 条（15.0%）
- `重复询问`：15 条（15.0%）

---

## 二、本体（Ontology）

- **服务名称**：`AnYiHua_1`
- **服务描述**：安逸花外呼促活服务（微贷平台坐席主动外呼，激活用户闲置借款额度）
- **领域**：微贷/消费金融（外呼促活）
- **数据来源**：真实外呼通话录音（已脱敏）
- **槽位总数**：15 个（CRM 可提取 11 个，对话提取 4 个）
- **意图总数**：10 个

### 2.1 意图列表

| 意图名称 | 描述 |
|---|---|
| `verify_identity` | 核实用户身份（开场必须执行） |
| `handle_loan_dispute` | 核实用户争议的借款记录 |
| `explain_credit_limit` | 告知可提现额度情况 |
| `explain_interest_rate` | 解释利率/还款方式 |
| `calculate_repayment` | 计算指定金额和期数的月还款额 |
| `explain_displayed_amount` | 解释 APP 页面显示金额的构成 |
| `guide_loan_operation` | 引导用户在 APP 完成借款操作 |
| `escalate_to_human` | 转接人工客服 |
| `say_goodbye` | 礼貌告别 |
| `general_inquiry` | 通用询问（默认，无法匹配其他意图时） |

### 2.2 槽位列表

| 槽位名称 | 来源 | 描述 |
|---|---|---|
| `customer_name` | CRM（覆盖率 100.0%） | 客户姓名（CRM） |
| `phone_suffix` | CRM（覆盖率 100.0%） | 手机尾号 3-4 位（CRM） |
| `available_credit` | CRM（覆盖率 99.0%） | 可提现额度（元，CRM） |
| `temp_credit` | CRM（覆盖率 89.0%） | 临时额度（元，CRM） |
| `temp_credit_status` | CRM（覆盖率 100.0%） | 临时额度是否有效（CRM） |
| `temp_expiry_days` | CRM（覆盖率 68.0%） | 临时额度剩余天数（CRM） |
| `annual_rate_pct` | CRM（覆盖率 100.0%） | 年化利率（%，CRM） |
| `loan_count` | CRM（覆盖率 56.0%） | 当前未还借款笔数（CRM） |
| `last_loan_date` | CRM（覆盖率 95.0%） | 最近借款日期（CRM） |
| `outstanding_amount` | CRM（覆盖率 52.0%） | 未还款金额（元，CRM） |
| `billing_day` | CRM（覆盖率 100.0%） | 账单日（CRM） |
| `dispute_date` | 对话文本（出现率 1.0%） | 用户争议的借款日期（对话文本） |
| `inquiry_amount` | 对话文本（出现率 3.0%） | 用户询问的金额（对话文本） |
| `term_months` | 对话文本（出现率 1.0%） | 分期期数（对话文本） |
| `identity_confirmed` | 对话文本（出现率 39.0%） | 身份是否已核实（对话文本） |

---

## 三、槽位分析

### 3.1 CRM 槽位覆盖率（来自 用户信息 字段）

| 槽位 | 覆盖率 | 评级 |
|---|---|---|
| `customer_name` | 100.0% | 🟢 高 |
| `phone_suffix` | 100.0% | 🟢 高 |
| `temp_credit_status` | 100.0% | 🟢 高 |
| `annual_rate_pct` | 100.0% | 🟢 高 |
| `billing_day` | 100.0% | 🟢 高 |
| `available_credit` | 99.0% | 🟢 高 |
| `last_loan_date` | 95.0% | 🟢 高 |
| `temp_credit` | 89.0% | 🟢 高 |
| `temp_expiry_days` | 68.0% | 🟡 中 |
| `loan_count` | 56.0% | 🟡 中 |
| `outstanding_amount` | 52.0% | 🟡 中 |

**高覆盖率槽位（≥80%）**：`customer_name`, `phone_suffix`, `available_credit`, `temp_credit`, `temp_credit_status`, `annual_rate_pct`, `last_loan_date`, `billing_day`

**低覆盖率槽位（<50%）**：无

### 3.2 对话文本槽位出现率

| 槽位 | 出现率 | 说明 |
|---|---|---|
| `dispute_date` | 1.0% | 用户主动提到日期（争议场景） |
| `inquiry_amount` | 3.0% | 用户主动提到具体金额 |
| `term_months` | 1.0% | 用户提及分期期数 |
| `identity_confirmed` | 39.0% | 用户确认身份 |

### 3.3 数值槽位值分布

| 槽位 | 有值条数 | 最小值 | 最大值 | 均值 |
|---|---|---|---|---|
| `available_credit` | 99 | 510 | 59093 | 16648.8 |
| `annual_rate_pct` | 100 | 24 | 24 | 24.0 |
| `loan_count` | 56 | 1 | 13 | 3.1 |
| `temp_expiry_days` | 68 | 3 | 29 | 20.0 |
| `outstanding_amount` | 52 | 509 | 31044 | 5369.5 |

---

## 四、意图（Intent）分析

- 每条对话平均包含 **3.2** 个不同意图
- 最少 2 个，最多 7 个

### 4.1 意图出现频率（按轮次统计）

| 意图 | 出现轮次 | 占比 |
|---|---|---|
| `general_inquiry` | 738 | 60.0% |
| `verify_identity` | 196 | 15.9% |
| `explain_credit_limit` | 165 | 13.4% |
| `guide_loan_operation` | 43 | 3.5% |
| `explain_interest_rate` | 40 | 3.3% |
| `explain_displayed_amount` | 22 | 1.8% |
| `handle_loan_dispute` | 21 | 1.7% |
| `calculate_repayment` | 3 | 0.2% |
| `escalate_to_human` | 1 | 0.1% |
| `say_goodbye` | 1 | 0.1% |

### 4.2 入口意图（对话首轮意图）

| 意图 | 对话数 |
|---|---|
| `verify_identity` | 99 |
| `general_inquiry` | 1 |

### 4.3 出口意图（对话末轮意图）

| 意图 | 对话数 |
|---|---|
| `general_inquiry` | 76 |
| `explain_credit_limit` | 17 |
| `explain_displayed_amount` | 3 |
| `handle_loan_dispute` | 1 |
| `guide_loan_operation` | 1 |
| `calculate_repayment` | 1 |
| `explain_interest_rate` | 1 |

---

## 五、对话策略（Strategy）分析

### 5.1 常见策略流程

```
verify_identity → explain_credit_limit → (explain_interest_rate | handle_loan_dispute | guide_loan_operation) → say_goodbye
```

### 5.2 高频意图转移（Top 10）

| 从意图 | 转移到 | 次数 |
|---|---|---|
| `verify_identity` | `general_inquiry` | 184 |
| `general_inquiry` | `explain_credit_limit` | 113 |
| `general_inquiry` | `verify_identity` | 95 |
| `explain_credit_limit` | `general_inquiry` | 94 |
| `guide_loan_operation` | `general_inquiry` | 29 |
| `general_inquiry` | `guide_loan_operation` | 26 |
| `explain_interest_rate` | `general_inquiry` | 23 |
| `general_inquiry` | `explain_interest_rate` | 21 |
| `handle_loan_dispute` | `general_inquiry` | 13 |
| `general_inquiry` | `handle_loan_dispute` | 13 |

### 5.3 高频策略模式（Top 5）

| 策略序列 | 出现次数 |
|---|---|
| `verify_identity → general_inquiry → verify_identity → general_inquiry` | 18 |
| `verify_identity → general_inquiry → verify_identity → general_inquiry → explain_credit_limit → general_inquiry` | 8 |
| `verify_identity → general_inquiry` | 8 |
| `verify_identity → general_inquiry → verify_identity → general_inquiry → explain_credit_limit → general_inquiry → explain_credit_limit → general_inquiry` | 5 |
| `verify_identity → general_inquiry → explain_credit_limit → general_inquiry` | 3 |

---

## 六、可提取性结论汇总

| 提取类别 | 涉及字段 | 可靠性 |
|---|---|---|
| 直接提取 | `dialogue_id`, `speaker`, `utterance`, `qc_label`, `reference_response` | 100% |
| CRM 解析 | `customer_name`, `phone_suffix`, `available_credit`, `temp_credit`, `temp_credit_status`, `annual_rate_pct`, `last_loan_date`, `billing_day` | ≈95–99% |
| 规则推断 | `active_intent`, `requested_slots`, `service_call`, `actions` | ≈50–70% |
| 对话 NLU | `dispute_date`, `inquiry_amount`, `term_months`, `identity_confirmed` | ≈30–60% |
| 无法自动提取 | `service_results`, `full_dst_annotation` | — |

**直接提取**：对话结构、发言者、话语内容、质检标签和参考回复可直接映射，无需推断。

**CRM 解析**：来自 用户信息 字段的 CRM 数据，通过 parse_user_info() 解析，可靠性极高。覆盖率 ≥70% 的槽位适合直接用于 TOD 训练数据。

**规则推断**：基于关键词规则从对话文本中推断，适合快速原型。生产环境建议使用 LLM 进行语义补全以提升准确率。

**对话 NLU**：只能从对话文本中提取（CRM 无对应字段），依赖用户在对话中明确提及。覆盖率较低，建议使用 LLM 进行 NLU 提取。

**无法自动提取**：完整的对话状态追踪（DST）标注和 API 调用结果无法从原始数据中提取，需要人工标注或 LLM 自动标注。

---

## 七、对 SGD TOD 任务构建的建议


1. **直接可用（无需补充）**
   - 对话结构（dialogue_id / speaker / utterance）来自原始数据，100% 可靠。
   - CRM 槽位（available_credit / annual_rate_pct / customer_name 等）来自 用户信息 字段，覆盖率高，可直接作为 `slot_values` 中的 groundtruth。

2. **规则推断（快速原型）**
   - 使用关键词规则推断 `active_intent`（准确率 ≈50–70%），适合快速构建数据集骨架。
   - 推断质量受对话文本简短/含混影响，建议对规则层结果进行抽样人工验证。

3. **LLM 补全（生产质量）**
   - 对 `active_intent`、`requested_slots`、`actions`、`service_call.parameters` 使用 LLM 进行语义补全。
   - 建议以 LLM 补全结果为主，规则推断结果为回退。

4. **保留扩展字段**
   - `metadata.user_info_parsed`：存放解析后的 CRM 数据，供执行引擎使用。
   - `metadata.reference_response`：存放参考坐席回复，供生成质量评估。
   - `metadata.qc_label`：存放人工质检标签，供质量分析。

5. **注意事项**
   - 外呼数据首轮为 SYSTEM（坐席），与标准 SGD（USER 首轮）相反，需注意 PyTOD 的 `user_turn_idx = 2 * idx` 假设。
   - 对话末尾的 `坐席回复` 字段是**待预测目标**，不应混入对话历史。
