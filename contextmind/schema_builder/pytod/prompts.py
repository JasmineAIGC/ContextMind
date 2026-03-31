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

### 函数体（每个函数都必须有真实计算逻辑）
1. **输入处理**：对 None 值设置合理默认值；金额/日期字段做格式化
2. **业务计算**：根据意图语义做相应计算
   - `complain_*`/`dispute_*`：调用 `_ticket_id(prefix)` 生成工单号
   - `verify_*`/`confirm_*`：根据必填参数是否存在推导布尔结果
   - `schedule_*`/`book_*`：调用 `_next_work_day()` 计算回调时间
   - `inquire_*`/`query_*`：必填参数校验后返回查询结果
   - 财务计算意图：调用 `_calc_monthly_payment()` / `_parse_amount()`
3. **返回值**：包含所有 result_slots 字段 + 输入参数 + `"status": "success"`
4. 可以直接调用文件顶部已定义的 `_ticket_id()`、`_calc_monthly_payment()` 等工具函数

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

2. **对话中期**（多轮对话第 4~6 轮，已积累若干 API 结果）：
   - 背景：对话进行到中途，前序已调用其他意图 API 并获得结果
   - 提供大多数必填槽位 + 至少 1 个可选槽位
   - 描述中明确说明：前序已调用哪些 API、各 API 返回了什么信息（"verify_identity 返回身份已确认，
     inquire_credit 返回额度 21900 元，用户现在报告还款流程麻烦"）

3. **对话完整**（所有槽位已通过多轮积累收集齐备）：
   - 背景：对话进行到较后期，所有关键信息已在多轮交互中收集完毕
   - 必须包含 ALL required_slots + 至少 1 个 optional_slot（若有）
   - 描述中说明完整的前序对话脉络（"经过8轮对话，已完成身份核实→额度告知→还款信息确认，用户最终反馈..."）

4. **跨意图上下文依赖**（当前函数输入来自前序 API 的返回值）：
   - 背景：某个槽位的值是从前序 API 调用结果中传入的（而非用户直接说出）
   - 在描述中明确注明：槽位值的来源 API（"loan_transaction=x1.loan_records[0]，
     来自前轮 inquire_loan_history API 的返回结果"）
   - 槽位值要反映真实 API 返回数据的格式（如带日期的贷款记录"2024年3月15日借款5000元"）

5. **边界/高价值业务场景**：
   - 逾期/纠纷/高额：含有对业务分支影响明显的极端值（逾期 90 天、贷款 10 万等）
   - 或用户明确拒绝/投诉场景：最少必填槽位组合 + 触发特殊业务路径的值

## 槽位值规范（高保真）
- 使用中文真实业务值，不使用 "xxx"、"test"、"value1" 等占位符
- 金额：使用"21900元"、"两万元"、"50000"（带数量级）
- 日期：使用具体日期"2024年7月23日"、"2025年3月15号"，不用 "2024-01-01"
- 状态：使用真实状态值"逾期30天"、"正常还款"、"账户冻结"、"贷款审核中"
- 贷款记录：使用场景化描述"2024年3月申请的1万元贷款"、"上月15号的借款记录"

## 输出格式
直接输出 JSON 数组，不要包含 markdown 代码块标记，不要包含解释文字。
格式：[{"input_slots": {"slot1": "value1", ...}, "description": "对话背景（前序步骤+当前阶段+触发原因）"}, ...]
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

result_slots（预期返回字段，函数必须在返回值中包含）：
{result_slots_desc}

{dialogue_hint}请生成 {max_cases} 条测试用例（JSON 数组），场景分别覆盖：
1. 对话早期（少量槽位，刚触发此意图）
2. 对话中期（多个槽位积累，前序已有 API 调用结果）
3. 对话完整（全槽位，完整对话背景）
4. 跨意图上下文依赖（某槽位来自前序 API 返回结果）
5. 边界/高价值业务场景（逾期/拒绝/高额等）
"""


# ---------------------------------------------------------------------------
# Phase 3：带 few-shot 测试用例的单函数生成（核心语义理解）
# ---------------------------------------------------------------------------

FUNCTION_GEN_SYSTEM = """\
你是一名 Python 开发专家，专门为任务型对话系统（ToD）编写 API 函数实现。

你将收到一个意图（intent）的函数签名、描述和业务背景，需要生成该函数的 **完整函数体**。

## 核心要求：透彻理解业务意图，写出本质逻辑

**在编写任何代码之前，先理解这个意图在当前业务场景中的本质含义：**

- 这个意图在对话中代表了什么动作/事件？
- 执行这个函数意味着什么业务操作？
- 返回值应该反映什么真实的业务结果？

**函数体必须体现对意图的深度理解：**

1. **投诉/纠纷类**（complain_/dispute_）：
   - 创建投诉/纠纷记录，确定问题严重程度
   - 基于槽位值（金额、时间等）计算或推断处理优先级
   - 返回工单号（`_ticket_id()`）、处理优先级、预计处理时间等有意义的字段

2. **询问/查询类**（inquire_/query_）：
   - 基于现有槽位值推断或计算用户真正关心的信息
   - 合理利用 `_parse_amount()` 处理金额，`_calc_monthly_payment()` 计算还款
   - 返回经过计算/推断的有效业务信息，而非简单回传输入

3. **确认/核实类**（confirm_/verify_）：
   - 根据必填槽位是否存在以及其语义内容判断确认结果
   - 必要时进行数值比较（如申请额度 vs 可用额度）
   - 返回确认状态、差异说明等

4. **拒绝/表态类**（decline_/express_/suggest_）：
   - 记录用户意图和态度，提取关键业务信号
   - 基于槽位值判断后续处理建议（如用户余额 0 时 decline 的建议与有余额不同）
   - 返回业务处理建议、状态标记

5. **通知/告知类**（inform_/offer_）：
   - 利用槽位值执行实际计算（如临时额度 + 有效期 → 完整的提额方案）
   - 返回对 DM 有用的推导结果，而不仅仅是透传输入

## 严格禁止的模式
- ❌ 不要写 `return {"status": "success", **{k:v for k,v in locals().items()}}` 这样的万能返回
- ❌ 不要只是把输入参数原样塞进返回字典（除非这是唯一合理的业务逻辑）
- ❌ 不要写 `if x is None: return {"status": "error"}` 这样的防御性 if/else——函数应该自然处理 None
- ❌ 不要为了通过测试而硬编码特定输入值的 if 判断

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

## 核心原则：从语义理解出发，而非打补丁

**失败的根本原因往往不是代码细节出错，而是对业务意图的理解不够深入。**

请按以下步骤思考：
1. 重新分析这个意图在当前业务场景中的本质含义
2. 找出现有实现在语义理解上的不足（而非语法问题）
3. 设计一个在业务逻辑上自然正确的新实现

## 严格禁止的修复方式
- ❌ 不要添加 `if input_value == "某个测试值": return {"status": "success", ...}` 这类判断
- ❌ 不要给现有函数添加 if/else 分支来专门处理失败的测试用例
- ❌ 不要为了让某条测试通过而硬编码条件判断
- ❌ 不要在原有逻辑之上叠加补丁——如果原逻辑有缺陷，应该重写

## 正确的修复思路

- ✅ 分析意图名称和描述，理解它在这个业务场景中的实际意义
- ✅ 检查返回值是否真的包含了所有 result_slots（可能是漏掉了某个字段）
- ✅ 检查 None 输入的处理：槽位为 None 时函数应该仍能正确运行并返回有意义的值
- ✅ 考虑当所有槽位都为 None 时（对话早期），函数的合理返回是什么
- ✅ 考虑当部分槽位有值时，如何利用这些值进行有意义的计算
- ✅ 如果原实现思路有根本性缺陷，完全重写比修补更好

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
请**重新理解该意图的业务语义**，生成一个业务逻辑上自然正确的新实现。
不要用 if/else 条件判断来针对性处理上述失败测试用例——而是写出一个对任何合理输入都能正确处理的函数。
（输出完整的函数定义，从 def 行开始）
"""
