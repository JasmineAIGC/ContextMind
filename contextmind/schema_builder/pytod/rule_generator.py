"""
基于规则的 PyTOD 意图函数代码生成器。

本模块无需 LLM，仅根据意图名称前缀启发式推断语义类型，自动生成包含
真实计算逻辑的 Python 函数定义，作为 LLM 生成的兜底方案。

各意图前缀对应的生成策略：

+------------------------------+------------------------------------------+
| 意图前缀                     | 生成的计算逻辑                           |
+==============================+==========================================+
| complain_/dispute_           | 调用 _ticket_id() 生成工单号             |
+------------------------------+------------------------------------------+
| verify_/confirm_             | 依据必填参数是否存在推导布尔结果         |
+------------------------------+------------------------------------------+
| decline_/close_/end_         | 记录拒绝/结束状态，返回确认布尔值        |
+------------------------------+------------------------------------------+
| schedule_/book_              | 调用 _next_work_day() 计算回调时间       |
+------------------------------+------------------------------------------+
| inquire_/query_/check_       | 校验必填参数后返回语义化查询结果         |
+------------------------------+------------------------------------------+
| inform_/express_             | 记录信息并回传所有输入参数               |
+------------------------------+------------------------------------------+
| 其他                         | 必填参数校验 + 语义化返回值              |
+------------------------------+------------------------------------------+

公开 API
--------
``generate_function_lines(intent)``
    返回单个意图函数的源代码行列表。

``generate_generic_function_lines(schema)``
    当 schema 没有意图定义时，生成一个以 service_name 命名的通用函数。

``function_def_header(intent)``
    仅返回 ``def`` + docstring 两行（供 LLM 生成器使用）。
"""

from __future__ import annotations

from typing import List

from contextmind.modes.pytod.schemas import IntentDefinition, ServiceSchema


# ---------------------------------------------------------------------------
# 意图分类前缀元组
# ---------------------------------------------------------------------------

# 投诉/纠纷类意图前缀
_INTENT_COMPLAINT: tuple = (
    "complain_", "complaint_", "dispute_", "reject_", "appeal_",
)
# 核实/确认类意图前缀
_INTENT_VERIFY: tuple = (
    "verify_", "confirm_", "acknowledge_", "validate_",
)
# 拒绝/结束类意图前缀
_INTENT_DECLINE: tuple = (
    "decline_", "refuse_", "close_", "end_", "cancel_",
)
# 预约/排期类意图前缀
_INTENT_SCHEDULE: tuple = (
    "schedule_", "book_", "reserve_", "arrange_",
)
# 查询类意图前缀
_INTENT_INQUIRE: tuple = (
    "inquire_", "query_", "check_", "search_", "find_",
    "get_", "look_", "ask_",
)
# 告知/通知类意图前缀
_INTENT_INFORM: tuple = (
    "inform_", "express_", "suggest_", "notify_", "tell_",
)


# ---------------------------------------------------------------------------
# 公开函数
# ---------------------------------------------------------------------------

def generate_function_lines(intent: IntentDefinition) -> List[str]:
    """为单个意图生成含真实计算逻辑的 Python 函数定义行列表。

    根据意图名称前缀推断语义类型并选择对应的代码生成策略，
    所有生成的函数体均包含实际 Python 计算逻辑（非空 stub）。
    """
    params = list(dict.fromkeys(
        list(intent.required_slots) + list(intent.optional_slots)
    ))
    param_str = ", ".join([f"{p}=None" for p in params]) if params else ""
    intent_lower = intent.name.lower()
    desc = intent.description.replace('"', '\\"') if intent.description else intent.name

    # 构造 def 行和 docstring
    header = [
        f"def {intent.name}({param_str}):",
        f'    """{desc}"""',
    ]

    # 根据意图前缀选择函数体生成策略
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
    """schema 无意图定义时，生成一个以 service_name 命名的通用函数。"""
    slot_names = [s.name for s in schema.slots]
    param_str = ", ".join([f"{p}=None" for p in slot_names]) if slot_names else ""
    desc = schema.description.replace('"', '\\"') if schema.description else schema.service_name
    return [
        f"def {schema.service_name}({param_str}):",
        f'    """{desc}"""',
        f'    args = {{k: v for k, v in locals().items() if v is not None}}',
        f'    return {{"status": "success", **args}}',
    ]


def function_def_header(intent: IntentDefinition) -> List[str]:
    """返回函数 def 行 + docstring 行（不含函数体）。

    LLM 生成模式使用：def 行和 docstring 始终由本函数根据 schema 元数据生成，
    函数体由 LLM 提供，两者拼接后构成完整函数定义。
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
# 各意图语义体生成器（返回 4 空格缩进的函数体行列表）
# ---------------------------------------------------------------------------

def _echo_params(params: List[str]) -> List[str]:
    """将所有输入参数回传到返回字典（供 AP 通过 say(xN.slot) 引用）。"""
    return [f'        "{slot}": {slot},' for slot in params]


def _complaint_body(intent: IntentDefinition, params: List[str]) -> List[str]:
    """投诉/纠纷意图体：调用 _ticket_id() 生成工单号，返回受理信息。"""
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
    """核实/确认意图体：依据必填参数是否存在推导布尔结果。"""
    req = list(intent.required_slots)
    if req:
        # 所有必填槽位均不为 None 时操作才成功
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
        # 否定语义的 result_slot 取反
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
    """拒绝/结束意图体：记录操作并返回确认。"""
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
    """预约/排期意图体：调用 _next_work_day() 计算下一工作日作为回调时间。"""
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
    """查询意图体：校验必填参数后返回语义化查询结果。"""
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
    """告知/通知意图体：记录信息并回传所有输入参数。"""
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
    """为 result_slot 返回合理的 Python 字面量字符串（用于查询/通用意图）。"""
    name_lower = slot_name.lower()
    intent_lower = intent.name.lower()

    # 布尔类 result_slot
    if any(kw in name_lower for kw in (
        "verified", "confirmed", "declined", "acknowledged",
        "informed", "accepted", "approved", "suggested",
    )):
        is_negative = any(kw in name_lower for kw in ("declined", "rejected", "refused"))
        return "False" if is_negative else "True"

    # ID / 工单号类 slot
    if "complaint_id" in name_lower or name_lower.endswith("_id"):
        prefix = "".join(w[0].upper() for w in intent.name.split("_"))[:4]
        return f'"{prefix}-20240115-001"'

    if "number" in name_lower or "policy" in name_lower:
        return f'"{intent.name.upper()[:6]}-001"'

    # 状态类 slot — 按业务领域返回语义化值
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

    # 金额/额度类 slot
    if any(kw in name_lower for kw in ("amount", "quota", "limit", "balance", "fee", "price")):
        return '"5000元"'

    # 日期/时间类 slot
    if any(kw in name_lower for kw in ("date", "time", "datetime", "schedule")):
        return '"2024-01-15"'

    # 信息/内容/详情类 slot
    if any(kw in name_lower for kw in ("info", "detail", "content", "description", "data", "result")):
        return f'"[{intent.name}执行成功]"'

    # 利率/费率类 slot
    if any(kw in name_lower for kw in ("interest", "rate", "ratio")):
        return '"年利率7.2%"'

    # 查询类意图兜底
    if any(intent_lower.startswith(p) for p in ("inquire_", "query_", "check_", "search_", "find_")):
        if "status" in name_lower:
            return '"处理中"'
        if "amount" in name_lower or "limit" in name_lower:
            return '"5000元"'
        return f'"[{intent.name}查询结果]"'

    # 默认：以意图名称作为完成标记
    return f'"{intent.name}_completed"'
