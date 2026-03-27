"""
PyTOD API 函数集合 — 由 callcenter_schema.json 生成
Service: CallCenter_Service
Generated at: 2026-03-27T08:04:28.945520+00:00
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

def query_order_status(order_id=None):
    """查询订单状态，包括支付状态、发货状态和预计到达时间"""
    if not ((order_id is not None)):
        return {"status": "error", "message": "缺少必填参数: order_id"}
    return {
        "order_status": "已发货",
        "order_id": order_id,
        "status": "success",
    }

def submit_complaint(complaint_description=None, issue_type=None, order_id=None, product_name=None):
    """提交投诉，记录问题类型和详细描述"""
    if not ((complaint_description is not None)):
        return {"status": "error", "message": "缺少必填参数: complaint_description"}
    return {
        "complaint_id": "SC-20240115-001",
        "complaint_description": complaint_description,
        "issue_type": issue_type,
        "order_id": order_id,
        "product_name": product_name,
        "status": "success",
    }

def request_refund(order_id=None, refund_amount=None, complaint_description=None):
    """申请退款，支持全额和部分退款"""
    if not ((order_id is not None)):
        return {"status": "error", "message": "缺少必填参数: order_id"}
    return {
        "refund_status": "退款处理中",
        "order_id": order_id,
        "refund_amount": refund_amount,
        "complaint_description": complaint_description,
        "status": "success",
    }

def request_exchange(order_id=None, product_name=None, complaint_description=None):
    """申请换货，需要订单号和问题描述"""
    if not ((order_id is not None)):
        return {"status": "error", "message": "缺少必填参数: order_id"}
    return {
        "exchange_status": "换货处理中",
        "order_id": order_id,
        "product_name": product_name,
        "complaint_description": complaint_description,
        "status": "success",
    }

def track_logistics(tracking_number=None, order_id=None):
    """查询物流配送状态和快递轨迹"""
    if not ((tracking_number is not None)):
        return {"status": "error", "message": "缺少必填参数: tracking_number"}
    return {
        "logistics_status": "快递运输中",
        "tracking_number": tracking_number,
        "order_id": order_id,
        "status": "success",
    }

def reset_password(account_id=None):
    """重置账户密码，需要账户ID验证"""
    if not ((account_id is not None)):
        return {"status": "error", "message": "缺少必填参数: account_id"}
    return {
        "reset_status": "密码重置成功",
        "account_id": account_id,
        "status": "success",
    }

def update_account_info(account_id=None, new_email=None, new_phone=None):
    """修改账户信息，如邮箱、手机号等"""
    if not ((account_id is not None)):
        return {"status": "error", "message": "缺少必填参数: account_id"}
    return {
        "update_status": "信息更新成功",
        "account_id": account_id,
        "new_email": new_email,
        "new_phone": new_phone,
        "status": "success",
    }

def query_service_policy(product_name=None, service_type=None):
    """查询售后政策、退换货规则、质保期限等"""
    return {
        "policy_info": "QUERY_-001",
        "product_name": product_name,
        "service_type": service_type,
        "status": "success",
    }

def submit_feedback(feedback_content=None):
    """提交用户反馈或建议"""
    if not ((feedback_content is not None)):
        return {"status": "error", "message": "缺少必填参数: feedback_content"}
    return {
        "feedback_id": "SF-20240115-001",
        "feedback_content": feedback_content,
        "status": "success",
    }

# ---------------------------------------------------------------------------
# INTENT_REGISTRY — intent 名称到函数的映射，供外部代码通过名称调用意图函数
# ---------------------------------------------------------------------------

INTENT_REGISTRY: dict = {
    "query_order_status": query_order_status,
    "submit_complaint": submit_complaint,
    "request_refund": request_refund,
    "request_exchange": request_exchange,
    "track_logistics": track_logistics,
    "reset_password": reset_password,
    "update_account_info": update_account_info,
    "query_service_policy": query_service_policy,
    "submit_feedback": submit_feedback,
}
