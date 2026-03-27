"""
PyTOD API 函数集合 — 由 insurance_schema.json 生成
Service: Insurance_Sales

每个函数对应 schema 中的一个意图（intent），函数签名参数来自
required_slots + optional_slots，返回值包含 result_slots 字段。
函数体包含真实业务逻辑（基于团体癌症保险电话销售业务场景）。
这些函数由 SchemaDataBuilder 预生成，运行时通过 load_pytod_api_module()
加载并注册到 ExecutionEngine，供 PyTOD AP 生成的程序调用。

业务背景：生活协同组合团体癌症险电话外呼销售
- 产品：团体癌症险（含体检、确诊、住院三重保障）
- 目标客户：生活协同组合会员
"""

from __future__ import annotations

import datetime


# ---------------------------------------------------------------------------
# 保费计算基准表（年龄段 × 性别）
# ---------------------------------------------------------------------------

_PREMIUM_TABLE = {
    # (age_range, gender) → 月保费（元）
    ("18-30岁", "男"): 48,  ("18-30岁", "女"): 38,
    ("31-40岁", "男"): 68,  ("31-40岁", "女"): 58,
    ("41-50岁", "男"): 98,  ("41-50岁", "女"): 88,
    ("51-55岁", "男"): 138, ("51-55岁", "女"): 118,
    ("18-30", "男"): 48,    ("18-30", "女"): 38,
    ("31-40", "男"): 68,    ("31-40", "女"): 58,
    ("41-50", "男"): 98,    ("41-50", "女"): 88,
    ("51-55", "男"): 138,   ("51-55", "女"): 118,
}

_OBJECTION_RESPONSES = {
    "价格": "您好，这款产品月保费仅需几十元，相当于每天一杯咖啡的钱，却能提供癌症确诊、住院、体检三重保障，性价比非常高。",
    "必要性": "癌症是当前发病率最高的疾病之一，在中国每天有超过1万人被确诊。有了这份保障，万一发生时可获得现金补偿，减轻经济压力。",
    "信任": "本产品由持牌保险公司承保，受银保监会监管，理赔有保障。我们已为数十万会员提供服务，理赔率超过98%。",
    "时间": "您现在方便的话，办理只需5分钟，电话中确认基本信息即可完成投保。如果不方便，我们可以预约回访时间。",
    "已有保险": "您现有的保险可能不包含癌症专项保障，这款产品专为补充癌症风险设计，与现有保险互补不冲突，理赔互不影响。",
}


def verify_member_identity(customer_age_range=None, customer_gender=None):
    """核实客户身份，确认是否为生活协同组合会员"""
    is_verified = True  # 被呼叫的客户均为已验证会员
    age = customer_age_range or "未知"
    gender = customer_gender or "未知"
    return {
        "identity_verified": is_verified,
        "customer_age_range": customer_age_range,
        "customer_gender": customer_gender,
        "member_since": "会员资格有效",
        "eligible_for_product": True,
        "note": f"已核实：{age}{gender}会员，符合投保资格",
        "status": "success",
    }


def introduce_product(insurance_type=None):
    """介绍团体癌症保险产品特点、保障范围及优惠政策"""
    itype = insurance_type or "团体癌症险"
    product_info = (
        f"【{itype}产品介绍】\n"
        "✅ 三重保障：① 癌症确诊一次性赔付 ② 住院津贴每日补偿 ③ 年度防癌体检\n"
        "✅ 保障范围：100种恶性肿瘤，涵盖肺癌、乳腺癌、肠癌等高发癌症\n"
        "✅ 会员专属优惠：在原价基础上享受八折优惠\n"
        "✅ 投保便捷：电话确认，无需体检，即时生效\n"
        "✅ 理赔简便：确诊即赔，无等待期（已生效30天后）"
    )
    return {
        "product_info": product_info,
        "insurance_type": itype,
        "status": "success",
    }


def calculate_premium(customer_age_range=None, customer_gender=None, budget_range=None):
    """计算保费，根据客户年龄、性别和选择的保额"""
    age = customer_age_range or "31-40岁"
    gender = customer_gender or "男"
    # Look up base monthly premium
    base = _PREMIUM_TABLE.get((age, gender))
    if base is None:
        # Try without 岁 suffix
        age_key = age.replace("岁", "")
        base = _PREMIUM_TABLE.get((age_key, gender), 68)

    # Budget adjustment
    if budget_range:
        budget_str = str(budget_range).replace("元", "").replace("以内", "").strip()
        try:
            budget = float(budget_str)
            if budget < base:
                base = max(38, int(budget))  # floor at 38 yuan
        except ValueError:
            pass

    monthly = base
    annual = monthly * 12
    coverage = monthly * 100  # 理赔额约为月保费100倍

    return {
        "premium_amount": f"月保费{monthly}元（年缴{annual}元）",
        "monthly_premium": f"{monthly}元/月",
        "annual_premium": f"{annual}元/年",
        "estimated_coverage": f"癌症确诊赔付约{coverage}元",
        "customer_age_range": customer_age_range,
        "customer_gender": customer_gender,
        "budget_range": budget_range,
        "status": "success",
    }


def handle_objection(intent_level1=None, intent_level2=None, intent_level3=None):
    """处理客户异议，针对价格、必要性、信任等顾虑给出专业解答"""
    # Find best matching objection response
    keys = [intent_level1, intent_level2, intent_level3]
    response = None
    for key in keys:
        if key:
            for obj_key, obj_resp in _OBJECTION_RESPONSES.items():
                if obj_key in str(key):
                    response = obj_resp
                    break
        if response:
            break
    if not response:
        response = _OBJECTION_RESPONSES.get("必要性", "感谢您的顾虑，这款产品专为会员设计，性价比极高，我们可以详细介绍。")

    return {
        "objection_handled": response,
        "intent_level1": intent_level1,
        "intent_level2": intent_level2,
        "intent_level3": intent_level3,
        "status": "success",
    }


def compare_with_existing_insurance(has_insurance=None, has_cancer_insurance=None, insurance_type=None):
    """与客户现有保险对比，说明补充保障的价值"""
    if has_cancer_insurance and str(has_cancer_insurance).lower() not in ("false", "no", "否", "没有"):
        comparison_result = (
            "您已有癌症保险，可以检查是否包含住院津贴和年度体检。"
            "我们的产品作为补充，可以加强您的综合保障层次，双重理赔互不影响。"
        )
    elif has_insurance and str(has_insurance).lower() not in ("false", "no", "否", "没有"):
        itype = insurance_type or "商业险"
        comparison_result = (
            f"您的{itype}通常以重疾/医疗为主，而癌症险专项补充现金流，"
            "确诊即付，不需等待医疗报销结算，两者互补效果更佳。"
        )
    else:
        comparison_result = (
            "目前没有保险是很常见的情况，这款癌症险入门门槛低、保障实用，"
            "是开始建立个人保障体系的理想选择。"
        )
    return {
        "comparison_result": comparison_result,
        "has_insurance": has_insurance,
        "has_cancer_insurance": has_cancer_insurance,
        "insurance_type": insurance_type,
        "status": "success",
    }


def schedule_callback(callback_needed=None, decision_maker=None):
    """安排后续回访时间，适用于客户需要考虑或与家人商量的情况"""
    # Calculate next working day for callback
    today = datetime.date.today()
    callback_date = today + datetime.timedelta(days=1)
    while callback_date.weekday() >= 5:  # Skip weekend
        callback_date += datetime.timedelta(days=1)
    callback_time = f"{callback_date.strftime('%m月%d日')}上午10:00"
    dm_note = f"（可与{decision_maker}商议后确认）" if decision_maker else ""
    return {
        "callback_scheduled": True,
        "callback_time": callback_time,
        "callback_needed": callback_needed,
        "decision_maker": decision_maker,
        "note": f"已为您预约回访{dm_note}，届时专员将致电确认投保意向",
        "status": "success",
    }


def close_sale(customer_age_range=None, customer_gender=None, budget_range=None):
    """促成成交，引导客户完成电话投保流程"""
    age = customer_age_range or "未知年龄段"
    gender = customer_gender or "客户"
    # Get premium for context
    base = _PREMIUM_TABLE.get((age, gender))
    if base is None:
        age_key = age.replace("岁", "")
        base = _PREMIUM_TABLE.get((age_key, gender), 68)

    policy_number = f"POL-{datetime.date.today().strftime('%Y%m%d')}-{abs(hash(str(age)+str(gender)))%10000:04d}"
    return {
        "sale_completed": True,
        "policy_number": policy_number,
        "customer_age_range": customer_age_range,
        "customer_gender": customer_gender,
        "budget_range": budget_range,
        "monthly_premium": f"{base}元/月",
        "effective_date": (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d"),
        "note": f"恭喜您成功投保！保单号：{policy_number}，次日零时起生效",
        "status": "success",
    }


def end_call_gracefully(callback_needed=None):
    """礼貌结束通话，适用于客户明确拒绝或当前不方便的情况"""
    has_callback = callback_needed and str(callback_needed).lower() not in ("false", "no", "否", "不需要")
    note = (
        "好的，我们将在您方便时再次联系，感谢您的耐心，祝您生活愉快！"
        if has_callback
        else "好的，打扰您了，如果将来有需要可随时联系我们，祝您身体健康！"
    )
    return {
        "call_ended": True,
        "callback_needed": callback_needed,
        "note": note,
        "status": "success",
    }
