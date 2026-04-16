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

- :data:`JUDGE_SYSTEM` / :data:`JUDGE_USER_TEMPLATE`：
  Phase S — LLM 裁判：根据区分性测试的实际执行结果，判断哪个候选更符合业务语义。

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

## 核心要求：透彻理解业务意图，写出本质逻辑

**在编写任何代码之前，先深入理解这个意图在当前业务场景中的本质含义：**

- 这个意图在对话中代表了什么动作/事件？用户或客服做了什么？
- 执行这个函数意味着什么业务操作？对客户账户/记录/关系有什么影响？
- 返回值应该反映什么真实的业务结果？什么信息对后续对话管理（DM）最有价值？

**函数体必须体现对意图的深度理解，每类意图的实现示例如下：**

### 1. 投诉/纠纷类（complain_/dispute_）
- 用 `_ticket_id()` 生成工单号（受理投诉的核心动作）
- 基于槽位值（金额大小、逾期天数）推断投诉严重程度
- 返回工单号、严重级别、预计处理时长等对后续跟进有价值的字段

```python
# 示例：complain_interest_rate(total_interest=None, daily_interest=None)
    ticket = _ticket_id("INTEREST")
    total = _parse_amount(total_interest)
    severity = "高" if total > 5000 else ("中" if total > 1000 else "低")
    return {{
        "complaint_interest_rate": ticket,
        "ticket_id": ticket,
        "severity": severity,
        "handling_days": 3 if severity == "高" else 5,
        "total_interest": total_interest or "未提供",
        "status": "success",
    }}
```

### 2. 询问/查询类（inquire_/query_）
- 基于槽位值推断用户真正关心的问题，给出有意义的查询结果
- 用 `_parse_amount()` 处理金额，必要时用 `_calc_monthly_payment()` 计算还款
- 返回推断/计算后的业务结论，而非简单重复输入

### 3. 确认/核实类（confirm_/verify_）
- 根据槽位值（账户状态、申请日期）判断确认的实际含义
- 必要时对比数值（申请额度 vs 可用额度、当前状态 vs 正常状态）
- 返回确认结果及支撑该结论的业务数据

### 4. 拒绝/表态类（decline_/express_/suggest_）
- 记录用户的决定及相关背景信息（为什么拒绝、什么建议）
- 基于槽位值提取关键业务信号（如拒绝借款时的额度信息）
- 返回记录状态和对后续流程有指导意义的标记

### 5. 通知/告知类（inform_/offer_）
- 利用槽位值执行实际计算（如临时额度 + 有效期 → 完整提额方案）
- 推导出对用户有价值的衍生信息（如每日可用额度、月利息等）
- 返回推导结果，而不仅仅是透传输入

## 核心约束（必须严格遵守）

1. **仅输出函数体**：不要输出 def 行和 docstring 行，框架已自动添加。
   从第一个计算语句开始，以 return 语句结束，全部使用 4 空格缩进。

2. **return 字典必须包含 status="success"** 以及所有指定的 result_slots 键。

3. **禁止防御性 None 检查**：不要写 `if param is None: return {{"status": "error"}}`，
   函数应对 None 输入给出合理的业务默认结果。

4. **不要重复定义工具函数**：以下函数已在文件顶部定义，直接调用即可：
   _parse_amount(val→float), _ticket_id(prefix→str),
   _calc_monthly_payment(p,r,m→float), _next_work_day(→str)

5. **只使用 Python 标准库**；**不要在函数体内使用 import 语句**（`re` 已以 `_re` 导入）。

6. **函数体不超过 30 行**（含 return）。

7. **注释极简**：每个逻辑块最多 1 行注释；禁止多行注释块和冗余注释。

8. **零参数健壮性（必须通过）**：函数在所有参数均为 None 时必须能正常执行并返回含 `status="success"` 的 dict。
   - `_parse_amount(None)` 返回 `0.0`，**绝不能将其用作除数**——用 `max(v, 1)` 或 `if v > 0` 保护
   - 避免 `if x: x = float(x)` 等条件赋值——改为 `x = float(x) if x else 0.0`
   - 字符串操作前先用 `str(param or "")` 处理 None

## 严格禁止的模式
- ❌ 不要写 `return {{"status": "success", **{{k:v for k,v in locals().items()}}}}` 这样的万能返回
- ❌ 不要只是把输入参数原样塞进返回字典
- ❌ 不要为了通过测试而硬编码特定输入值的 if 判断

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

5. **只使用 Python 标准库**；**不要在函数体内使用 import 语句**（`re` 已以 `_re` 导入）。

6. **函数体不超过 30 行**（含 return）。

7. **注释极简**：每个逻辑块最多 1 行注释；禁止多行注释块。

8. **零参数健壮性（必须通过）**：函数在所有参数均为 None 时必须能正常执行。
   `_parse_amount(None)` 返回 `0.0`，不能将其用作除数；字符串操作前用 `str(param or "")` 处理 None。

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
按以下步骤精确修复：
1. 阅读每条执行追踪，对比"输入"和"实际输出/错误"：
   - 若含 "缺少字段"：return 字典遗漏了某个 result_slots 键
   - 若含 "期望 X，实际 Y"：具体某个字段的计算逻辑产生了错误值
   - 若含 "异常"：运行时错误，检查类型转换或 None 处理
2. 在脑中用第一条失败用例的输入逐行执行当前函数体，找到产生错误结果的具体语句。
3. 完全重写函数体——修复根本问题，不要用 if/else 针对特定输入打补丁。
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

# ---------------------------------------------------------------------------
# Phase S：LLM 裁判（Judge）——比较两候选在区分性测试上的实际输出
# 这是 S* 论文中 Selection Phase 的核心：不仅比较通过率，
# 还让 LLM 根据实际执行输出判断哪个候选更可能符合业务语义。
# ---------------------------------------------------------------------------

JUDGE_SYSTEM = """\
你是一名代码审查专家，负责根据两个 Python 函数在相同测试输入上的实际返回结果，
判断哪个实现更符合业务语义和正确性要求。

判断标准：
1. 返回结构完整性（必须包含 status="success" 以及所有 result_slots 键）
2. 返回值的业务合理性（数值、格式、逻辑是否符合业务场景）
3. 对边界输入（None、空值、极值）的处理是否给出合理默认值

请只输出 "A" 或 "B"（选择更好的实现），不要包含其他内容。
"""

JUDGE_USER_TEMPLATE = """\
## 业务意图
函数名：{intent_name}
描述：{description}

## 候选实现 A
```python
{candidate_a}
```

## 候选实现 B
```python
{candidate_b}
```

## 区分性测试执行结果

{execution_comparison}

## 任务
根据以上执行结果，判断哪个实现（A 或 B）更符合业务语义和正确性要求。
只输出 "A" 或 "B"，不要包含任何解释或其他内容。
"""
