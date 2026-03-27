"""
PyTOD API 函数集合 — 由 anyihua_schema.json 生成
Service: AnYiHua_OutboundCall
Generated at: 2026-03-27T01:28:29.512587+00:00

每个函数对应 schema 中的一个意图（intent），函数签名参数来自
required_slots + optional_slots，返回值包含 result_slots 字段。
这些函数由 SchemaDataBuilder 预生成，运行时通过 load_pytod_api_module()
加载并注册到 ExecutionEngine，供 PyTOD AP 生成的程序调用。

业务背景：安逸花外呼促活服务
- 产品：安逸花（马上消费金融）贷款产品
- 流程：核实身份 → 告知额度/利率 → 解答疑问 → 引导借款
- 年化利率：24%（日利率约 0.065%，月利率约 2%）
- 客服热线：95090
"""

from __future__ import annotations

import datetime
import math


# ---------------------------------------------------------------------------
# 内部工具函数
# ---------------------------------------------------------------------------

def _parse_amount(value) -> float:
    """将字符串金额（如 '21900元'、'5000'）解析为浮点数，无法解析时返回 0.0。
    注意：仅处理阿拉伯数字+常见金额后缀，不处理汉字数字（如'两万'）。
    """
    if value is None:
        return 0.0
    s = str(value).strip().replace(",", "").replace("，", "")
    # 移除常见金额后缀
    for suffix in ("元", "万元", "千元", "百元"):
        s = s.replace(suffix, "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_years(value) -> float:
    """将贷款期限字符串（如 '1'、'2年'、'24个月'）解析为年数。"""
    if value is None:
        return 0.0
    s = str(value).strip()
    # 处理月份表示，如 '12个月' → 1 年
    import re as _re
    m_months = _re.search(r"(\d+(?:\.\d+)?)\s*(?:个)?月", s)
    if m_months:
        return float(m_months.group(1)) / 12
    m_years = _re.search(r"(\d+(?:\.\d+)?)", s)
    if m_years:
        return float(m_years.group(1))
    return 0.0


def _calculate_monthly_payment(principal: float, annual_rate: float, months: int) -> float:
    """等额还款月供计算（PMT 公式）。"""
    if principal <= 0 or months <= 0:
        return 0.0
    monthly_rate = annual_rate / 12
    if monthly_rate == 0:
        return principal / months
    return principal * monthly_rate / (1 - (1 + monthly_rate) ** (-months))


def _complaint_ticket(prefix: str) -> str:
    """生成投诉工单编号，格式：{PREFIX}-YYYYMMDD-XXX。"""
    today = datetime.date.today().strftime("%Y%m%d")
    return f"{prefix}-{today}-001"


# ---------------------------------------------------------------------------
# API 函数定义
# ---------------------------------------------------------------------------

def confirm_terms(loan_amount=None, monthly_payment=None, current_credit_limit=None, total_interest=None, term_years=None, daily_interest=None, monthly_interest_amount=None):
    """确认账户额度和利息信息"""
    # 标准年化利率 24%
    ANNUAL_RATE = 0.24
    DAILY_RATE = ANNUAL_RATE / 365

    principal = _parse_amount(loan_amount)
    years = _parse_years(term_years) if term_years else 1.0
    months = max(1, round(years * 12))

    if principal > 0:
        mp = _calculate_monthly_payment(principal, ANNUAL_RATE, months)
        total_int = mp * months - principal
        d_interest = principal * DAILY_RATE

        if not monthly_payment:
            monthly_payment = f"{mp:.0f}元"
        if not total_interest:
            total_interest = f"{total_int:.0f}元"
        if not daily_interest:
            daily_interest = f"{d_interest:.2f}元/天"
        if not monthly_interest_amount:
            monthly_interest_amount = f"{principal * ANNUAL_RATE / 12:.0f}元/月"

    return {
        "confirmed_terms": True,
        "loan_amount": loan_amount,
        "monthly_payment": monthly_payment,
        "current_credit_limit": current_credit_limit,
        "total_interest": total_interest,
        "term_years": term_years,
        "daily_interest": daily_interest,
        "monthly_interest_amount": monthly_interest_amount,
        "annual_rate": "24%",
        "status": "success",
    }

def verify_identity(account_usage_status=None):
    """坐席尝试核实用户身份"""
    status = account_usage_status or "正常使用中"
    # 账户处于正常/使用中时核实通过
    is_verified = any(kw in str(status) for kw in ("正常", "使用", "active", "ok"))
    return {
        "verified_identity": is_verified,
        "account_usage_status": status,
        "verification_method": "电话核实",
        "customer_service_hotline": "95090",
        "status": "success",
    }

def complain_repayment_process(monthly_payment_amount=None):
    """用户认为还款流程过于繁琐或不便"""
    ticket = _complaint_ticket("COMP-PROC")
    return {
        "complaint_repayment_process": "已记录，将在3个工作日内处理",
        "ticket_id": ticket,
        "monthly_payment_amount": monthly_payment_amount,
        "handling_days": 3,
        "status": "success",
    }

def complain_interest_rate(total_interest=None, daily_interest=None):
    """用户认为利率偏高"""
    ticket = _complaint_ticket("COMP-RATE")
    return {
        "complaint_interest_rate": "已记录，将在3个工作日内处理",
        "ticket_id": ticket,
        "total_interest": total_interest,
        "daily_interest": daily_interest,
        "reference_annual_rate": "24%",
        "handling_days": 3,
        "status": "success",
    }

def confirm_awareness(temporary_credit_limit=None, current_credit_limit=None):
    """确认用户是否注意到额度变动或临时提额"""
    is_aware = temporary_credit_limit is not None or current_credit_limit is not None
    return {
        "confirmed_awareness": is_aware,
        "temporary_credit_limit": temporary_credit_limit,
        "current_credit_limit": current_credit_limit,
        "note": "临时额度到期后将自动恢复原额度" if temporary_credit_limit else "",
        "status": "success",
    }

def dispute_loan(loan_date=None, loan_amount=None):
    """用户质疑存在未申请的贷款"""
    ticket = _complaint_ticket("DISP-LOAN")
    return {
        "disputed_loan": "已记录，将在3个工作日内处理",
        "ticket_id": ticket,
        "loan_date": loan_date,
        "loan_amount": loan_amount,
        "investigation_result": "正在核查，如确认非本人操作将全额退款",
        "handling_days": 3,
        "status": "success",
    }

def confirm_borrowing_history(borrowing_date=None, loan_amount=None):
    """用户确认有借款记录"""
    return {
        "confirmed_borrowing_history": True,
        "borrowing_date": borrowing_date,
        "loan_amount": loan_amount,
        "repayment_reminder": "请注意按时还款，逾期将影响信用记录",
        "status": "success",
    }

def decline_usage(current_credit_limit=None):
    """用户表示不敢使用额度"""
    return {
        "declined_usage": True,
        "current_credit_limit": current_credit_limit,
        "suggestion": "额度随时可用，资金周转需要时欢迎致电95090或在APP内申请",
        "status": "success",
    }

def inquire_concerns_quota_interest(current_credit_limit=None, total_interest=None):
    """询问用户对额度和利息的顾虑"""
    # 基于传入的额度和利息构建具体说明
    limit_info = f"当前额度{current_credit_limit}" if current_credit_limit else "当前额度可满足日常资金需求"
    interest_info = f"总利息{total_interest}" if total_interest else "年化利率24%，按日计息"
    return {
        "inquired_concerns": f"{limit_info}；{interest_info}，如有顾虑可拨打95090咨询",
        "current_credit_limit": current_credit_limit,
        "total_interest": total_interest,
        "annual_rate": "24%",
        "daily_rate": "0.065%",
        "status": "success",
    }

def express_future_intent(loan_limit=None):
    """表达未来可能有借款需求并希望长期合作"""
    return {
        "expressed_future_intent": True,
        "loan_limit": loan_limit,
        "note": "已记录您的借款意向，额度随时为您保留，有需要随时通过APP或95090申请",
        "status": "success",
    }

def inquire_repayment_type(monthly_payment_amount=None):
    """询问具体是哪种还款方式（如提前还款等）"""
    repayment_info = f"每月固定还款{monthly_payment_amount}" if monthly_payment_amount else "等额还款方式"
    return {
        "inquired_repayment_type": f"{repayment_info}；支持提前还款（无违约金）、随借随还",
        "monthly_payment_amount": monthly_payment_amount,
        "repayment_options": ["等额还款", "提前还款", "随借随还"],
        "status": "success",
    }

def complain_repayment_difficulty(monthly_payment_amount=None):
    """用户表示还款金额过高，感到烦恼"""
    ticket = _complaint_ticket("COMP-DIFF")
    return {
        "complaint_repayment_difficulty": "已记录，将在3个工作日内处理",
        "ticket_id": ticket,
        "monthly_payment_amount": monthly_payment_amount,
        "suggestion": "如还款困难，可拨打95090申请分期调整方案",
        "handling_days": 3,
        "status": "success",
    }

def complain_monthly_payment(monthly_payment_amount=None):
    """用户抱怨每月还款金额过高，难以承担"""
    ticket = _complaint_ticket("COMP-PAY")
    return {
        "complaint_monthly_payment": "已记录，将在3个工作日内处理",
        "ticket_id": ticket,
        "monthly_payment_amount": monthly_payment_amount,
        "suggestion": "可拨打客服热线95090申请延期还款或还款计划调整",
        "handling_days": 3,
        "status": "success",
    }

def inquire_expected_interest_rate(total_interest=None):
    """询问用户期望的利息水平"""
    return {
        "inquired_expected_interest": "当前产品年化利率24%（日利率0.065%），如有更低利率诉求可拨打95090咨询",
        "current_annual_rate": "24%",
        "current_daily_rate": "0.065%",
        "total_interest": total_interest,
        "status": "success",
    }

def inquire_annual_interest_rate(total_interest=None):
    """询问用户期望的年化利率"""
    return {
        "inquired_annual_interest": "年化利率24%（等额还款，按日计息）",
        "annual_rate": "24%",
        "monthly_rate": "2%",
        "daily_rate": "0.065%",
        "total_interest": total_interest,
        "status": "success",
    }

def inform_credit_limit_increase(temporary_credit_limit=None):
    """告知用户临时提额情况"""
    limit = temporary_credit_limit or "临时提额"
    return {
        "informed_credit_limit_increase": True,
        "temporary_credit_limit": temporary_credit_limit,
        "note": f"您已获得{limit}临时额度，请在有效期内使用，到期后自动恢复原额度",
        "status": "success",
    }

def confirm_application(application_date=None, loan_amount=None):
    """用户确认已申请贷款"""
    return {
        "confirmed_application": True,
        "application_date": application_date,
        "loan_amount": loan_amount,
        "next_step": "贷款审核通常在1个工作日内完成，审核通过后资金将自动到账",
        "status": "success",
    }

def complain_limit_denied(current_credit_limit=None, requested_amount=None):
    """用户抱怨额度被拒绝，认为应批准更高额度"""
    ticket = _complaint_ticket("COMP-LMTD")
    return {
        "complaint_limit_denied": "已记录，将在3个工作日内处理",
        "ticket_id": ticket,
        "current_credit_limit": current_credit_limit,
        "requested_amount": requested_amount,
        "explanation": "额度由系统根据信用评分综合评定，后续持续保持良好信用记录可申请提额",
        "handling_days": 3,
        "status": "success",
    }

def confirm_account_status(account_usage_status=None, temporary_credit_limit=None):
    """确认账户使用状态及提额情况"""
    status = account_usage_status or "正常使用中"
    has_temp = temporary_credit_limit is not None
    return {
        "confirmed_account_status": True,
        "account_usage_status": status,
        "temporary_credit_limit": temporary_credit_limit,
        "has_temporary_limit": has_temp,
        "note": "账户状态正常，额度随时可用" if "正常" in str(status) else f"账户状态：{status}",
        "status": "success",
    }

def inquire_amount_discrepancy(borrow_amount=None, actual_amount=None):
    """询问每次借款额度不一致的情况"""
    ticket = _complaint_ticket("INQU-DISC")
    return {
        "inquired_amount_discrepancy": "到账金额与借款金额差异可能由手续费或提现费率不同导致",
        "ticket_id": ticket,
        "borrow_amount": borrow_amount,
        "actual_amount": actual_amount,
        "explanation": "实际到账金额=借款金额-相关费用，如有疑问请拨打95090核实",
        "status": "success",
    }

def complain_discrepancy(requested_amount=None, actual_amount=None):
    """用户对申请金额与到账金额不一致表示不满"""
    ticket = _complaint_ticket("COMP-DISC")
    return {
        "complaint_discrepancy": "已记录，将在3个工作日内处理",
        "ticket_id": ticket,
        "requested_amount": requested_amount,
        "actual_amount": actual_amount,
        "explanation": "正在核查到账差异原因，如确认有误将全额退还差额",
        "handling_days": 3,
        "status": "success",
    }

def suggest_contact_customer_service():
    """建议用户拨打客服热线95090咨询"""
    return {
        "suggested_contact_service": True,
        "customer_service_hotline": "95090",
        "service_hours": "7×24小时",
        "note": "如有任何问题，可随时拨打95090客服热线，专业团队为您解答",
        "status": "success",
    }
