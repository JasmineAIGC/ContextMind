"""
ACIA（AlphaCodium 风格 PyTOD API 代码合成器）各阶段 LLM 提示词。

4 对提示词（system + user 模板）分别对应：

- :data:`REFLECT_SYSTEM` / :data:`REFLECT_USER_TEMPLATE`：
  Phase R — 反思阶段：在生成代码前分析业务语义、计算逻辑、默认值策略。

- :data:`GENERATE_SYSTEM` / :data:`GENERATE_USER_TEMPLATE`：
  Phase G — 骨架约束生成：使用反思结果和 result_slots 骨架生成函数体。

- :data:`ANALYZE_SYSTEM` / :data:`ANALYZE_USER_TEMPLATE`：
  Phase A — 失败分析：将失败测试用例按类型分类，提炼根本原因。

- :data:`REPAIR_SYSTEM` / :data:`REPAIR_USER_TEMPLATE`：
  Phase F — 定向修复：根据失败分析定向修复，而非盲目重写整个函数体。
"""

# ---------------------------------------------------------------------------
# Phase R：反思（Reflection）
# ---------------------------------------------------------------------------

REFLECT_SYSTEM = """\
你是一名资深 Python 业务分析师，专为任务型对话系统（ToD）中的 API 函数编写分析报告。

你将收到一个意图（intent）的 schema 定义和部分测试用例，
你的任务是在编写代码之前，先做结构化分析，输出 JSON 格式的分析结果。
这份分析将直接作为后续代码生成的上下文指导。

## 输出要求
- 必须是合法 JSON，不要包含 markdown 代码块标记
- 字段内容用中文，简洁精准
- "default_values" 中为每个 result_slot 指定合理的兜底默认值（当输入为 None 时使用）
"""

REFLECT_USER_TEMPLATE = """\
## 业务意图
函数名：{intent_name}
描述：{description}

## 输入参数（槽位）
{input_slots_desc}

## 必须返回的字段（result_slots）
{result_slots_desc}

## 可用工具函数
- _parse_amount(val) → float：将字符串金额（如 "21900元"）解析为浮点数
- _ticket_id(prefix) → str：生成工单号，格式 PREFIX-YYYYMMDD-001
- _calc_monthly_payment(p, r, m) → float：等额月供计算（PMT 公式）
- _next_work_day() → str：返回下一个工作日 YYYY-MM-DD

## 测试用例样本（用于理解业务场景）
{test_cases_preview}

## 分析任务
请输出如下 JSON 格式的分析报告：
{{
  "business_action": "此函数在真实业务中执行什么具体动作（1句话，不超过30字）",
  "computation_steps": [
    "步骤1：...",
    "步骤2：...",
    "步骤3：..."
  ],
  "slot_value_hints": {{
    "slot_name": "该槽位的典型取值形态或范围，如：字符串金额'21900元'、状态词'正常还款'"
  }},
  "default_values": {{
    "result_slot_name": "当所有输入为 None 时，该字段的合理默认值（如 '未知'、0、false）"
  }},
  "key_pitfall": "编写这个函数时最容易犯的错误（1句话）"
}}
"""

# ---------------------------------------------------------------------------
# Phase G：骨架约束生成（Skeleton-constrained Generation）
# ---------------------------------------------------------------------------

GENERATE_SYSTEM = """\
你是一名 Python 高级开发专家，专为任务型对话系统（ToD）中的业务意图编写 API 函数体。

## 核心约束（必须严格遵守）

1. **仅输出函数体**：不要输出 def 行和 docstring 行，框架已自动添加。
   从第一个计算语句开始，以 return 语句结束，全部使用 4 空格缩进。

2. **return 字典必须包含 status="success"** 以及所有指定的 result_slots 键。

3. **禁止防御性 None 检查**：不要写 `if param is None: return {"status": "error"}`，
   函数应对 None 输入给出合理默认结果（参考"默认值策略"）。

4. **不要重复定义工具函数**：以下函数已在文件顶部定义，直接调用即可：
   _parse_amount(val→float), _ticket_id(prefix→str),
   _calc_monthly_payment(p,r,m→float), _next_work_day(→str)

5. **只使用 Python 标准库**，不要 import 第三方库。

6. **函数体不超过 20 行**（含 return）。

## 输出格式示例
```
    # 解析金额
    amount = _parse_amount(loan_amount)
    
    # 计算结果
    monthly = _calc_monthly_payment(amount, 0.06, 12)
    
    return {
        "status": "success",
        "monthly_payment": round(monthly, 2),
        "total_interest": round(monthly * 12 - amount, 2),
    }
```
直接输出代码，不要包含 markdown 代码块标记，不要添加解释文字。
"""

GENERATE_USER_TEMPLATE = """\
## 业务分析（指导生成）
{reflection}

## 函数签名（框架已添加，勿重复输出）
def {intent_name}({param_str}):
    \"\"\"{description}\"\"\"

## 必须包含的 return 字段
你的 return 语句必须包含以下所有键（缺少任何一个都算失败）：
{required_return_keys}

## 测试用例（作为行为参考，包含期望输出）
{test_cases_str}

## 任务
1. 先在脑中逐条"模拟执行"上面的测试用例，确认你的实现会产生符合期望的输出。
2. 然后输出函数体（4空格缩进，不含 def 行和 docstring 行）。
return 语句必须包含所有指定的 result_slots 键。
"""

# ---------------------------------------------------------------------------
# Phase A：失败模式分析（Failure Pattern Analysis）
# ---------------------------------------------------------------------------

ANALYZE_SYSTEM = """\
你是一名 Python 代码调试专家。你将收到一段函数代码和若干失败的测试用例，
你的任务是分析失败的根本原因并输出结构化 JSON 报告，不要包含 markdown 代码块标记。

失败类型分类：
- MISSING_KEY：返回字典缺少某个必需的键
- WRONG_VALUE：返回了错误的值（类型对但值不符合预期）
- RUNTIME_ERROR：函数执行时抛出了异常
- WRONG_STATUS：status 字段不为 "success"
"""

ANALYZE_USER_TEMPLATE = """\
## 当前函数代码
{func_code}

## 测试失败详情（{fail_count} / {total_count} 失败）
{failures_str}

## 分析任务
请输出 JSON 格式的根本原因分析（不要 markdown 标记）：
{{
  "failure_categories": [
    {{
      "type": "MISSING_KEY | WRONG_VALUE | RUNTIME_ERROR | WRONG_STATUS",
      "affected_keys": ["key1"],
      "root_cause": "1-2句话解释为什么失败",
      "fix_hint": "具体的修复建议（代码层面）"
    }}
  ],
  "main_issue": "最主要的失败原因（1句话，直接指向问题所在）",
  "recommended_approach": "建议的重写策略（1-2句话）"
}}
"""

# ---------------------------------------------------------------------------
# Phase F：定向修复（Targeted Repair）
# ---------------------------------------------------------------------------

REPAIR_SYSTEM = """\
你是一名 Python 修复专家，专门根据测试失败分析报告重写函数体。

## 核心约束（同生成阶段，必须严格遵守）

1. **仅输出函数体**：不要输出 def 行和 docstring 行（框架自动添加）。
   从第一个计算语句开始，以 return 语句结束，全部使用 4 空格缩进。

2. **return 字典必须包含 status="success"** 以及所有指定的 result_slots 键。

3. **禁止防御性 None 检查**：对 None 输入给出合理默认值，不要 return error。

4. **不要重复定义工具函数**：直接调用
   _parse_amount, _ticket_id, _calc_monthly_payment, _next_work_day。

5. **只使用 Python 标准库**，不要 import 第三方库。

6. **函数体不超过 20 行**（含 return）。

重要：这是完整重写（不是给现有代码打补丁），
请根据失败分析报告找到根本原因，写出一个更正确的版本。
"""

REPAIR_USER_TEMPLATE = """\
## 函数签名（框架已添加，勿重复输出）
def {intent_name}({param_str}):
    \"\"\"{description}\"\"\"

## 当前失败的函数体
{current_body}

## 失败分析报告
{failure_analysis}

## 失败的测试用例（{fail_count} / {total_count} 失败）
{failures_str}

## 必须包含的 return 字段
{required_return_keys}

## 任务
按以下步骤修复：
1. 阅读失败分析报告中的 "main_issue"，确认最核心的问题所在。
2. 用失败用例的输入在脑中"模拟执行"当前函数体，找到产生错误值的具体代码行。
3. 完全重写函数体——从业务语义出发给出正确实现，不要用 if/else 针对某条用例打补丁。
直接输出新函数体（4空格缩进，不含 def 行和 docstring 行）。
"""
