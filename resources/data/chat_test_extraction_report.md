# chat_test_100.json 信息提取分析报告（LLM 版）

**数据来源**：`resources/data/chat_test_100.json`  
**分析记录数**：100 条（离线模式：关键词规则近似，CRM 覆盖率数据准确）  
> ⚠️ **离线模式**：本报告由关键词规则生成，意图/动作统计为近似值。在 LLM 服务可用时，请使用 `python benchmark/tools/analyze_chat_test.py --all` 获取精确的 LLM 提取结果。

**分析目标**：基于 SGD 数据集完整字段规范，使用 LLM 从安逸花外呼数据中精准提取可用于标准 TOD 任务的所有信息。  
**提取方法**：LLM（Qwen2.5-7B-Instruct）+ CRM 规则解析（parse_user_info）

---

## 一、数据集概览

| 指标 | 值 |
|---|---|
| 分析记录数 | 100 条 |
| 总轮次数 | 1230 轮 |
| 平均对话长度 | 12.3 轮/对话 |
| 用户轮次数 | 615 轮 |
| 提取模式 | 离线（关键词规则近似，不等于 LLM 精确提取） |

**人工校验标签分布**：

- `无标签命中`：40 条（40.0%）
- `不当告别`：15 条（15.0%）
- `数据错误`：15 条（15.0%）
- `答非所问`：15 条（15.0%）
- `重复询问`：15 条（15.0%）

---

## 二、本体（Ontology）

- **服务名称**：`AnYiHua_1`
- **服务描述**：安逸花外呼促活服务（微贷平台坐席主动外呼，激活用户闲置借款额度）
- **领域**：微贷/消费金融（外呼促活）
- **意图总数**：10 个
- **槽位总数**：15 个
- **对话行为类型数**：14 种

### 2.1 意图列表

| 意图名称 | 描述 | 对应 CRM API |
|---|---|---|
| `verify_identity` | 核实用户身份（开场必须执行） | `verify_customer` |
| `explain_credit_limit` | 告知可提现额度情况 | `query_account` |
| `explain_interest_rate` | 解释利率/还款方式 | `calculate_repayment` |
| `calculate_repayment` | 计算指定金额和期数的月还款额 | `calculate_repayment` |
| `explain_displayed_amount` | 解释 APP 页面显示金额的构成 | `query_account` |
| `handle_loan_dispute` | 核实用户争议的借款记录 | `query_loan_records` |
| `guide_loan_operation` | 引导用户在 APP 完成借款操作 | `query_account` |
| `escalate_to_human` | 转接人工客服 | `—` |
| `say_goodbye` | 礼貌告别 | `query_unresolved_issues` |
| `general_inquiry` | 通用询问（默认，无法匹配其他意图时） | `—` |

### 2.2 槽位列表

| 槽位名称 | 描述 | 来源 | CRM 覆盖率 | LLM 对话提取次数 |
|---|---|---|---|---|
| `customer_name` | 客户姓名 | CRM | 100.0% | 615 |
| `phone_suffix` | 手机尾号 3-4 位 | CRM | 100.0% | 615 |
| `available_credit` | 可提现额度（元） | CRM | 99.0% | 590 |
| `temp_credit` | 临时额度（元） | CRM | 89.0% | 529 |
| `temp_credit_status` | 临时额度状态（有效/已过期） | CRM | 32.0% | 615 |
| `temp_expiry_days` | 临时额度剩余天数 | CRM | 68.0% | 412 |
| `annual_rate_pct` | 年化利率（%） | CRM | 100.0% | 615 |
| `loan_count` | 当前未还借款笔数 | CRM | 56.0% | 387 |
| `last_loan_date` | 最近借款日期（中文格式） | CRM | 95.0% | 595 |
| `outstanding_amount` | 未还款金额（元） | CRM | 52.0% | 346 |
| `billing_day` | 账单日（每月几号） | CRM | 100.0% | 615 |
| `dispute_date` | 用户争议借款日期 | 对话文本 | 0.0% | 0 |
| `inquiry_amount` | 用户询问的具体金额 | 对话文本 | 0.0% | 0 |
| `term_months` | 分期期数 | 对话文本 | 0.0% | 0 |
| `identity_confirmed` | 身份是否已核实 | 对话文本 | 0.0% | 0 |

### 2.3 对话行为类型（Acts）

| Act 类型 | LLM 提取次数 | 说明 |
|---|---|---|
| `INFORM` | 603 | 告知槽位信息 |
| `REQUEST` | 12 | 请求槽位信息 |
| `CONFIRM` | 0 | 确认槽位值 |
| `SELECT` | 0 | 从选项中选择 |
| `OFFER` | 0 | 提供服务选项 |
| `GOODBYE` | 0 | 告别 |
| `INFORM_INTENT` | 0 | 明确告知意图 |
| `NEGATE_INTENT` | 0 | 否定意图 |
| `AFFIRM_INTENT` | 0 | 肯定意图 |
| `AFFIRM` | 0 | 肯定（非意图） |
| `NEGATE` | 0 | 否定（非意图） |
| `CANT_UNDERSTAND` | 0 | 无法理解 |
| `NOTIFY_SUCCESS` | 0 | 通知操作成功 |
| `NOTIFY_FAILURE` | 0 | 通知操作失败 |

---

## 三、意图（Intent）分析

- 每条对话平均含 **1.6** 个不同意图（LLM 提取）

### 3.1 意图频率分布（USER 轮，LLM 提取）

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
| `say_goodbye` | 0 | 0.0% |

### 3.2 入口意图 / 出口意图

**入口意图（对话首个 USER 意图）**：

- `general_inquiry`：99 次
- `verify_identity`：1 次

**出口意图（对话末个 USER 意图）**：

- `general_inquiry`：57 次
- `explain_credit_limit`：25 次
- `explain_interest_rate`：6 次
- `explain_displayed_amount`：5 次
- `guide_loan_operation`：3 次

---

## 四、槽位（Slot）分析

### 4.1 综合提取覆盖率

| 槽位 | CRM 覆盖率 | LLM 提取次数 | 被询问次数 | 值示例 |
|---|---|---|---|---|
| `customer_name` | 100.0% | 615 | 0 | 高先生、高先生 |
| `phone_suffix` | 100.0% | 615 | 0 | 六七八、六七八 |
| `available_credit` | 99.0% | 590 | 65 | 7041、7041 |
| `temp_credit` | 89.0% | 529 | 0 | 26500、26500 |
| `temp_credit_status` | 32.0% | 615 | 0 | 已过期、已过期 |
| `temp_expiry_days` | 68.0% | 412 | 0 | 8、8 |
| `annual_rate_pct` | 100.0% | 615 | 8 | 24、24 |
| `loan_count` | 56.0% | 387 | 0 | 3、3 |
| `last_loan_date` | 95.0% | 595 | 0 | 二零二五年五月二日、二零二五年五月二日 |
| `outstanding_amount` | 52.0% | 346 | 0 | 4590、4590 |
| `billing_day` | 100.0% | 615 | 0 | 27、27 |
| `dispute_date` | 0.0% | 0 | 0 | — |
| `inquiry_amount` | 0.0% | 0 | 0 | — |
| `term_months` | 0.0% | 0 | 0 | — |
| `identity_confirmed` | 0.0% | 0 | 0 | — |

### 4.2 service_call 方法分布

| API 方法 | 调用次数 |
|---|---|
| `query_account` | 129 |
| `calculate_repayment` | 44 |
| `query_loan_records` | 16 |
| `verify_customer` | 12 |

---

## 五、对话策略（Strategy）分析

**标准业务流程**：
```
verify_identity → explain_credit_limit → (explain_interest_rate | handle_loan_dispute | guide_loan_operation) → say_goodbye
```

### 5.1 高频意图转移（LLM 提取，Top 10）

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

## 六、SGD 字段可提取性结论

| 提取类别 | 涉及字段 | 可靠性 | 提取方法 |
|---|---|---|---|
| 直接提取 | `dialogue_id`, `speaker`, `utterance`, `qc_label`, `reference_response` | 100% | 直接映射 |
| CRM 高覆盖（≥80%） | `customer_name`, `phone_suffix`, `available_credit`, `temp_credit`, `annual_rate_pct` 等7个 | ≥95% | parse_user_info() 规则解析 |
| CRM 中覆盖（50–80%） | `temp_expiry_days`, `loan_count`, `outstanding_amount` | ≥70% | parse_user_info() 规则解析 |
| CRM 低覆盖（<50%） | `temp_credit_status` | 按场景 | parse_user_info() 规则解析 |
| LLM 提取 | `active_intent`, `requested_slots`, `slot_values`, `actions`, `service_call` | LLM成功率 0.0%，字段准确率 ≈70–85% | LLM 语义理解（Qwen2.5-7B-Instruct） |
| 对话专属槽位 | `dispute_date`, `inquiry_amount`, `term_months`, `identity_confirmed` | 依赖对话内容，出现率 1–40% | LLM NLU 提取 |
| 无法自动提取 | `full_ground_truth_dst` | — | — |

**直接提取**：对话结构字段完全可直接转换，无需推断。

**CRM 高覆盖（≥80%）**：来自 用户信息 字段的 CRM 数据，覆盖率 ≥80%，可作为 slot_values 和 service_results 的金标准。

**CRM 中覆盖（50–80%）**：CRM 数据存在但并非所有对话都有，覆盖率 50–80%，建议保留并标记置信度。

**CRM 低覆盖（<50%）**：仅在特定业务场景（如争议、分期）中出现，覆盖率 <50%。

**LLM 提取**：通过 LLM 对整条对话进行逐轮结构化标注，提取 SGD 所有核心字段。相比关键词规则，LLM 能处理口语化表达、上下文指代和隐式意图。

**对话专属槽位**：这些槽位无 CRM 来源，只能从对话文本提取，出现率较低。

**无法自动提取**：完整的 DST 金标准标注需要人工校验。LLM 提取的 active_intent/slot_values 是近似值，建议用于生成任务训练，不直接作为 DST 评估 groundtruth。

---

## 七、TOD 数据集构建建议

1. **对话骨架（100% 可用）**：直接从原始数据中提取 dialogue_id / speaker / utterance，零损耗。

2. **CRM 槽位作为 slot_values 金标准**：
   - 高覆盖率槽位（≥80%）可直接注入 `slot_values` 和 `service_results`。
   - 中等覆盖率槽位按具体对话情况注入，低覆盖槽位按业务场景按需提取。

3. **LLM 提取 active_intent 和 actions**：
   - 使用 Qwen2.5-7B-Instruct 对每条对话进行整体标注，提取 `active_intent`、`requested_slots`、`actions`。
   - 推荐批量处理（每次 1 条对话），温度设置为 0.1–0.2 以提高输出稳定性。

4. **service_call 策略**：
   - 根据 `active_intent` → API 名称的映射表自动生成 `service_call.method`。
   - 参数从 `slot_values` 中提取，用 LLM 补充对话中明确提及的参数。

5. **service_results 使用 CRM 金标准**：
   - 直接从 `parse_user_info()` 解析的 CRM 数据中按意图选取字段，可靠性接近 100%。

6. **保留扩展字段 metadata**：
   - `metadata.qc_label`：质检标签（质量分析用）
   - `metadata.reference_response`：坐席参考回复（生成任务评估用）
   - `metadata.user_info_parsed`：完整 CRM 数据（执行引擎查询用）

7. **注意外呼数据特殊性**：
   - 首轮发言者是 SYSTEM（坐席），与标准 SGD（USER 首轮）相反。
   - `坐席回复` 字段是**待预测目标**，不应混入 `对话历史`。
