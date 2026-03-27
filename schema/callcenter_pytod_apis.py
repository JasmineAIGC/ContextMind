"""
PyTOD API 函数集合 — 由 callcenter_schema.json 生成
Service: CallCenter_Service

每个函数对应 schema 中的一个意图（intent），函数签名参数来自
required_slots + optional_slots，返回值包含 result_slots 字段。
函数体包含真实业务逻辑（基于电商客服业务场景）。
这些函数由 SchemaDataBuilder 预生成，运行时通过 load_pytod_api_module()
加载并注册到 ExecutionEngine，供 PyTOD AP 生成的程序调用。
"""

from __future__ import annotations

import datetime
import hashlib


def _ticket_id(prefix: str) -> str:
    """生成工单/反馈编号，格式：{PREFIX}-YYYYMMDD-{hash4}。"""
    today = datetime.date.today().strftime("%Y%m%d")
    h = hashlib.md5(f"{prefix}{today}".encode()).hexdigest()[:4].upper()
    return f"{prefix}-{today}-{h}"


def query_order_status(order_id=None):
    """查询订单状态，包括支付状态、发货状态和预计到达时间"""
    if not order_id:
        return {"order_status": "未知", "order_id": order_id, "status": "error", "message": "缺少订单号"}
    # 根据订单号后缀模拟不同状态（实际场景中调用订单系统）
    suffix = str(order_id)[-1]
    status_map = {"0": "待付款", "1": "已付款", "2": "备货中", "3": "已发货",
                  "4": "运输中", "5": "派送中", "6": "已签收", "7": "已完成"}
    order_status = status_map.get(suffix, "已发货")
    eta = "预计明天送达" if order_status in ("已发货", "运输中", "派送中") else ""
    return {
        "order_status": order_status,
        "order_id": order_id,
        "estimated_delivery": eta,
        "status": "success",
    }


def submit_complaint(complaint_description=None, issue_type=None, order_id=None, product_name=None):
    """提交投诉，记录问题类型和详细描述"""
    complaint_id = _ticket_id("COMP")
    issue = issue_type or "其他"
    return {
        "complaint_id": complaint_id,
        "complaint_description": complaint_description,
        "issue_type": issue,
        "order_id": order_id,
        "product_name": product_name,
        "handling_days": 3,
        "note": f"投诉已受理（工单号：{complaint_id}），将在3个工作日内联系您处理",
        "status": "success",
    }


def request_refund(order_id=None, refund_amount=None, complaint_description=None):
    """申请退款，支持全额和部分退款"""
    if not order_id:
        return {"refund_status": "失败", "order_id": order_id, "status": "error", "message": "缺少订单号"}
    ticket = _ticket_id("RFND")
    amount_note = f"退款金额：{refund_amount}" if refund_amount else "全额退款"
    return {
        "refund_status": "退款申请已提交，审核中",
        "ticket_id": ticket,
        "order_id": order_id,
        "refund_amount": refund_amount,
        "complaint_description": complaint_description,
        "note": f"{amount_note}，预计3个工作日内原路退回",
        "status": "success",
    }


def request_exchange(order_id=None, product_name=None, complaint_description=None):
    """申请换货，需要订单号和问题描述"""
    if not order_id:
        return {"exchange_status": "失败", "order_id": order_id, "status": "error", "message": "缺少订单号"}
    ticket = _ticket_id("EXCH")
    return {
        "exchange_status": "换货申请已受理，等待快递上门取件",
        "ticket_id": ticket,
        "order_id": order_id,
        "product_name": product_name,
        "complaint_description": complaint_description,
        "note": "请保持手机畅通，快递员将在1-2个工作日内联系取件",
        "status": "success",
    }


def track_logistics(tracking_number=None, order_id=None):
    """查询物流配送状态和快递轨迹"""
    if not tracking_number:
        return {"logistics_status": "未知", "tracking_number": tracking_number, "status": "error", "message": "缺少运单号"}
    # 根据运单号末位模拟物流状态
    suffix = str(tracking_number)[-1] if tracking_number else "0"
    stage_map = {
        "0": "已揽件", "1": "已揽件", "2": "运输中", "3": "运输中",
        "4": "派送中", "5": "派送中", "6": "已签收", "7": "已签收",
        "8": "派件异常", "9": "快递柜存放中",
    }
    logistics_status = stage_map.get(suffix, "运输中")
    return {
        "logistics_status": logistics_status,
        "tracking_number": tracking_number,
        "order_id": order_id,
        "last_update": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "status": "success",
    }


def reset_password(account_id=None):
    """重置账户密码，需要账户ID验证"""
    if not account_id:
        return {"reset_status": "失败", "account_id": account_id, "status": "error", "message": "缺少账户ID"}
    return {
        "reset_status": "密码重置成功，临时密码已发送至绑定手机",
        "account_id": account_id,
        "note": "请在首次登录后立即修改密码，临时密码24小时内有效",
        "status": "success",
    }


def update_account_info(account_id=None, new_email=None, new_phone=None):
    """修改账户信息，如邮箱、手机号等"""
    if not account_id:
        return {"update_status": "失败", "account_id": account_id, "status": "error", "message": "缺少账户ID"}
    updated_fields = []
    if new_email:
        updated_fields.append(f"邮箱→{new_email}")
    if new_phone:
        masked_phone = "****" + new_phone[-4:] if len(new_phone) >= 4 else new_phone
        updated_fields.append(f"手机号→{masked_phone}")
    note = "已更新：" + "、".join(updated_fields) if updated_fields else "未指定更新字段"
    return {
        "update_status": "信息更新成功" if updated_fields else "无需更新",
        "account_id": account_id,
        "new_email": new_email,
        "new_phone": new_phone,
        "note": note,
        "status": "success",
    }


def query_service_policy(product_name=None, service_type=None):
    """查询售后政策、退换货规则、质保期限等"""
    policy_db = {
        "退货": "自收货之日起7天内无理由退货，商品需保持原包装完整",
        "换货": "自收货之日起15天内可申请换货，质量问题30天内均可处理",
        "保修": "电子产品1年保修，家用电器3年保修，消耗品不在保修范围",
        "发货": "订单付款后1-2个工作日内发货，节假日顺延",
    }
    stype = service_type or "退货"
    policy = policy_db.get(stype, "请拨打客服热线400-000-0000了解详细政策")
    product_note = f"（{product_name}）" if product_name else ""
    return {
        "policy_info": f"{stype}政策{product_note}：{policy}",
        "product_name": product_name,
        "service_type": service_type,
        "status": "success",
    }


def submit_feedback(feedback_content=None):
    """提交用户反馈或建议"""
    feedback_id = _ticket_id("FB")
    return {
        "feedback_id": feedback_id,
        "feedback_content": feedback_content,
        "note": f"感谢您的反馈（编号：{feedback_id}），我们将认真考虑您的建议",
        "status": "success",
    }
