"""
PyTOD 生成文件的共享工具函数模板。

``SHARED_HELPERS`` 常量会嵌入到每个生成的 ``*_pytod_apis.py`` 文件顶部附近。
它提供了若干工具函数（``_parse_amount``、``_ticket_id``、``_calc_monthly_payment``、
``_next_work_day``），同一模块中的所有意图函数均可直接调用，无需重复编写样板代码。
"""

# 嵌入到每个生成的 *_pytod_apis.py 文件顶部的工具函数模板字符串。
# 规则生成和 LLM 生成的意图函数都可以调用这些工具，避免重复代码。
SHARED_HELPERS = r'''
# ---------------------------------------------------------------------------
# 共享工具函数 — 由 SchemaDataBuilder 自动生成，所有 API 函数均可调用
# ---------------------------------------------------------------------------

import datetime as _dt
import math as _math
import re as _re


def _parse_amount(value) -> float:
    """将字符串金额（如 '21900元'、'两万一千九百'）解析为浮点数，无法解析时返回 0.0。"""
    if value is None:
        return 0.0
    s = _re.sub(r"[^\d.]", "", str(value).replace(",", "").replace("，", ""))
    try:
        return float(s)
    except ValueError:
        return 0.0


def _ticket_id(prefix: str = "TICKET") -> str:
    """生成工单编号，格式：{PREFIX}-YYYYMMDD-001。适用于投诉、申请、纠纷等意图。"""
    today = _dt.date.today().strftime("%Y%m%d")
    return f"{prefix}-{today}-001"


def _calc_monthly_payment(principal: float, annual_rate: float, months: int) -> float:
    """等额还款月供计算（PMT 公式）。

    Args:
        principal:   贷款本金（元）
        annual_rate: 年化利率（小数，如 0.24 表示 24%）
        months:      还款期数（月）
    """
    if principal <= 0 or months <= 0:
        return 0.0
    r = annual_rate / 12.0
    if r == 0:
        return principal / months
    return principal * r / (1.0 - (1.0 + r) ** (-months))


def _next_work_day() -> str:
    """返回下一个工作日日期字符串（格式 YYYY-MM-DD），跳过周末（周六/周日）。"""
    d = _dt.date.today() + _dt.timedelta(days=1)
    while d.weekday() >= 5:   # 5=周六, 6=周日（周一=0）
        d += _dt.timedelta(days=1)
    return d.strftime("%Y-%m-%d")

'''
