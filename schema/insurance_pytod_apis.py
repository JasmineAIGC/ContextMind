"""
PyTOD API 函数集合 — 由 insurance_schema.json 生成
Service: Insurance_Sales
Generated at: 2026-03-27T08:04:28.947857+00:00
Generation mode: 规则引擎生成（含共享工具函数调用）

每个函数对应 schema 中的一个意图（intent），函数签名参数来自
required_slots + optional_slots，返回值包含 result_slots 字段。
文件头部定义了共享工具函数（_parse_amount、_ticket_id 等），
意图函数通过调用这些工具函数实现真实计算逻辑。
运行时通过 load_pytod_api_module() 加载并注册到 ExecutionEngine。
"""

from __future__ import annotations


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
        principal: 贷款本金（元）
        annual_rate: 年化利率（小数，如 0.24 表示 24%）
        months: 还款期数（月）
    """
    if principal <= 0 or months <= 0:
        return 0.0
    r = annual_rate / 12.0
    if r == 0:
        return principal / months
    return principal * r / (1.0 - (1.0 + r) ** (-months))


def _next_work_day() -> str:
    """返回下一个工作日日期字符串（格式 YYYY-MM-DD），跳过周末。"""
    d = _dt.date.today() + _dt.timedelta(days=1)
    while d.weekday() >= 5:   # 5=Saturday, 6=Sunday
        d += _dt.timedelta(days=1)
    return d.strftime("%Y-%m-%d")

def verify_member_identity(customer_age_range=None, customer_gender=None):
    """核实客户身份，确认是否为生活协同组合会员"""
    _ok = (customer_age_range is not None)
    return {
        "identity_verified": _ok,
        "customer_age_range": customer_age_range,
        "customer_gender": customer_gender,
        "status": "success",
    }

def introduce_product(insurance_type=None):
    """介绍团体癌症保险产品特点、保障范围及优惠政策"""
    return {
        "product_info": "[introduce_product执行成功]",
        "insurance_type": insurance_type,
        "status": "success",
    }

def calculate_premium(customer_age_range=None, customer_gender=None, budget_range=None):
    """计算保费，根据客户年龄、性别和选择的保额"""
    return {
        "premium_amount": "5000元",
        "customer_age_range": customer_age_range,
        "customer_gender": customer_gender,
        "budget_range": budget_range,
        "status": "success",
    }

def handle_objection(intent_level1=None, intent_level2=None, intent_level3=None):
    """处理客户异议，针对价格、必要性、信任等顾虑给出专业解答"""
    if not ((intent_level1 is not None)):
        return {"status": "error", "message": "缺少必填参数: intent_level1"}
    return {
        "objection_handled": "handle_objection_completed",
        "intent_level1": intent_level1,
        "intent_level2": intent_level2,
        "intent_level3": intent_level3,
        "status": "success",
    }

def compare_with_existing_insurance(has_insurance=None, has_cancer_insurance=None, insurance_type=None):
    """与客户现有保险对比，说明补充保障的价值"""
    return {
        "comparison_result": "[compare_with_existing_insurance执行成功]",
        "has_insurance": has_insurance,
        "has_cancer_insurance": has_cancer_insurance,
        "insurance_type": insurance_type,
        "status": "success",
    }

def schedule_callback(callback_needed=None, decision_maker=None):
    """安排后续回访时间，适用于客户需要考虑或与家人商量的情况"""
    _callback_time = _next_work_day() + ' 10:00'
    return {
        "callback_scheduled": _callback_time,
        "callback_needed": callback_needed,
        "decision_maker": decision_maker,
        "callback_time": _callback_time,
        "status": "success",
    }

def close_sale(customer_age_range=None, customer_gender=None, budget_range=None):
    """促成成交，引导客户完成电话投保流程"""
    return {
        "sale_completed": True,
        "customer_age_range": customer_age_range,
        "customer_gender": customer_gender,
        "budget_range": budget_range,
        "note": "操作已记录",
        "status": "success",
    }

def end_call_gracefully(callback_needed=None):
    """礼貌结束通话，适用于客户明确拒绝或当前不方便的情况"""
    return {
        "call_ended": True,
        "callback_needed": callback_needed,
        "note": "操作已记录",
        "status": "success",
    }

# ---------------------------------------------------------------------------
# INTENT_REGISTRY — intent 名称到函数的映射，供外部代码通过名称调用意图函数
# ---------------------------------------------------------------------------

INTENT_REGISTRY: dict = {
    "verify_member_identity": verify_member_identity,
    "introduce_product": introduce_product,
    "calculate_premium": calculate_premium,
    "handle_objection": handle_objection,
    "compare_with_existing_insurance": compare_with_existing_insurance,
    "schedule_callback": schedule_callback,
    "close_sale": close_sale,
    "end_call_gracefully": end_call_gracefully,
}
