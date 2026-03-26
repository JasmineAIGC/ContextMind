"""
PyTOD API 函数集合 — 由 insurance_schema.json 生成
Service: Insurance_Sales
Generated at: 2026-03-26T11:48:27.883006+00:00

每个函数对应 schema 中的一个意图（intent），函数签名参数来自
required_slots + optional_slots，返回值包含 result_slots 字段。
这些函数由 SchemaDataBuilder 预生成，运行时通过 load_pytod_api_module()
加载并注册到 ExecutionEngine，供 PyTOD AP 生成的程序调用。
"""

from __future__ import annotations

def verify_member_identity(customer_age_range=None, customer_gender=None):
    """核实客户身份，确认是否为生活协同组合会员"""
    return {
        "identity_verified": True,
        "status": "success",
    }

def introduce_product(insurance_type=None):
    """介绍团体癌症保险产品特点、保障范围及优惠政策"""
    return {
        "product_info": "[introduce_product 执行成功]",
        "status": "success",
    }

def calculate_premium(customer_age_range=None, customer_gender=None, budget_range=None):
    """计算保费，根据客户年龄、性别和选择的保额"""
    return {
        "premium_amount": "5000元",
        "status": "success",
    }

def handle_objection(intent_level1=None, intent_level2=None, intent_level3=None):
    """处理客户异议，针对价格、必要性、信任等顾虑给出专业解答"""
    return {
        "objection_handled": "handle_objection_completed",
        "status": "success",
    }

def compare_with_existing_insurance(has_insurance=None, has_cancer_insurance=None, insurance_type=None):
    """与客户现有保险对比，说明补充保障的价值"""
    return {
        "comparison_result": "[compare_with_existing_insurance 执行成功]",
        "status": "success",
    }

def schedule_callback(callback_needed=None, decision_maker=None):
    """安排后续回访时间，适用于客户需要考虑或与家人商量的情况"""
    return {
        "callback_scheduled": True,
        "status": "success",
    }

def close_sale(customer_age_range=None, customer_gender=None, budget_range=None):
    """促成成交，引导客户完成电话投保流程"""
    return {
        "sale_completed": True,
        "status": "success",
    }

def end_call_gracefully(callback_needed=None):
    """礼貌结束通话，适用于客户明确拒绝或当前不方便的情况"""
    return {
        "call_ended": True,
        "status": "success",
    }
