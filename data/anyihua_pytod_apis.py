"""
PyTOD API 函数集合 — 由 anyihua_schema.json 生成
Service: AnYiHua_OutboundCall
Generated at: 2026-03-26T11:48:27.881706+00:00

每个函数对应 schema 中的一个意图（intent），函数签名参数来自
required_slots + optional_slots，返回值包含 result_slots 字段。
这些函数由 SchemaDataBuilder 预生成，运行时通过 load_pytod_api_module()
加载并注册到 ExecutionEngine，供 PyTOD AP 生成的程序调用。
"""

from __future__ import annotations

def confirm_terms(loan_amount=None, monthly_payment=None, current_credit_limit=None, total_interest=None, term_years=None, daily_interest=None, monthly_interest_amount=None):
    """确认账户额度和利息信息"""
    return {
        "confirmed_terms": True,
        "loan_amount": loan_amount,
        "current_credit_limit": current_credit_limit,
        "monthly_interest_amount": monthly_interest_amount,
        "status": "success",
    }

def verify_identity(account_usage_status=None):
    """坐席尝试核实用户身份"""
    return {
        "verified_identity": True,
        "status": "success",
    }

def complain_repayment_process(monthly_payment_amount=None):
    """用户认为还款流程过于繁琐或不便"""
    return {
        "complaint_repayment_process": "已记录，将在3个工作日内处理",
        "monthly_payment_amount": monthly_payment_amount,
        "status": "success",
    }

def complain_interest_rate(total_interest=None, daily_interest=None):
    """用户认为利率偏高"""
    return {
        "complaint_interest_rate": "已记录，将在3个工作日内处理",
        "status": "success",
    }

def confirm_awareness(temporary_credit_limit=None, current_credit_limit=None):
    """确认用户是否注意到额度变动或临时提额"""
    return {
        "confirmed_awareness": True,
        "temporary_credit_limit": temporary_credit_limit,
        "current_credit_limit": current_credit_limit,
        "status": "success",
    }

def dispute_loan(loan_date=None, loan_amount=None):
    """用户质疑存在未申请的贷款"""
    return {
        "disputed_loan": "已记录，将在3个工作日内处理",
        "loan_date": loan_date,
        "loan_amount": loan_amount,
        "status": "success",
    }

def confirm_borrowing_history(borrowing_date=None, loan_amount=None):
    """用户确认有借款记录"""
    return {
        "confirmed_borrowing_history": True,
        "borrowing_date": borrowing_date,
        "loan_amount": loan_amount,
        "status": "success",
    }

def decline_usage(current_credit_limit=None):
    """用户表示不敢使用额度"""
    return {
        "declined_usage": True,
        "current_credit_limit": current_credit_limit,
        "status": "success",
    }

def inquire_concerns_quota_interest(current_credit_limit=None, total_interest=None):
    """询问用户对额度和利息的顾虑"""
    return {
        "inquired_concerns": "inquire_concerns_quota_interest_completed",
        "current_credit_limit": current_credit_limit,
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
        "inquired_repayment_type": "inquire_repayment_type_completed",
        "monthly_payment_amount": monthly_payment_amount,
        "status": "success",
    }

def complain_repayment_difficulty(monthly_payment_amount=None):
    """用户表示还款金额过高，感到烦恼"""
    return {
        "complaint_repayment_difficulty": "已记录，将在3个工作日内处理",
        "monthly_payment_amount": monthly_payment_amount,
        "status": "success",
    }

def complain_monthly_payment(monthly_payment_amount=None):
    """用户抱怨每月还款金额过高，难以承担"""
    return {
        "complaint_monthly_payment": "已记录，将在3个工作日内处理",
        "monthly_payment_amount": monthly_payment_amount,
        "status": "success",
    }

def inquire_expected_interest_rate(total_interest=None):
    """询问用户期望的利息水平"""
    return {
        "inquired_expected_interest": "inquire_expected_interest_rate_completed",
        "status": "success",
    }

def inquire_annual_interest_rate(total_interest=None):
    """询问用户期望的年化利率"""
    return {
        "inquired_annual_interest": "inquire_annual_interest_rate_completed",
        "status": "success",
    }

def inform_credit_limit_increase(temporary_credit_limit=None):
    """告知用户临时提额情况"""
    return {
        "informed_credit_limit_increase": "5000元",
        "temporary_credit_limit": temporary_credit_limit,
        "status": "success",
    }

def confirm_application(application_date=None, loan_amount=None):
    """用户确认已申请贷款"""
    return {
        "confirmed_application": True,
        "application_date": application_date,
        "loan_amount": loan_amount,
        "status": "success",
    }

def complain_limit_denied(current_credit_limit=None, requested_amount=None):
    """用户抱怨额度被拒绝，认为应批准更高额度"""
    return {
        "complaint_limit_denied": "已记录，将在3个工作日内处理",
        "current_credit_limit": current_credit_limit,
        "requested_amount": requested_amount,
        "status": "success",
    }

def confirm_account_status(account_usage_status=None, temporary_credit_limit=None):
    """确认账户使用状态及提额情况"""
    return {
        "confirmed_account_status": True,
        "temporary_credit_limit": temporary_credit_limit,
        "status": "success",
    }

def inquire_amount_discrepancy(borrow_amount=None, actual_amount=None):
    """询问每次借款额度不一致的情况"""
    return {
        "inquired_amount_discrepancy": "5000元",
        "borrow_amount": borrow_amount,
        "actual_amount": actual_amount,
        "status": "success",
    }

def complain_discrepancy(requested_amount=None, actual_amount=None):
    """用户对申请金额与到账金额不一致表示不满"""
    return {
        "complaint_discrepancy": "已记录，将在3个工作日内处理",
        "requested_amount": requested_amount,
        "actual_amount": actual_amount,
        "status": "success",
    }

def suggest_contact_customer_service():
    """建议用户拨打客服热线95090咨询"""
    return {
        "suggested_contact_service": "suggest_contact_customer_service_completed",
        "status": "success",
    }
