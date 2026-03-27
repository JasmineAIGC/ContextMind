"""
LLM prompt templates for the schema_builder 5-phase generation pipeline.

Each prompt pair (system + user template) corresponds to one phase of the
plan.md workflow:

- :data:`MODULE_GEN_SYSTEM` / :data:`MODULE_GEN_USER_TEMPLATE`:
  Full-module generation (one LLM call → all intent functions).
- :data:`TEST_CASE_GEN_SYSTEM` / :data:`TEST_CASE_GEN_USER_TEMPLATE`:
  Phase 2 — per-intent test case generation.
- :data:`FUNCTION_GEN_SYSTEM` / :data:`FUNCTION_GEN_USER_TEMPLATE`:
  Phase 3 — per-function generation with few-shot test cases.
- :data:`REPAIR_SYSTEM` / :data:`REPAIR_USER_TEMPLATE`:
  Phase 4 — iterative function repair with failure context.
"""

# ---------------------------------------------------------------------------
# Full-module generation (one LLM call for all intents)
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
- **不要添加 `INTENT_REGISTRY`**（由生成器自动追加，不需要在函数区中定义）

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

#: Optional section inserted into MODULE_GEN_USER_TEMPLATE when dialogue data
#: is provided. The ``{dialogue_samples}`` placeholder is filled with formatted
#: dialogue text excerpts.
DIALOGUE_CONTEXT_SECTION = """\
## 真实对话示例（参考以下对话提炼业务细节）
{dialogue_samples}

"""


# ---------------------------------------------------------------------------
# Phase 2: Per-intent test case generation
# ---------------------------------------------------------------------------

TEST_CASE_GEN_SYSTEM = """\
你是一名任务型对话系统（ToD）的测试工程师，专门为意图函数生成高质量的单元测试用例。

你将收到一个意图函数的名称、描述和槽位定义，需要生成该函数的 **测试用例列表**。

## 测试用例要求
- 每条测试用例包含 "input_slots"（输入槽位值）和 "description"（测试场景描述）
- 输入槽位值要真实、多样，覆盖不同业务场景（正常流程、边界值等）
- 如果意图有 required_slots，每条用例都必须提供这些槽位的值
- 可选槽位（optional_slots）在部分用例中提供，在其他用例中省略
- 槽位值使用中文，符合真实对话系统的输入特征
- 金额类字段使用中文描述（如 "21900元"、"五千"）；日期类字段使用具体日期

## 输出格式
直接输出 JSON 数组，不要包含 markdown 代码块标记，不要包含解释文字。
格式：[{"input_slots": {"slot1": "value1", ...}, "description": "测试场景描述"}, ...]
"""

TEST_CASE_GEN_USER_TEMPLATE = """\
服务：{service_name}（{service_description}）

意图：{intent_name}
描述：{intent_description}

函数签名：def {func_name}({param_str})

required_slots（必填，每个测试用例必须提供）：
{required_slots_desc}

optional_slots（可选）：
{optional_slots_desc}

result_slots（预期返回字段）：
{result_slots_desc}

{dialogue_hint}请生成 {max_cases} 条测试用例（JSON 数组）。
"""


# ---------------------------------------------------------------------------
# Phase 3: Per-function generation (with few-shot test cases)
# ---------------------------------------------------------------------------

FUNCTION_GEN_SYSTEM = """\
你是一名 Python 开发专家，专门为任务型对话系统（ToD）编写 API 函数实现。

你将收到一个意图（intent）的函数签名、描述以及业务背景，需要生成该函数的 **完整函数体**。

## 要求
1. 保持函数签名不变（参数名和默认值 None）
2. 包含真实的业务逻辑处理，不要只是直接返回固定字符串
3. 可以直接调用文件中已定义的工具函数：`_parse_amount()`、`_ticket_id()`、
   `_calc_monthly_payment()`、`_next_work_day()`
4. 返回值包含所有 result_slots 字段和输入参数，以及 "status": "success"
5. 只输出函数体代码，不包含 def 行，4 空格缩进，不超过 25 行

## 输出格式
只输出函数体代码（4空格缩进），例如：
    _ok = bool(account_usage_status is not None)
    return {
        "verified_identity": _ok,
        "status": "success",
    }
"""

FUNCTION_GEN_USER_TEMPLATE = """\
服务：{service_name}（{service_description}）

函数：def {func_name}({param_str}):
描述：{description}
输入槽位：
{slot_descriptions}
result_slots（必须在返回值中包含）：
{result_slots}
{few_shot_section}"""


# ---------------------------------------------------------------------------
# Phase 4: Function repair (iterative fix with failure context)
# ---------------------------------------------------------------------------

REPAIR_SYSTEM = """\
你是一名 Python 高级开发专家，专门为任务型对话系统（ToD）修复 API 函数实现。

你将收到一个意图函数的完整代码以及测试失败信息，需要修复函数体使其通过测试。

## 修复要求
1. **保持函数签名不变**（参数名和默认值 None）
2. **修复错误**：根据失败信息分析问题根因，修改函数体逻辑
3. **返回值格式**：必须返回包含所有 result_slots 字段的字典，且含 "status": "success"
4. 可以直接调用文件中已定义的工具函数：`_parse_amount()`、`_ticket_id()`、
   `_calc_monthly_payment()`、`_next_work_day()`
5. 只使用 Python 标准库，函数体不超过 25 行
6. **不要重定义**已有的共享工具函数

## 输出格式
只输出完整的函数定义（包含 def 行和函数体），不包含 import 语句，不要 markdown 代码块。
"""

REPAIR_USER_TEMPLATE = """\
## 意图信息
服务：{service_name}
意图：{intent_name}（{intent_description}）

result_slots（返回值中必须包含）：
{result_slots_desc}

## 当前函数代码（第 {iteration} 轮修复）
{current_code}

## 失败的测试用例（共 {fail_count} 条，通过率 {pass_rate}）
{failures_text}

## 任务
请修复上述函数，使所有测试用例通过（输出完整的函数定义，从 def 行开始）。
"""
