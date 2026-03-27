"""
PyTOD API 函数集合 — 由 anyihua_schema.json 生成
Service: AnYiHua_OutboundCall
Generated at: 2026-03-27T08:04:28.943753+00:00
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

def confirm_terms(loan_amount=None, monthly_payment=None, current_credit_limit=None, total_interest=None, term_years=None, daily_interest=None, monthly_interest_amount=None):
    """确认账户额度和利息信息"""
    _ok = bool((loan_amount is not None) and (monthly_payment is not None) and (current_credit_limit is not None) and (total_interest is not None))
    return {
        "confirmed_terms": _ok,
        "loan_amount": loan_amount,
        "monthly_payment": monthly_payment,
        "current_credit_limit": current_credit_limit,
        "total_interest": total_interest,
        "term_years": term_years,
        "daily_interest": daily_interest,
        "monthly_interest_amount": monthly_interest_amount,
        "status": "success",
    }

def verify_identity(account_usage_status=None):
    """坐席尝试核实用户身份"""
    _ok = bool((account_usage_status is not None))
    return {
        "verified_identity": _ok,
        "account_usage_status": account_usage_status,
        "status": "success",
    }

def complain_repayment_process(monthly_payment_amount=None):
    """用户认为还款流程过于繁琐或不便"""
    _ticket = _ticket_id('COMPLAIN')
    return {
        "complaint_repayment_process": "已受理，将在3个工作日内处理",
        "monthly_payment_amount": monthly_payment_amount,
        "ticket_id": _ticket,
        "handling_days": 3,
        "status": "success",
    }

def complain_interest_rate(total_interest=None, daily_interest=None):
    """用户认为利率偏高"""
    _ticket = _ticket_id('COMPLAIN')
    return {
        "complaint_interest_rate": "已受理，将在3个工作日内处理",
        "total_interest": total_interest,
        "daily_interest": daily_interest,
        "ticket_id": _ticket,
        "handling_days": 3,
        "status": "success",
    }

def confirm_awareness(temporary_credit_limit=None, current_credit_limit=None):
    """确认用户是否注意到额度变动或临时提额"""
    _ok = bool((temporary_credit_limit is not None) and (current_credit_limit is not None))
    return {
        "confirmed_awareness": _ok,
        "temporary_credit_limit": temporary_credit_limit,
        "current_credit_limit": current_credit_limit,
        "status": "success",
    }

def dispute_loan(loan_date=None, loan_amount=None):
    """用户质疑存在未申请的贷款"""
    _ticket = _ticket_id('DISPUTE')
    return {
        "disputed_loan": "已受理，将在3个工作日内处理",
        "loan_date": loan_date,
        "loan_amount": loan_amount,
        "ticket_id": _ticket,
        "handling_days": 3,
        "status": "success",
    }

def confirm_borrowing_history(borrowing_date=None, loan_amount=None):
    """用户确认有借款记录"""
    _ok = bool((borrowing_date is not None) and (loan_amount is not None))
    return {
        "confirmed_borrowing_history": _ok,
        "borrowing_date": borrowing_date,
        "loan_amount": loan_amount,
        "status": "success",
    }

def decline_usage(current_credit_limit=None):
    """用户表示不敢使用额度"""
    return {
        "declined_usage": True,
        "current_credit_limit": current_credit_limit,
        "note": "操作已记录",
        "status": "success",
    }

def inquire_concerns_quota_interest(current_credit_limit=None, total_interest=None):
    """询问用户对额度和利息的顾虑"""
    return {
        "inquired_concerns": "[inquire_concerns_quota_interest查询结果]",
        "current_credit_limit": current_credit_limit,
        "total_interest": total_interest,
        "status": "success",
    }

def express_future_intent(loan_limit=None):
    """表达未来可能有借款需求并希望长期合作"""
    return {
        "expressed_future_intent": True,
        "loan_limit": loan_limit,
        "status": "success",
    }

def inquire_repayment_type(monthly_payment_amount=None):
    """询问具体是哪种还款方式（如提前还款等）"""
    return {
        "inquired_repayment_type": "[inquire_repayment_type查询结果]",
        "monthly_payment_amount": monthly_payment_amount,
        "status": "success",
    }

def complain_repayment_difficulty(monthly_payment_amount=None):
    """用户表示还款金额过高，感到烦恼"""
    _ticket = _ticket_id('COMPLAIN')
    return {
        "complaint_repayment_difficulty": "已受理，将在3个工作日内处理",
        "monthly_payment_amount": monthly_payment_amount,
        "ticket_id": _ticket,
        "handling_days": 3,
        "status": "success",
    }

def complain_monthly_payment(monthly_payment_amount=None):
    """用户抱怨每月还款金额过高，难以承担"""
    _ticket = _ticket_id('COMPLAIN')
    return {
        "complaint_monthly_payment": "已受理，将在3个工作日内处理",
        "monthly_payment_amount": monthly_payment_amount,
        "ticket_id": _ticket,
        "handling_days": 3,
        "status": "success",
    }

def inquire_expected_interest_rate(total_interest=None):
    """询问用户期望的利息水平"""
    return {
        "inquired_expected_interest": "年利率7.2%",
        "total_interest": total_interest,
        "status": "success",
    }

def inquire_annual_interest_rate(total_interest=None):
    """询问用户期望的年化利率"""
    return {
        "inquired_annual_interest": "年利率7.2%",
        "total_interest": total_interest,
        "status": "success",
    }

def inform_credit_limit_increase(temporary_credit_limit=None):
    """告知用户临时提额情况"""
    return {
        "informed_credit_limit_increase": True,
        "temporary_credit_limit": temporary_credit_limit,
        "status": "success",
    }

def confirm_application(application_date=None, loan_amount=None):
    """用户确认已申请贷款"""
    _ok = bool((application_date is not None) and (loan_amount is not None))
    return {
        "confirmed_application": _ok,
        "application_date": application_date,
        "loan_amount": loan_amount,
        "status": "success",
    }

def complain_limit_denied(current_credit_limit=None, requested_amount=None):
    """用户抱怨额度被拒绝，认为应批准更高额度"""
    _ticket = _ticket_id('COMPLAIN')
    return {
        "complaint_limit_denied": "已受理，将在3个工作日内处理",
        "current_credit_limit": current_credit_limit,
        "requested_amount": requested_amount,
        "ticket_id": _ticket,
        "handling_days": 3,
        "status": "success",
    }

def confirm_account_status(account_usage_status=None, temporary_credit_limit=None):
    """确认账户使用状态及提额情况"""
    _ok = bool((account_usage_status is not None) and (temporary_credit_limit is not None))
    return {
        "confirmed_account_status": _ok,
        "account_usage_status": account_usage_status,
        "temporary_credit_limit": temporary_credit_limit,
        "status": "success",
    }

def inquire_amount_discrepancy(borrow_amount=None, actual_amount=None):
    """询问每次借款额度不一致的情况"""
    if not ((borrow_amount is not None) and (actual_amount is not None)):
        return {"status": "error", "message": "缺少必填参数: borrow_amount, actual_amount"}
    return {
        "inquired_amount_discrepancy": "5000元",
        "borrow_amount": borrow_amount,
        "actual_amount": actual_amount,
        "status": "success",
    }

def complain_discrepancy(requested_amount=None, actual_amount=None):
    """用户对申请金额与到账金额不一致表示不满"""
    _ticket = _ticket_id('COMPLAIN')
    return {
        "complaint_discrepancy": "已受理，将在3个工作日内处理",
        "requested_amount": requested_amount,
        "actual_amount": actual_amount,
        "ticket_id": _ticket,
        "handling_days": 3,
        "status": "success",
    }

def suggest_contact_customer_service():
    """建议用户拨打客服热线95090咨询"""
    return {
        "suggested_contact_service": True,
        "status": "success",
    }

# ---------------------------------------------------------------------------
# INTENT_REGISTRY — intent 名称到函数的映射，供外部代码通过名称调用意图函数
# ---------------------------------------------------------------------------

INTENT_REGISTRY: dict = {
    "confirm_terms": confirm_terms,
    "verify_identity": verify_identity,
    "complain_repayment_process": complain_repayment_process,
    "complain_interest_rate": complain_interest_rate,
    "confirm_awareness": confirm_awareness,
    "dispute_loan": dispute_loan,
    "confirm_borrowing_history": confirm_borrowing_history,
    "decline_usage": decline_usage,
    "inquire_concerns_quota_interest": inquire_concerns_quota_interest,
    "express_future_intent": express_future_intent,
    "inquire_repayment_type": inquire_repayment_type,
    "complain_repayment_difficulty": complain_repayment_difficulty,
    "complain_monthly_payment": complain_monthly_payment,
    "inquire_expected_interest_rate": inquire_expected_interest_rate,
    "inquire_annual_interest_rate": inquire_annual_interest_rate,
    "inform_credit_limit_increase": inform_credit_limit_increase,
    "confirm_application": confirm_application,
    "complain_limit_denied": complain_limit_denied,
    "confirm_account_status": confirm_account_status,
    "inquire_amount_discrepancy": inquire_amount_discrepancy,
    "complain_discrepancy": complain_discrepancy,
    "suggest_contact_customer_service": suggest_contact_customer_service,
}
