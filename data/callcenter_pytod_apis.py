"""
PyTOD API 函数集合 — 由 callcenter_schema.json 生成
Service: CallCenter_Service
Generated at: 2026-03-26T11:48:27.882215+00:00

每个函数对应 schema 中的一个意图（intent），函数签名参数来自
required_slots + optional_slots，返回值包含 result_slots 字段。
这些函数由 SchemaDataBuilder 预生成，运行时通过 load_pytod_api_module()
加载并注册到 ExecutionEngine，供 PyTOD AP 生成的程序调用。
"""

from __future__ import annotations

def query_order_status(order_id=None):
    """查询订单状态，包括支付状态、发货状态和预计到达时间"""
    return {
        "order_status": "success",
        "order_id": order_id,
        "status": "success",
    }

def submit_complaint(complaint_description=None, issue_type=None, order_id=None, product_name=None):
    """提交投诉，记录问题类型和详细描述"""
    return {
        "complaint_id": "SUBMIT_C-001",
        "order_id": order_id,
        "product_name": product_name,
        "status": "success",
    }

def request_refund(order_id=None, refund_amount=None, complaint_description=None):
    """申请退款，支持全额和部分退款"""
    return {
        "refund_status": "success",
        "order_id": order_id,
        "refund_amount": refund_amount,
        "status": "success",
    }

def request_exchange(order_id=None, product_name=None, complaint_description=None):
    """申请换货，需要订单号和问题描述"""
    return {
        "exchange_status": "success",
        "order_id": order_id,
        "product_name": product_name,
        "status": "success",
    }

def track_logistics(tracking_number=None, order_id=None):
    """查询物流配送状态和快递轨迹"""
    return {
        "logistics_status": "success",
        "tracking_number": tracking_number,
        "order_id": order_id,
        "status": "success",
    }

def reset_password(account_id=None):
    """重置账户密码，需要账户ID验证"""
    return {
        "reset_status": "success",
        "account_id": account_id,
        "status": "success",
    }

def update_account_info(account_id=None, new_email=None, new_phone=None):
    """修改账户信息，如邮箱、手机号等"""
    return {
        "update_status": "success",
        "account_id": account_id,
        "status": "success",
    }

def query_service_policy(product_name=None, service_type=None):
    """查询售后政策、退换货规则、质保期限等"""
    return {
        "policy_info": "QUERY_SE-001",
        "product_name": product_name,
        "status": "success",
    }

def submit_feedback(feedback_content=None):
    """提交用户反馈或建议"""
    return {
        "feedback_id": "SUBMIT_F-001",
        "status": "success",
    }
