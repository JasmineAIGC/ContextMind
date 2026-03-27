"""
Rule-based Python function code generation for *_pytod_apis.py files.

This module generates function definitions purely from schema metadata — no LLM
needed.  The generated functions have **real computation logic** derived from
intent-name-prefix heuristics:

+--------------------------+------------------------------------------+
| 意图前缀                 | 生成的计算逻辑                           |
+==========================+==========================================+
| complain_/dispute_       | 调用 _ticket_id() 生成工单号             |
+--------------------------+------------------------------------------+
| verify_/confirm_         | 依据必填参数是否存在推导布尔结果         |
+--------------------------+------------------------------------------+
| decline_/close_/end_     | 记录拒绝/结束状态，返回确认布尔值        |
+--------------------------+------------------------------------------+
| schedule_/book_          | 调用 _next_work_day() 计算回调时间       |
+--------------------------+------------------------------------------+
| inquire_/query_/check_   | 校验必填参数后返回语义化查询结果         |
+--------------------------+------------------------------------------+
| inform_/express_         | 记录信息并回传所有输入参数               |
+--------------------------+------------------------------------------+
| 其他                     | 必填参数校验 + 语义化返回值              |
+--------------------------+------------------------------------------+

Public API
----------
``generate_function_lines(intent)``
    Returns a list of source-code lines for a single intent function.

``generate_generic_function_lines(schema)``
    Generates a single catch-all function when the schema has no intents.

``function_def_header(intent)``
    Returns just the ``def`` + docstring lines (used by the LLM generator).
"""

from __future__ import annotations

from typing import List

from contextmind.modes.pytod.schemas import IntentDefinition, ServiceSchema


# ---------------------------------------------------------------------------
# Intent classification prefix tuples
# ---------------------------------------------------------------------------

_INTENT_COMPLAINT: tuple = (
    "complain_", "complaint_", "dispute_", "reject_", "appeal_",
)
_INTENT_VERIFY: tuple = (
    "verify_", "confirm_", "acknowledge_", "validate_",
)
_INTENT_DECLINE: tuple = (
    "decline_", "refuse_", "close_", "end_", "cancel_",
)
_INTENT_SCHEDULE: tuple = (
    "schedule_", "book_", "reserve_", "arrange_",
)
_INTENT_INQUIRE: tuple = (
    "inquire_", "query_", "check_", "search_", "find_",
    "get_", "look_", "ask_",
)
_INTENT_INFORM: tuple = (
    "inform_", "express_", "suggest_", "notify_", "tell_",
)


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def generate_function_lines(intent: IntentDefinition) -> List[str]:
    """为单个 intent 生成含真实计算逻辑的 Python 函数定义行列表。

    根据意图名称前缀推断语义类型，生成对应的计算代码：

    - **complain_/dispute_**：生成工单号（格式 PREFIX-YYYYMMDD-001），记录处理期限
    - **verify_/confirm_**：根据必填参数是否齐全推导布尔结果
    - **decline_/close_/end_**：记录拒绝/结束状态并返回 True
    - **schedule_**：计算下一个工作日作为回调时间
    - **inquire_/query_**：带必填参数校验的信息查询
    - **通用**：必填参数校验 + 输入参数回传

    函数体均包含真实 Python 计算逻辑（非仅 ``return {}``），
    可被 PyTOD ExecutionEngine 正确调用并向 AP 返回有意义的数据。
    """
    params = list(dict.fromkeys(
        list(intent.required_slots) + list(intent.optional_slots)
    ))
    param_str = ", ".join([f"{p}=None" for p in params]) if params else ""
    intent_lower = intent.name.lower()
    desc = intent.description.replace('"', '\\"') if intent.description else intent.name

    header = [
        f"def {intent.name}({param_str}):",
        f'    """{desc}"""',
    ]

    if any(intent_lower.startswith(p) for p in _INTENT_COMPLAINT):
        body = _complaint_body(intent, params)
    elif any(intent_lower.startswith(p) for p in _INTENT_VERIFY):
        body = _verify_body(intent, params)
    elif any(intent_lower.startswith(p) for p in _INTENT_DECLINE):
        body = _decline_body(intent, params)
    elif any(intent_lower.startswith(p) for p in _INTENT_SCHEDULE):
        body = _schedule_body(intent, params)
    elif any(intent_lower.startswith(p) for p in _INTENT_INQUIRE):
        body = _inquire_body(intent, params)
    elif any(intent_lower.startswith(p) for p in _INTENT_INFORM):
        body = _inform_body(intent, params)
    else:
        body = _generic_body(intent, params)

    return header + body


def generate_generic_function_lines(schema: ServiceSchema) -> List[str]:
    """无意图定义时生成一个以 service_name 命名的通用函数。"""
    slot_names = [s.name for s in schema.slots]
    param_str = ", ".join([f"{p}=None" for p in slot_names]) if slot_names else ""
    lines: List[str] = []
    lines.append(f"def {schema.service_name}({param_str}):")
    desc = schema.description.replace('"', '\\"') if schema.description else schema.service_name
    lines.append(f'    """{desc}"""')
    lines.append(f'    args = {{k: v for k, v in locals().items() if v is not None}}')
    lines.append(f'    return {{"status": "success", **args}}')
    return lines


def function_def_header(intent: IntentDefinition) -> List[str]:
    """返回函数 def 行 + docstring 行（不含函数体）。

    Used by the LLM generator: the ``def`` line and docstring are always
    generated here (keeping them consistent with schema metadata), while
    the function body is provided by the LLM.
    """
    params = list(dict.fromkeys(
        list(intent.required_slots) + list(intent.optional_slots)
    ))
    param_str = ", ".join([f"{p}=None" for p in params]) if params else ""
    desc = intent.description.replace('"', '\\"') if intent.description else intent.name
    return [
        f"def {intent.name}({param_str}):",
        f'    """{desc}"""',
    ]


# ---------------------------------------------------------------------------
# Intent semantic body generators (each returns 4-space-indented code lines)
# ---------------------------------------------------------------------------

def _echo_params(params: List[str]) -> List[str]:
    """将所有输入参数回传到返回字典（供 AP 通过 say(xN.slot) 引用）。"""
    return [f'        "{slot}": {slot},' for slot in params]


def _complaint_body(intent: IntentDefinition, params: List[str]) -> List[str]:
    """complaint/dispute 意图体：调用 _ticket_id() 生成工单号，返回受理信息。"""
    prefix = intent.name.upper()[:8].replace("_", "")
    lines = [
        f"    _ticket = _ticket_id('{prefix}')",
        "    return {",
    ]
    for rs in intent.result_slots:
        if any(kw in rs.lower() for kw in ("_id", "ticket", "number", "no_")):
            lines.append(f'        "{rs}": _ticket,')
        else:
            lines.append(f'        "{rs}": "已受理，将在3个工作日内处理",')
    lines += _echo_params(params)
    lines += [
        '        "ticket_id": _ticket,',
        '        "handling_days": 3,',
        '        "status": "success",',
        "    }",
    ]
    return lines


def _verify_body(intent: IntentDefinition, params: List[str]) -> List[str]:
    """verify/confirm 意图体：依据必填参数是否存在推导布尔结果。"""
    req = list(intent.required_slots)
    if req:
        check_parts = [f"({p} is not None)" for p in req]
        check_expr = " and ".join(check_parts)
        lines = [f"    _ok = bool({check_expr})"]
    elif params:
        lines = [f"    _ok = ({params[0]} is not None)"]
    else:
        lines = ["    _ok = True"]

    lines += ["    return {"]
    for rs in intent.result_slots:
        rsl = rs.lower()
        if any(kw in rsl for kw in ("declined", "rejected", "refused", "failed", "denied")):
            lines.append(f'        "{rs}": not _ok,')
        else:
            lines.append(f'        "{rs}": _ok,')
    lines += _echo_params(params)
    lines += [
        '        "status": "success",',
        "    }",
    ]
    return lines


def _decline_body(intent: IntentDefinition, params: List[str]) -> List[str]:
    """decline/close/end 意图体：记录拒绝/结束操作并返回确认。"""
    lines = ["    return {"]
    for rs in intent.result_slots:
        lines.append(f'        "{rs}": True,')
    lines += _echo_params(params)
    lines += [
        '        "note": "操作已记录",',
        '        "status": "success",',
        "    }",
    ]
    return lines


def _schedule_body(intent: IntentDefinition, params: List[str]) -> List[str]:
    """schedule 意图体：调用 _next_work_day() 计算下一个工作日作为回调时间。"""
    lines = [
        "    _callback_time = _next_work_day() + ' 10:00'",
        "    return {",
    ]
    for rs in intent.result_slots:
        rsl = rs.lower()
        if any(kw in rsl for kw in ("time", "date", "datetime", "schedule", "when")):
            lines.append(f'        "{rs}": _callback_time,')
        else:
            lines.append(f'        "{rs}": True,')
    lines += _echo_params(params)
    lines += [
        '        "callback_time": _callback_time,',
        '        "status": "success",',
        "    }",
    ]
    return lines


def _inquire_body(intent: IntentDefinition, params: List[str]) -> List[str]:
    """inquire/query 意图体：校验必填参数后返回查询结果。"""
    req = list(intent.required_slots)
    lines: List[str] = []
    if req:
        check_parts = [f"({p} is not None)" for p in req]
        check_expr = " and ".join(check_parts)
        missing_list = ", ".join(req)
        lines += [
            f"    if not ({check_expr}):",
            f'        return {{"status": "error", "message": "缺少必填参数: {missing_list}"}}',
        ]
    lines.append("    return {")
    for rs in intent.result_slots:
        val = _mock_value_for_result_slot(rs, intent)
        lines.append(f'        "{rs}": {val},')
    lines += _echo_params(params)
    lines += [
        '        "status": "success",',
        "    }",
    ]
    return lines


def _inform_body(intent: IntentDefinition, params: List[str]) -> List[str]:
    """inform/express/suggest 意图体：记录信息并回传所有输入参数。"""
    lines = ["    return {"]
    for rs in intent.result_slots:
        lines.append(f'        "{rs}": True,')
    lines += _echo_params(params)
    lines += [
        '        "status": "success",',
        "    }",
    ]
    return lines


def _generic_body(intent: IntentDefinition, params: List[str]) -> List[str]:
    """通用意图体：必填参数校验 + 语义化返回值。"""
    req = list(intent.required_slots)
    lines: List[str] = []
    if req:
        check_parts = [f"({p} is not None)" for p in req]
        check_expr = " and ".join(check_parts)
        missing_list = ", ".join(req)
        lines += [
            f"    if not ({check_expr}):",
            f'        return {{"status": "error", "message": "缺少必填参数: {missing_list}"}}',
        ]
    lines.append("    return {")
    for rs in intent.result_slots:
        val = _mock_value_for_result_slot(rs, intent)
        lines.append(f'        "{rs}": {val},')
    lines += _echo_params(params)
    lines += [
        '        "status": "success",',
        "    }",
    ]
    return lines


def _mock_value_for_result_slot(slot_name: str, intent: IntentDefinition) -> str:
    """为 result_slot 返回合理的 Python 字面量字符串表示（用于 inquire/generic 意图）。"""
    name_lower = slot_name.lower()
    intent_lower = intent.name.lower()

    # ---- Slot-name semantics ----
    # Boolean-like result slots
    if any(kw in name_lower for kw in (
        "verified", "confirmed", "declined", "acknowledged",
        "informed", "accepted", "approved", "suggested",
    )):
        is_negative = any(kw in name_lower for kw in ("declined", "rejected", "refused"))
        return "False" if is_negative else "True"

    # ID / ticket slots
    if "complaint_id" in name_lower or name_lower.endswith("_id"):
        prefix = "".join(w[0].upper() for w in intent.name.split("_"))[:4]
        return f'"{prefix}-20240115-001"'

    if "number" in name_lower or "policy" in name_lower:
        return f'"{intent.name.upper()[:6]}-001"'

    # Status slots — domain-aware
    if name_lower.endswith("_status"):
        base = name_lower.replace("_status", "")
        status_map = {
            "order": '"已发货"',
            "refund": '"退款处理中"',
            "exchange": '"换货处理中"',
            "logistics": '"快递运输中"',
            "reset": '"密码重置成功"',
            "update": '"信息更新成功"',
            "payment": '"支付成功"',
            "repayment": '"还款成功"',
            "account": '"账户正常"',
        }
        for key, val in status_map.items():
            if key in base:
                return val
        return '"处理成功"'

    # Amount / money slots
    if any(kw in name_lower for kw in ("amount", "quota", "limit", "balance", "fee", "price")):
        return '"5000元"'

    # Date / time slots
    if any(kw in name_lower for kw in ("date", "time", "datetime", "schedule")):
        return '"2024-01-15"'

    # Info / content / detail / result slots
    if any(kw in name_lower for kw in ("info", "detail", "content", "description", "data", "result")):
        return f'"[{intent.name}执行成功]"'

    # Interest / rate slots
    if any(kw in name_lower for kw in ("interest", "rate", "ratio")):
        return '"年利率7.2%"'

    # Inquiry / query result slots (fallback)
    if any(intent_lower.startswith(p) for p in ("inquire_", "query_", "check_", "search_", "find_")):
        if "status" in name_lower:
            return '"处理中"'
        if "amount" in name_lower or "limit" in name_lower:
            return '"5000元"'
        return f'"[{intent.name}查询结果]"'

    # Default: slot is a named completion marker
    return f'"{intent.name}_completed"'
