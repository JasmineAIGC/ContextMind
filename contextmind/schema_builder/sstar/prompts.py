"""
S*（S-star）PyTOD API 代码合成器各阶段 LLM 提示词。

4 组提示词分别对应 S* 算法的各关键阶段：

- :data:`DRAFT_SYSTEM_TEMPLATE` / :data:`DRAFT_USER_TEMPLATE`：
  Phase P — 并行草稿生成：以不同思维模式生成候选实现。

- :data:`REPAIR_SYSTEM` / :data:`REPAIR_USER_TEMPLATE`：
  Phase D — 执行追踪驱动修复（LDB 风格）：基于实际执行输出（而非仅错误信息）
  精准定位 bug 并重写函数体。

- :data:`DISCRIMINATE_SYSTEM` / :data:`DISCRIMINATE_USER_TEMPLATE`：
  Phase S — 区分性测试生成：S* 核心创新，LLM 生成能区分两候选行为差异的测试输入。

论文参考：
    Dacheng Li et al., "S*: Test Time Scaling for Code Generation",
    arXiv:2502.14382, 2025. https://arxiv.org/abs/2502.14382
"""

# ---------------------------------------------------------------------------
# Phase P：并行草稿生成（3 种思维模式）
# ---------------------------------------------------------------------------

DRAFT_SYSTEM_TEMPLATE = """\
你是一名 Python 高级开发专家，专为任务型对话系统（ToD）中的业务意图编写 API 函数体。

## 当前思维模式：{thinking_mode}
{thinking_mode_detail}

## 核心约束（必须严格遵守）

1. **仅输出函数体**：不要输出 def 行和 docstring 行，框架已自动添加。
   从第一个计算语句开始，以 return 语句结束，全部使用 4 空格缩进。

2. **return 字典必须包含 status="success"** 以及所有指定的 result_slots 键。

3. **禁止防御性 None 检查**：不要写 `if param is None: return {{"status": "error"}}`，
   函数应对 None 输入给出合理的业务默认结果。

4. **不要重复定义工具函数**：以下函数已在文件顶部定义，直接调用即可：
   _parse_amount(val→float), _ticket_id(prefix→str),
   _calc_monthly_payment(p,r,m→float), _next_work_day(→str)

5. **只使用 Python 标准库**，不要 import 第三方库。

6. **函数体不超过 20 行**（含 return）。

直接输出代码，不要包含 markdown 代码块标记，不要添加解释文字。
"""

DRAFT_USER_TEMPLATE = """\
## 函数签名（框架已添加，勿重复输出）
def {intent_name}({param_str}):
    \"\"\"{description}\"\"\"

## 输入参数（槽位）说明
{input_slots_desc}

## 必须包含的 return 字段
你的 return 语句必须包含以下所有键（缺少任何一个都算测试失败）：
{required_return_keys}

## 测试用例（行为参考）
{test_cases_str}
{dialogue_hint_block}
## 任务
根据以上信息，直接输出函数体（4空格缩进，不含 def 行和 docstring 行）。
"""

# 3 种并行思维模式（Phase P）
THINKING_MODES = [
    {
        "name": "业务语义优先",
        "detail": (
            "先充分理解此函数在真实业务场景中执行的完整动作，"
            "然后从业务逻辑出发推导每个计算步骤，"
            "最后构造返回值字典。重点确保业务语义和计算逻辑的正确性。"
        ),
    },
    {
        "name": "返回结构优先",
        "detail": (
            "先确定 return 字典中必须包含的所有键及其业务含义，"
            "然后逆向推导：每个返回字段的值应该如何从输入参数计算得到，"
            "最后补充必要的中间变量。重点确保返回结构完整且每个字段有合理的计算逻辑。"
        ),
    },
    {
        "name": "输入鲁棒性优先",
        "detail": (
            "先分析所有输入参数的可能取值状态（有效值、None、边界值等），"
            "为每种输入状态确定合理的输出策略（给出业务合理的默认值而非报错），"
            "然后编写能优雅处理所有输入情况的实现。重点确保对各种输入的鲁棒性。"
        ),
    },
]

# ---------------------------------------------------------------------------
# Phase D：执行追踪驱动修复（Trace-Guided Repair，LDB 风格）
# ---------------------------------------------------------------------------

REPAIR_SYSTEM = """\
你是一名 Python 修复专家，根据函数执行追踪（execution traces）精准重写函数体以修复测试失败。

执行追踪包含每个失败用例的：
- 实际调用输入（input）
- 函数实际返回值或抛出的异常（actual output / exception）
- 期望满足的验证条件（expected）

通过对比实际输出和期望条件，可以精确定位 bug 所在位置，而不是盲目猜测。

## 核心约束（必须严格遵守）

1. **仅输出函数体**：不要输出 def 行和 docstring 行（框架自动添加）。
   从第一个计算语句开始，以 return 语句结束，全部使用 4 空格缩进。

2. **return 字典必须包含 status="success"** 以及所有指定的 result_slots 键。

3. **禁止防御性 None 检查**：对 None 输入给出合理默认值，不要 return error。

4. **不要重复定义工具函数**：直接调用
   _parse_amount, _ticket_id, _calc_monthly_payment, _next_work_day。

5. **只使用 Python 标准库**，不要 import 第三方库。

6. **函数体不超过 20 行**（含 return）。

根据执行追踪精确定位问题所在，完整重写函数体（不是打补丁）。
"""

REPAIR_USER_TEMPLATE = """\
## 函数签名（框架已添加，勿重复输出）
def {intent_name}({param_str}):
    \"\"\"{description}\"\"\"

## 当前函数体（待修复）
{current_body}

## 执行追踪（{fail_count}/{total_count} 个用例失败）
{execution_traces}

## 必须包含的 return 字段
{required_return_keys}

## 任务
根据执行追踪精确定位 bug，完全重写函数体修复问题。
直接输出新函数体（4空格缩进，不含 def 行和 docstring 行）。
"""

# ---------------------------------------------------------------------------
# Phase S：区分性测试输入生成（S* 核心创新）
# ---------------------------------------------------------------------------

DISCRIMINATE_SYSTEM = """\
你是一名测试工程师，专门设计能揭示两个候选函数实现行为差异的测试输入。

两个候选函数声称实现了相同的业务意图，但实现逻辑不同，行为可能存在差异。
你的任务是设计测试输入，使这两个函数对相同输入产生不同的返回结果，
从而帮助判断哪个实现更符合业务语义。

重点设计：
- 涉及边界值的输入（如金额为 0、参数为 None、数量取极值）
- 涉及多个相关参数组合的输入
- 触发两种实现分支差异的输入
"""

DISCRIMINATE_USER_TEMPLATE = """\
## 业务意图
函数名：{intent_name}
描述：{description}

## 输入参数（槽位）
{input_slots_desc}

## 候选实现 A
```python
{candidate_a}
```

## 候选实现 B
```python
{candidate_b}
```

## 任务
分析两个实现的逻辑差异，设计 3 个最能区分它们行为差异的测试输入。

输出格式为 JSON 数组（每个元素是一个槽位值字典，值必须是字符串或 null）：
[
  {{"slot_name": "value", ...}},
  {{"slot_name": "value", ...}},
  {{"slot_name": "value", ...}}
]

只输出 JSON，不要包含 markdown 代码块标记或解释文字。
"""
