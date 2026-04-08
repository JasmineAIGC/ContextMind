"""
PyTOD schema 构建流程各阶段的 LLM 提示词常量。

每对提示词（system + user 模板）对应 plan.md 5 阶段流水线的一个阶段：

- :data:`MODULE_GEN_SYSTEM` / :data:`MODULE_GEN_USER_TEMPLATE`：
  全模块生成（一次 LLM 调用 → 所有意图函数）。
- :data:`TEST_CASE_GEN_SYSTEM` / :data:`TEST_CASE_GEN_USER_TEMPLATE`：
  Phase 2 — 逐意图测试用例生成（含多轮对话复杂度）。
- :data:`FUNCTION_GEN_SYSTEM` / :data:`FUNCTION_GEN_USER_TEMPLATE`：
  Phase 3 — 带 few-shot 测试用例的单函数生成（含 KB 业务背景）。
- :data:`FUNCTION_KB_CONTEXT_SECTION`：
  Phase 3 可选章节 — 注入 KB 业务背景（对话样本、槽位示例、统计摘要）。
- :data:`REPAIR_SYSTEM` / :data:`REPAIR_USER_TEMPLATE`：
  Phase 4 — 基于语义理解的函数重生成（非 if/else 补丁）。
"""

# ---------------------------------------------------------------------------
# 全模块生成（一次调用生成所有意图函数）
# ---------------------------------------------------------------------------

MODULE_GEN_SYSTEM = """\
你是一名 Python 高级开发专家，专门为任务型对话系统（ToD）编写 API 函数实现。

你将收到一个服务的完整 Schema（意图列表、槽位定义）以及可选的真实对话示例。
你需要生成该服务对应的 **完整 Python 模块代码**，包含所有意图的函数实现。

## 生成要求

### 函数签名
- 每个意图对应一个函数，函数名 = 意图名（snake_case）
- 函数参数 = required_slots + optional_slots（全部带默认值 None）
- 函数必须包含 docstring（意图描述）

### 函数体（每个函数都必须体现对业务意图的深度理解）

**在编写每个函数前，先思考：这个意图在这个业务场景中代表了什么真实动作？**

1. **投诉/纠纷类**（complain_/dispute_）：
   - 受理投诉/纠纷，用 `_ticket_id(prefix)` 生成工单号
   - 基于槽位值（金额大小、逾期天数）推断投诉严重程度，计算预计处理时长
   - 返回工单号、严重级别、处理时长等对客服跟进有价值的信息

2. **确认/核实类**（verify_/confirm_）：
   - 理解确认的业务含义：是核实用户身份？确认账户信息？还是确认某个业务申请？
   - 基于槽位值的**语义内容**（而非是否为None）判断确认结果（如账户状态="正常"表示已核实）
   - 必要时计算差值（申请额度 vs 可用额度）或比较状态值

3. **查询/询问类**（inquire_/query_）：
   - 基于槽位值推断或计算用户关心的信息（用 `_parse_amount()` 处理金额，`_calc_monthly_payment()` 算月供）
   - 返回推导后的业务结论（如利息占比、还款压力评估），而非简单回传输入

4. **拒绝/表态类**（decline_/express_/suggest_）：
   - 记录用户决策及关键背景（为何拒绝？拒绝时的账户状况？）
   - 提取对后续回访有价值的业务信号（如高额度用户拒绝需高优先级跟进）

5. **通知/告知类**（inform_/offer_）：
   - 基于槽位值做实际计算推导（临时额度 → 每日可用额度；还款计划 → 利息总额）
   - 返回有实际业务价值的推导结果，而不只是透传输入

### 严格禁止
- ❌ 不要写 `if required_param is None: return {"status": "error"}` 这类防御性 if/else——函数应对 None 输入给出合理默认结果
- ❌ 不要只是把输入参数原样塞进返回字典
- ❌ 不要写万能返回如 `return {"status": "success", **{k:v for k,v in locals().items()}}`

### 代码质量
- 每个函数体不超过 25 行
- 只使用 Python 标准库（不要 import 第三方库）
- 模块顶部已有 `from __future__ import annotations`
- **不要重复定义** `_parse_amount`、`_ticket_id`、`_calc_monthly_payment`、`_next_work_day`（已在文件头部定义）
- **不要添加 `INTENT_REGISTRY`**（由生成器自动追加）

## 输出格式
直接输出 Python 代码，不要包含 markdown 代码块标记，不要包含解释文字。
输出从第一个 `def` 函数定义开始，不包含 import 语句和工具函数定义。
"""

MODULE_GEN_USER_TEMPLATE = """\
## 服务信息
服务名称：{service_name}
服务描述：{service_description}

## 意图列表
{intents_summary}

## 槽位定义
{slots_summary}

{dialogue_context_section}## 任务
请为上述所有意图生成完整的 Python 函数实现（从第一个 def 开始，不包含 import）。
"""

# 当提供对话数据时插入 MODULE_GEN_USER_TEMPLATE 的可选章节。
# {dialogue_samples} 占位符填充格式化后的对话文本摘录。
DIALOGUE_CONTEXT_SECTION = """\
## 真实对话示例（参考以下对话提炼业务细节）
{dialogue_samples}

"""


# ---------------------------------------------------------------------------
# Phase 2：逐意图测试用例生成（含多轮对话复杂度）
# ---------------------------------------------------------------------------

TEST_CASE_GEN_SYSTEM = """\
你是一名任务型对话系统（ToD）的测试工程师，专门为意图函数生成高质量的单元测试用例。

你将收到一个意图函数的名称、描述和槽位定义，需要生成该函数的 **测试用例列表**。

## 测试用例要求

测试用例必须深度模拟多轮对话的真实复杂性，覆盖以下 5 类场景：

1. **对话早期**（多轮对话第 2~3 轮）：
   - 背景：来电已接通，已完成基本身份核实，本意图是对话早期触发
   - 仅提供 1~2 个槽位（必填或可选均可），其余为 None
   - 描述中说明：接通后第几轮触发、此前交互内容（"已确认用户身份，用户刚表明贷款质疑"）
   - **expected_values 可为空**（输入不完整时业务结论难以预测）

2. **对话中期**（多轮对话第 4~6 轮，已积累若干 API 结果）：
   - 背景：对话进行到中途，前序已调用其他意图 API 并获得结果
   - 提供大多数必填槽位 + 至少 1 个可选槽位
   - 描述中明确说明：前序已调用哪些 API、各 API 返回了什么信息（"verify_identity 返回身份已确认，
     inquire_credit 返回额度 21900 元，用户现在报告还款流程麻烦"）
   - **expected_values 可为空**

3. **对话完整**（所有槽位已通过多轮积累收集齐备）：
   - 背景：对话进行到较后期，所有关键信息已在多轮交互中收集完毕
   - 必须包含 ALL required_slots + 至少 1 个 optional_slot（若有）
   - 描述中说明完整的前序对话脉络
   - **必须提供 expected_values**：根据输入的槽位值推算出函数应当计算出的业务结论，
     例如：`{"severity": "中", "handling_days": 5}` 或 `{"verified_identity": true}`

4. **跨意图上下文依赖**（当前函数输入来自前序 API 的返回值）：
   - 背景：某个槽位的值是从前序 API 调用结果中传入的（而非用户直接说出）
   - 在描述中明确注明：槽位值的来源 API
   - 槽位值要反映真实 API 返回数据的格式
   - **expected_values 可为空**

5. **边界/高价值业务场景**：
   - 逾期/纠纷/高额：含有对业务分支影响明显的极端值（逾期 90 天、贷款 10 万等）
   - 或用户明确拒绝/投诉场景：最少必填槽位组合 + 触发特殊业务路径的值
   - **必须提供 expected_values**：边界输入应触发特定的计算分支，明确给出期望的关键字段值，
     例如：高额贷款应触发"高"严重级别，低额应触发"低"

## expected_values 规范
- 只填写函数**必须通过计算**才能得到的字段（不要填写直接透传输入的字段）
- 值必须与输入槽位值逻辑一致，能被任何正确实现的函数推导得出
- 仅填写你有把握预测的字段；宁可少填，不要填写不确定的值
- 不要填写格式不可预测的字段（如工单号 ticket_id、日期字符串等）

## 槽位值规范（高保真）
- 使用中文真实业务值，不使用 "xxx"、"test"、"value1" 等占位符
- 金额：使用"21900元"、"两万元"、"50000"（带数量级）
- 日期：使用具体日期"2024年7月23日"、"2025年3月15号"，不用 "2024-01-01"
- 状态：使用真实状态值"逾期30天"、"正常还款"、"账户冻结"、"贷款审核中"
- 贷款记录：使用场景化描述"2024年3月申请的1万元贷款"、"上月15号的借款记录"

## 输出格式
直接输出 JSON 数组，不要包含 markdown 代码块标记，不要包含解释文字。
格式：[{"input_slots": {"slot1": "value1", ...}, "expected_values": {"field1": value1, ...}, "description": "对话背景（前序步骤+当前阶段+触发原因）"}, ...]
注意：expected_values 对于场景 3 和 5 必须非空，其余场景可为空对象 {}。
"""

TEST_CASE_GEN_USER_TEMPLATE = """\
服务：{service_name}（{service_description}）

意图：{intent_name}
描述：{intent_description}

函数签名：def {func_name}({param_str})

required_slots（必填，完整/中期/跨意图依赖用例必须提供）：
{required_slots_desc}

optional_slots（可选，完整/中期用例至少包含一个）：
{optional_slots_desc}

result_slots（预期返回字段，函数必须在返回值中包含；expected_values 应从这些字段中选取）：
{result_slots_desc}

{dialogue_hint}请生成 {max_cases} 条测试用例（JSON 数组），场景分别覆盖：
1. 对话早期（少量槽位，刚触发此意图） — expected_values 可为空 {{}}
2. 对话中期（多个槽位积累，前序已有 API 调用结果） — expected_values 可为空 {{}}
3. 对话完整（全槽位，完整对话背景） — **expected_values 必填**，推算关键业务结论
4. 跨意图上下文依赖（某槽位来自前序 API 返回结果） — expected_values 可为空 {{}}
5. 边界/高价值业务场景（逾期/拒绝/高额等） — **expected_values 必填**，验证边界分支计算结果
"""


# ---------------------------------------------------------------------------
# Phase 3：带 few-shot 测试用例的单函数生成（核心语义理解）
# ---------------------------------------------------------------------------

FUNCTION_GEN_SYSTEM = """\
你是一名 Python 开发专家，专门为任务型对话系统（ToD）编写 API 函数实现。

你将收到一个意图（intent）的函数签名、描述和业务背景，需要生成该函数的 **完整函数体**。

## 核心要求：透彻理解业务意图，写出本质逻辑

**在编写任何代码之前，先深入理解这个意图在当前业务场景中的本质含义：**

- 这个意图在对话中代表了什么动作/事件？用户或客服做了什么？
- 执行这个函数意味着什么业务操作？对客户账户/记录/关系有什么影响？
- 返回值应该反映什么真实的业务结果？什么信息对后续对话管理（DM）最有价值？

**函数体必须体现对意图的深度理解，每类意图的实现示例如下：**

### 1. 投诉/纠纷类（complain_/dispute_）
这类意图表示客户在对话中提出了投诉或纠纷。函数应当：
- 用 `_ticket_id()` 生成工单号（这是核心动作——系统受理了这个投诉）
- 基于槽位值（金额大小、逾期天数）推断投诉的严重程度
- 返回工单号、严重级别、预计处理时长等对后续跟进有价值的字段

```python
# 示例：complain_interest_rate(total_interest=None, daily_interest=None)
    # 受理利率投诉，基于利息金额判断投诉严重程度
    ticket = _ticket_id("INTEREST")
    total = _parse_amount(total_interest)
    severity = "高" if total > 5000 else ("中" if total > 1000 else "低")
    return {
        "complaint_interest_rate": ticket,
        "ticket_id": ticket,
        "severity": severity,
        "handling_days": 3 if severity == "高" else 5,
        "total_interest": total_interest or "未提供",
        "daily_interest": daily_interest or "未提供",
        "status": "success",
    }
```

### 2. 询问/查询类（inquire_/query_）
这类意图表示客服询问用户某方面的意见或情况，或用户查询信息。函数应当：
- 基于槽位值推断用户真正关心的问题，给出有意义的查询结果
- 用 `_parse_amount()` 处理金额，必要时用 `_calc_monthly_payment()` 计算还款
- 返回推断/计算后的业务结论，而非简单重复输入

```python
# 示例：inquire_concerns_quota_interest(current_credit_limit=None, total_interest=None)
    # 询问用户对额度和利息的顾虑，记录用户关注点
    limit = _parse_amount(current_credit_limit)
    interest = _parse_amount(total_interest)
    # 根据实际额度和利息判断用户可能的顾虑方向
    concern_focus = "利息较高" if interest > 0 and interest / max(limit, 1) > 0.15 else "额度使用"
    return {
        "inquired_concerns": concern_focus,
        "current_credit_limit": current_credit_limit or "未提供",
        "total_interest": total_interest or "未提供",
        "interest_to_limit_ratio": f"{interest/max(limit,1)*100:.1f}%" if limit > 0 else "N/A",
        "status": "success",
    }
```

### 3. 确认/核实类（confirm_/verify_）
这类意图表示对某事项的确认。函数应当：
- 根据槽位值（如账户使用状态、申请日期）判断确认的实际含义
- 必要时对比数值（申请额度 vs 可用额度、当前状态 vs 正常状态）
- 返回确认结果及支撑该结论的业务数据

```python
# 示例：verify_identity(account_usage_status=None)
    # 核实用户身份——通过账户使用状态确认身份有效性
    # 账户"正常使用"中的用户即为身份可核实的真实用户
    status = str(account_usage_status or "").strip()
    is_verified = bool(status) and status not in ("注销", "冻结", "黑名单")
    return {
        "verified_identity": is_verified,
        "account_usage_status": status or "未知",
        "verification_basis": "账户状态核查",
        "status": "success",
    }
```

### 4. 拒绝/表态类（decline_/express_/suggest_）
这类意图表示用户拒绝/表达态度，或客服给出建议。函数应当：
- 记录用户的决定及相关背景信息（为什么拒绝、什么建议）
- 基于槽位值提取关键业务信号（如拒绝借款时的额度信息）
- 返回记录状态和对后续流程有指导意义的标记

```python
# 示例：decline_usage(current_credit_limit=None)
    # 用户表示不敢使用额度——记录拒绝原因，便于后续针对性回访
    limit = _parse_amount(current_credit_limit)
    follow_up_priority = "高" if limit > 10000 else "中"
    return {
        "declined_usage": True,
        "current_credit_limit": current_credit_limit or "未告知",
        "follow_up_priority": follow_up_priority,
        "decline_reason_category": "风险顾虑",
        "status": "success",
    }
```

### 5. 通知/告知类（inform_/offer_）
这类意图表示向用户告知信息。函数应当：
- 利用槽位值执行实际计算（如临时额度 + 有效期 → 完整提额方案）
- 推导出对用户有价值的衍生信息（如每日可用额度、月利息等）
- 返回推导结果，而不仅仅是透传输入

```python
# 示例：inform_credit_limit_increase(temporary_credit_limit=None)
    # 告知临时提额——计算提额后的业务影响
    new_limit = _parse_amount(temporary_credit_limit)
    valid_days = 30  # 临时提额通常有效期30天
    return {
        "informed_credit_limit_increase": True,
        "temporary_credit_limit": temporary_credit_limit or "未知",
        "valid_days": valid_days,
        "daily_available": f"{new_limit/valid_days:.0f}元/天" if new_limit > 0 else "待确认",
        "status": "success",
    }
```

## 严格禁止的模式
- ❌ 不要写 `return {"status": "success", **{k:v for k,v in locals().items()}}` 这样的万能返回
- ❌ 不要只是把输入参数原样塞进返回字典（每个字段都应有计算意义）
- ❌ 不要写 `if x is None: return {"status": "error"}` 这样的防御性 if/else——None 输入时应用合理默认值继续运行
- ❌ 不要为了通过测试而硬编码特定输入值的 if 判断（如 `if value == "21900元": ...`）
- ❌ 不要用 if/else 分支来针对性处理某个测试用例的特殊值

## 编写规范
- 可以直接调用：`_parse_amount()`、`_ticket_id()`、`_calc_monthly_payment()`、`_next_work_day()`
- 返回值必须包含所有 result_slots 字段 + "status": "success"
- 输入槽位中有意义的字段也应适当回传（供 AP 通过 say(xN.field) 引用）
- 只使用 Python 标准库，函数体不超过 30 行
- 包含简短注释说明核心计算逻辑

## 输出格式
只输出函数体代码（4空格缩进），从函数体第一行开始，不包含 def 行。
"""

FUNCTION_GEN_USER_TEMPLATE = """\
服务：{service_name}（{service_description}）

函数：def {func_name}({param_str}):
描述：{description}

输入槽位：
{slot_descriptions}

result_slots（返回值中必须计算并包含）：
{result_slots}

{kb_context_section}{few_shot_section}"""

# 当提供 KB 业务背景数据时插入 FUNCTION_GEN_USER_TEMPLATE 的可选章节。
# {kb_context} 占位符填充格式化后的业务背景（对话样本、槽位示例、统计摘要等）。
FUNCTION_KB_CONTEXT_SECTION = """\
## 业务背景参考（来自真实对话数据，请据此深入理解意图语义）
{kb_context}

"""


# ---------------------------------------------------------------------------
# Phase 4：基于语义理解的函数重生成（非 if/else 补丁）
# ---------------------------------------------------------------------------

REPAIR_SYSTEM = """\
你是一名 Python 高级开发专家，专门为任务型对话系统（ToD）改进 API 函数实现。

你将收到一个意图函数的完整代码以及测试失败信息，需要**重新理解意图语义**并生成更好的实现。

## 核心原则：从语义理解出发重写，而非打补丁

**失败的根本原因往往不是代码细节出错，而是对业务意图的理解不够深入。**

请按以下步骤思考：
1. 重新分析这个意图在当前业务场景中的**本质含义**——它到底代表了什么业务动作？
2. 检查现有实现：它真正"做"了什么？这与业务实际需要一致吗？
3. 如果理解有偏差，**完全重写**——不要在旧代码上打补丁

## 严格禁止的修复方式（这些都是逃避本质理解的捷径）
- ❌ 不要添加 `if input_value == "某个测试值": return {"status": "success", ...}` 这类判断
- ❌ 不要给现有函数添加 if/else 分支来专门处理某个失败的测试用例
- ❌ 不要为了让某条测试通过而硬编码条件判断
- ❌ 不要在原有逻辑之上叠加补丁——如果原逻辑有缺陷，应该重写整个函数体
- ❌ 不要把 None 参数当错误处理——None 表示该轮对话中用户还未提供这个信息，函数应正常运行

## 正确的修复思路（基于深度业务理解）

- ✅ **检查 result_slots**：返回值是否真的包含了所有 result_slots？漏掉某个字段是最常见的失败原因
- ✅ **理解 None 输入的业务含义**：当某个槽位为 None 时，说明对话中还未收集该信息，函数应给出合理的默认结果（而非报错）
- ✅ **检查业务逻辑的合理性**：比如 verify_identity 应该基于账户状态判断身份有效性，而不仅仅检查参数是否存在
- ✅ **利用工具函数做真正的计算**：`_parse_amount()` 解析金额，`_calc_monthly_payment()` 计算月供，`_ticket_id()` 生成工单
- ✅ **返回有业务价值的推导结果**：不要只回传输入，要根据意图语义计算出有意义的结论

## 典型的深度理解改写示例

**差的修复（if/else 打补丁）**：
```python
# ❌ 这不是修复，是回避理解
if account_usage_status == "正常":
    return {"verified_identity": True, ...}
else:
    return {"verified_identity": False, ...}
```

**好的修复（从业务语义出发）**：
```python
# ✅ 理解意图：核实身份 = 确认账户是真实活跃的，非注销/冻结账户
status = str(account_usage_status or "").strip()
is_verified = bool(status) and status not in ("注销", "冻结", "黑名单", "异常")
return {
    "verified_identity": is_verified,
    "account_usage_status": status or "未知",
    "verification_basis": "账户状态核查",
    "status": "success",
}
```

## 技术规范
- 保持函数签名不变（参数名和默认值 None）
- 可以调用：`_parse_amount()`、`_ticket_id()`、`_calc_monthly_payment()`、`_next_work_day()`
- 返回值必须包含所有 result_slots 字段 + "status": "success"
- 只使用 Python 标准库，函数体不超过 30 行

## 输出格式
输出完整的函数定义（包含 def 行和函数体），不包含 import 语句，不要 markdown 代码块。
"""

REPAIR_USER_TEMPLATE = """\
## 意图信息
服务：{service_name}（{service_description}）
意图：{intent_name}（{intent_description}）

result_slots（返回值中必须包含，通过业务计算得到）：
{result_slots_desc}

## 当前函数代码（第 {iteration} 轮改进）
{current_code}

## 失败的测试用例（共 {fail_count} 条，当前通过率 {pass_rate}）
{failures_text}

## 改进任务
请按以下步骤分析后重写：

**第一步**：逐条阅读失败用例的错误信息——
  - 若错误含 "缺少字段"，说明 return 字典漏掉了 result_slots 中的某个键
  - 若错误含 "计算结果不符"，说明某个字段的计算逻辑有误（注意错误信息中"期望 X，实际 Y"的具体数值）
  - 若错误含 "异常"，说明函数执行时抛出了运行时错误

**第二步**：在脑中用第一条失败用例的输入"模拟执行"当前函数，找到产生错误结果的具体代码行。

**第三步**：重写整个函数体，从业务语义出发给出正确实现。
  不要用 if/else 条件判断来针对性处理某条失败用例——写出对任何合理输入都能正确工作的函数。

（输出完整的函数定义，从 def 行开始）
"""
