"""
CodeTree PyTOD API 代码合成器各阶段 LLM 提示词。

提示词对应 CodeTree 算法（arXiv:2411.04329，2024/2025）的各关键节点：

- :data:`ROOT_SYSTEM` / :data:`ROOT_USER_TEMPLATE`：
  根节点生成 — 从意图定义、槽位说明和测试用例直接生成初始候选函数体。

- :data:`EXPAND_SYSTEM` / :data:`EXPAND_USER_TEMPLATE`：
  树扩展 — 针对特定失败测试用例生成修复分支（子节点）。
  每个失败用例对应一个独立扩展方向，充分探索不同修复策略。

- :data:`REFLECT_SYSTEM` / :data:`REFLECT_USER_TEMPLATE`：
  节点评估 — 在选择最优叶节点前，对候选实现做业务语义验证。

论文参考：
    CodeTree: Agent-guided Tree Search for Code Generation
    with Large Language Models, arXiv:2411.04329, 2024/2025.
"""

# ---------------------------------------------------------------------------
# 根节点：初始代码生成
# ---------------------------------------------------------------------------

ROOT_SYSTEM = """\
你是一名 Python 高级开发专家，专为任务型对话系统（ToD）中的业务意图编写 API 函数体。

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
   函数应对 None 输入给出合理的业务默认结果（如使用合理的占位值）。

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

ROOT_USER_TEMPLATE = """\
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

# ---------------------------------------------------------------------------
# 树扩展：针对单个失败测试用例的定向修复（生成子节点）
# ---------------------------------------------------------------------------

EXPAND_SYSTEM = """\
你是一名 Python 调试专家，专门为特定失败测试用例修复 ToD 业务函数。

## 修复策略
1. **精确定位**：只修复导致目标用例失败的具体问题，不破坏其他用例的通过结果。
2. **最小改动**：保留原函数体中正确的计算逻辑，只修改必要的部分。
3. **业务合理性**：修复后的实现对所有输入（包括 None）都应给出合理的业务默认值。

## 核心约束

1. **仅输出函数体**：不要输出 def 行和 docstring 行。
2. **return 字典必须包含 status="success"** 以及所有指定的 result_slots 键。
3. **禁止防御性 None 检查**：对 None 给出合理默认值，不要 return error。
4. **直接调用工具函数**：_parse_amount, _ticket_id, _calc_monthly_payment, _next_work_day。
5. **只使用 Python 标准库**；**不要在函数体内使用 import 语句**（`re` 已以 `_re` 导入）。
6. **函数体不超过 30 行**（含 return）。
7. **注释极简**：每个逻辑块最多 1 行注释；禁止多行注释块。
8. **零参数健壮性**：所有参数为 None 时函数必须正常运行——`_parse_amount(None)` 返回 `0.0`，不能将其用作除数；字符串操作前用 `str(param or "")` 处理 None。

直接输出修复后的函数体，不要包含 markdown 代码块标记或解释文字。
"""

EXPAND_USER_TEMPLATE = """\
## 函数签名（框架已添加，勿重复输出）
def {intent_name}({param_str}):
    \"\"\"{description}\"\"\"

## 当前函数体（待修复）
{current_body}

## 目标失败用例（本次修复聚焦于此）
输入: {target_input}
错误: {target_error}

说明：
  - 若错误含 "缺少字段"：return 字典遗漏了某个必需键，需在 return 中补充该字段
  - 若错误含 "期望 X，实际 Y"：该字段的计算逻辑产生了错误值，需修正计算方式
  - 若错误含 "异常"：函数运行时崩溃，检查类型转换（如 _parse_amount）或 None 处理

## 其他测试用例参考（修复后仍需全部通过）
{other_cases_str}

## 当前执行追踪摘要
{execution_traces}

## 必须包含的 return 字段
{required_return_keys}

## 任务
按以下步骤修复：
1. 分析目标失败用例的错误类型（见上方说明）。
2. 用目标用例的输入在脑中"模拟执行"当前函数体，找到产生错误的具体代码行。
3. 修复该问题，同时确保"其他测试用例"已通过的逻辑不被破坏。
直接输出修复后的完整函数体（4空格缩进，不含 def 行和 docstring 行）。
"""

# ---------------------------------------------------------------------------
# 叶节点评估：业务语义验证（选出最优节点前的快速评估）
# ---------------------------------------------------------------------------

REFLECT_SYSTEM = """\
你是一名业务逻辑审查专家，对候选的 PyTOD 意图函数实现进行快速业务语义验证。

评估维度：
1. 返回结构完整性（是否包含所有 result_slots 键 + status="success"）
2. 计算逻辑合理性（返回值是否符合业务场景）
3. 边界处理（None 输入是否给出合理默认值）

输出格式（JSON）：
{{
  "verdict": "accept" | "reject",
  "issues": ["问题1", "问题2"]  // 拒绝时列出主要问题，接受时为空列表
}}

只输出 JSON，不要包含 markdown 代码块标记或解释文字。
"""

REFLECT_USER_TEMPLATE = """\
## 业务意图
函数名：{intent_name}
描述：{description}

## 候选实现
```python
{func_code}
```

## 必须包含的 return 字段
{required_return_keys}

## 测试执行情况
{execution_summary}

## 任务
快速评估此实现的业务语义正确性，输出 JSON 评审结果。
"""
