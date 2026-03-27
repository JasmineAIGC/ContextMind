"""
PyTOD API 函数集合 — 由 callcenter_schema.json 生成
Service: CallCenter_Service
Generated at: 2026-03-27T07:02:59.760756+00:00

每个函数对应 schema 中的一个意图（intent），函数签名参数来自
required_slots + optional_slots。函数体由 SchemaDataBuilder 规则引擎生成，
包含输入参数校验、工单号生成、布尔推导、回调时间计算等计算逻辑。

如需更贴近真实生产逻辑的函数体，请使用 LLM 模式重新生成：
  python examples/build_schema_data.py --with-llm
这些函数运行时通过 load_pytod_api_module() 加载并注册到 ExecutionEngine，
供 PyTOD AP 生成的程序调用。
"""

from __future__ import annotations

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
