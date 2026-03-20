"""
PyTOD 场景 API 注册表

为各内置场景（闲聊、客服、保险）提供演示 API 函数的注册逻辑，
以及按场景名称查找注册函数的辅助工具。

扩展方法：
    1. 在本文件中定义新的 ``_register_<scenario>_apis(engine)`` 函数
    2. 将场景名称映射添加到 ``SCENARIO_API_REGISTRY``

本模块与 ``PyTODTracker`` 解耦：追踪器无需关心 API 实现细节，
只需调用 ``get_scenario_key`` + ``SCENARIO_API_REGISTRY`` 完成注册。
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

from .execution_engine import ExecutionEngine


# ---------------------------------------------------------------------------
# 闲聊场景 API
# ---------------------------------------------------------------------------

def _register_chat_apis(engine: ExecutionEngine) -> None:
    """为闲聊场景注册演示 API 函数。"""

    @engine.register
    def get_weather(city=None, date=None):
        """查询天气预报。支持今天/明天/后天，或指定城市。"""
        if not city:
            return {"hint": "请提供城市名称"}
        weather_map = {
            "北京": {"condition": "晴", "temp_high": 12, "temp_low": 2, "wind": "西北风3级"},
            "上海": {"condition": "多云", "temp_high": 16, "temp_low": 8, "wind": "东南风2级"},
            "广州": {"condition": "小雨", "temp_high": 22, "temp_low": 15, "wind": "南风1级"},
        }
        w = weather_map.get(city, {"condition": "晴转多云", "temp_high": 15, "temp_low": 5, "wind": "微风"})
        return {
            "city": city,
            "date": date or "今天",
            "condition": w["condition"],
            "temp_high": w["temp_high"],
            "temp_low": w["temp_low"],
            "wind": w["wind"],
            "message": f"{city}{date or '今天'}天气：{w['condition']}，{w['temp_low']}~{w['temp_high']}℃，{w['wind']}",
        }

    @engine.register
    def search_info(query=None, category=None):
        """搜索信息或回答知识类问题。category 可选：news（新闻）、wiki（百科）、general（通用）。"""
        if not query:
            return {"hint": "请提供搜索关键词"}
        return {
            "query": query,
            "category": category or "general",
        }

    @engine.register
    def tell_joke(topic=None):
        """讲一个笑话。topic 可选：程序员、数学、生活、动物。"""
        jokes = {
            "程序员": "一个程序员妻子让他去超市：'买一斤鸡蛋，如果有苹果就买两斤。'程序员回来带了两斤鸡蛋，因为超市有苹果。",
            "数学": "老师问：x = 1 的话，x + x 等于几？学生答：等于 2 + 2，老师问为什么？学生说：因为 x = 1，所以 2x = 2。",
            "生活": "闹钟响了，我问自己：'再睡五分钟？'自己说：'好的。'——三小时后，我迟到了。",
            "动物": "狗对猫说：'你喜欢主人吗？'猫说：'喜欢。'狗问：'那你为什么总是无视他？'猫说：'因为这样他才会更宠我。'",
        }
        joke_text = jokes.get(topic, jokes.get("生活"))
        return {"topic": topic or "生活", "joke": joke_text}

    @engine.register
    def translate_text(text=None, target_language=None, source_language=None):
        """翻译文本。target_language 为目标语言（中文/英文/日文/韩文等）。"""
        if not text:
            return {"hint": "请提供要翻译的文本"}
        if not target_language:
            return {"hint": "请提供目标语言"}
        return {
            "original": text,
            "source_language": source_language or "自动检测",
            "target_language": target_language,
        }

    @engine.register
    def calculate(expression=None):
        """计算数学表达式。支持加减乘除、百分比等基础运算。"""
        if not expression:
            return {"hint": "请提供计算表达式，如：100*0.85 或 1200/12"}
        try:
            # 只允许数字和安全运算符
            import re as _re
            safe = _re.sub(r'[^0-9+\-*/.() %]', '', str(expression))
            result = eval(safe)  # nosec — expression filtered to safe chars only
            return {"expression": expression, "result": result, "message": f"{expression} = {result}"}
        except Exception:
            return {"expression": expression, "error": "表达式格式有误，请检查后重试"}


# ---------------------------------------------------------------------------
# 客服场景 API
# ---------------------------------------------------------------------------

def _register_callcenter_apis(engine: ExecutionEngine) -> None:
    """为客服场景注册演示 API 函数。"""

    @engine.register
    def lookup_order(order_id=None, customer_id=None, product_name=None, purchase_date=None):
        """查询订单信息。支持按订单号、客户ID、商品名称或购买日期查询。"""
        if not any([order_id, customer_id, product_name, purchase_date]):
            return {"error": "请提供至少一项查询条件：订单号、客户ID、商品名称或购买日期"}
        oid = order_id or "ORD-20260220-8851"
        return {
            "order_id": oid,
            "product_name": product_name or "智能扫地机器人",
            "purchase_date": purchase_date or "2026-02-20",
            "status": "已发货",
            "shipping_date": "2026-02-21",
            "estimated_delivery": "2026-02-28",
            "carrier": "顺丰快递",
            "tracking_number": f"SF{oid[-10:].replace('-', '')}",
        }

    @engine.register
    def submit_complaint(complaint_type=None, description=None, order_id=None, urgency=None):
        """提交投诉或反馈。适用于服务不满意、产品问题、物流问题等场景。"""
        urgency_map = {"高": "12小时内", "紧急": "4小时内"}
        return {
            "ticket_id": "CMP-20260226-5842",
            "complaint_type": complaint_type or "服务投诉",
            "description_received": bool(description),
            "order_id": order_id,
            "urgency": urgency or "普通",
            "status": "已受理",
            "expected_response_time": urgency_map.get(urgency or "", "24小时内"),
        }

    @engine.register
    def process_refund(order_id=None, reason=None, amount=None, product_name=None):
        """申请退款。需要提供订单号（或商品名称）及退款原因。"""
        if not (order_id or product_name):
            return {"hint": "请提供订单号或商品名称，以便为您办理退款"}
        ref_base = order_id or product_name or "UNKNOWN"
        return {
            "refund_id": f"REF-{ref_base[:8].upper()}-001",
            "order_id": order_id or "(待确认)",
            "product_name": product_name,
            "status": "受理中",
            "expected_time": "3-5个工作日",
            "amount": f"{amount}元" if amount else "全额退款",
            "reason": reason or "用户申请",
        }

    @engine.register
    def check_refund_status(refund_id=None, order_id=None):
        """查询退款进度。支持按退款单号或原订单号查询。"""
        if not (refund_id or order_id):
            return {"error": "请提供退款单号或订单号"}
        return {
            "refund_id": refund_id or f"REF-{order_id}-001",
            "order_id": order_id,
            "status": "审核中",
            "submitted_date": "2026-02-22",
            "expected_completion": "2026-02-27",
            "refund_method": "原路退回",
            "notes": "退款审核通过后将在1-3个工作日内到账。",
        }

    @engine.register
    def check_logistics(order_id=None, tracking_number=None):
        """查询物流轨迹。按订单号或快递单号查询实时物流状态。"""
        if not (order_id or tracking_number):
            return {"hint": "请提供订单号或快递单号"}
        return {
            "tracking_number": tracking_number or "SF1234567890",
            "carrier": "顺丰快递",
            "status": "运输中",
            "current_location": "上海中转仓",
            "last_update": "2026-02-25 18:30",
            "estimated_delivery": "2026-02-27",
        }

    @engine.register
    def transfer_to_agent(department=None, issue_type=None, priority=None):
        """转接人工客服。复杂问题或客户强烈要求时使用。"""
        wait_map = {"紧急": "约1分钟", "高": "约3分钟"}
        return {
            "status": "转接中",
            "department": department or "综合客服",
            "issue_type": issue_type,
            "priority": priority or "普通",
            "estimated_wait": wait_map.get(priority or "", "约5分钟"),
            "ticket_id": "TKT-20260226-001",
        }


# 拒保风险关键词（保险健康告知校验）
_EXCLUDED_CONDITIONS = ["癌症", "艾滋", "精神", "肝硬化"]


# ---------------------------------------------------------------------------
# 保险场景 API
# ---------------------------------------------------------------------------

def _register_insurance_apis(engine: ExecutionEngine) -> None:
    """为保险场景注册演示 API 函数。"""

    @engine.register
    def query_insurance(insurance_type=None, customer_age=None, coverage_type=None):
        """查询保险产品信息。insurance_type 可选：癌症险、重疾险、寿险、医疗险、意外险。"""
        product_map = {
            "癌症险": {
                "monthly_premium_base": 114.0,
                "coverage_amount": 1000000,
                "coverage_items": ["确诊即赔100万", "恶性肿瘤住院津贴每日200元", "身故保额赔付"],
                "waiting_period": "90天",
                "max_age": 60,
                "description": "专项癌症保障，确诊即赔，适合30-60岁健康人群",
            },
            "重疾险": {
                "monthly_premium_base": 280.0,
                "coverage_amount": 500000,
                "coverage_items": ["100种重大疾病", "60种中症", "20种轻症", "保费豁免", "身故赔付"],
                "waiting_period": "90天",
                "max_age": 55,
                "description": "涵盖100种重大疾病，含轻中症分级赔付，可附加保费豁免",
            },
            "医疗险": {
                "monthly_premium_base": 50.0,
                "coverage_amount": 2000000,
                "coverage_items": ["住院医疗100%报销", "门诊手术", "特殊门诊", "质子重离子治疗"],
                "waiting_period": "30天",
                "max_age": 65,
                "description": "200万保额，住院医疗报销比例高，含免赔额1万元",
            },
            "意外险": {
                "monthly_premium_base": 30.0,
                "coverage_amount": 500000,
                "coverage_items": ["意外身故/残疾赔付", "意外医疗报销", "住院津贴"],
                "waiting_period": "无等待期",
                "max_age": 70,
                "description": "覆盖日常意外及交通意外，无等待期，次日生效",
            },
            "寿险": {
                "monthly_premium_base": 150.0,
                "coverage_amount": 1000000,
                "coverage_items": ["身故赔付100万", "全残赔付", "保费豁免"],
                "waiting_period": "90天",
                "max_age": 60,
                "description": "定期寿险，身故或全残赔付，适合有家庭责任的人群",
            },
        }
        ptype = insurance_type or "重疾险"
        product = product_map.get(ptype, product_map["重疾险"])
        age = int(customer_age) if customer_age is not None else None
        if age is not None and age > product["max_age"]:
            return {"error": f"{ptype}投保年龄上限为{product['max_age']}岁，您目前超出投保范围"}
        return {
            "insurance_type": ptype,
            "coverage_type": coverage_type or "全面保障",
            "monthly_premium_reference": product["monthly_premium_base"],
            "coverage_amount": product["coverage_amount"],
            "coverage_items": product["coverage_items"],
            "waiting_period": product["waiting_period"],
            "description": product["description"],
        }

    @engine.register
    def calculate_premium(insurance_type=None, customer_age=None, coverage_amount=None, gender=None):
        """精算保费。根据险种、年龄、保额（及性别）计算月保费和年保费。"""
        base_rate_map = {
            "癌症险": 0.000228,
            "重疾险": 0.00056,
            "医疗险": 0.0001,
            "意外险": 0.00006,
            "寿险": 0.0003,
        }
        ptype = insurance_type or "重疾险"
        base_rate = base_rate_map.get(ptype, 0.00056)
        amount = float(coverage_amount or 500000)
        age = int(customer_age or 35)
        # 年龄系数：30岁以下1.0，每满5岁增加0.15（阶梯式计算）
        age_factor = 1.0 + max(0, (age - 30) // 5) * 0.15
        gender_factor = 1.1 if gender in ("男", "male", "M") else 1.0
        monthly = round(amount * base_rate * age_factor * gender_factor, 2)
        return {
            "insurance_type": ptype,
            "customer_age": age,
            "gender": gender or "未指定",
            "coverage_amount": int(amount),
            "monthly_premium": monthly,
            "annual_premium": round(monthly * 12, 2),
            "payment_term": "20年缴清",
            "note": "以上为参考保费，实际以核保结果为准",
        }

    @engine.register
    def compare_products(product_a=None, product_b=None, customer_age=None):
        """对比两款保险产品的保障范围和性价比。"""
        if not product_a or not product_b:
            return {"hint": "请提供要对比的两款保险产品名称"}
        return {
            "product_a": product_a,
            "product_b": product_b,
            "comparison_dimensions": ["保障范围", "保费水平", "等待期", "理赔便利性"],
            "recommendation": f"根据{customer_age or '您'}的情况，两款产品各有优势，建议结合自身健康状况和预算选择。",
        }

    @engine.register
    def check_health_requirements(insurance_type=None, condition=None):
        """查询投保健康告知要求，判断某种健康状况是否影响投保。"""
        if not insurance_type:
            return {"hint": "请提供险种名称（如重疾险、医疗险）"}
        if not condition:
            return {"hint": "请描述需要核查的健康状况或既往病史"}
        has_risk = any(kw in condition for kw in _EXCLUDED_CONDITIONS)
        return {
            "insurance_type": insurance_type,
            "condition": condition,
            "risk_level": "高风险（可能拒保）" if has_risk else "低风险（建议如实告知）",
            "advice": "如实填写健康告知，具体是否可投保以保险公司核保结果为准。",
        }

    @engine.register
    def get_policy_details(policy_number=None, customer_name=None):
        """查询保单详情。需要保单号或客户姓名。"""
        if not (policy_number or customer_name):
            return {"hint": "请提供保单号或客户姓名以查询保单信息"}
        return {
            "policy_number": policy_number or "POL-20240315-0042",
            "customer_name": customer_name or "张先生",
            "insurance_type": "重疾险",
            "coverage_amount": 500000,
            "monthly_premium": 280,
            "effective_date": "2024-03-15",
            "expiry_date": "2044-03-15",
            "payment_term": "20年缴清",
            "status": "有效",
            "beneficiary": "配偶",
        }

    @engine.register
    def submit_claim(policy_number=None, claim_type=None, incident_date=None, description=None):
        """提交理赔申请。需要保单号、理赔类型和事故/诊断日期。"""
        if not policy_number:
            return {"hint": "请提供保单号以提交理赔"}
        if not claim_type:
            return {"hint": "请提供理赔类型（如：重疾确诊、住院医疗、意外伤害）"}
        doc_map = {
            "重疾确诊": ["医院诊断证明（加盖公章）", "病理报告", "出院小结", "银行账户信息"],
            "住院医疗": ["住院病历", "医疗费用总清单", "费用发票原件", "出院小结"],
            "意外伤害": ["意外事故说明", "诊断证明", "费用发票", "银行账户信息"],
        }
        docs = doc_map.get(claim_type, ["医院诊断证明", "费用发票", "银行账户信息"])
        return {
            "claim_id": "CLM-20260226-0089",
            "policy_number": policy_number,
            "claim_type": claim_type,
            "incident_date": incident_date or "待确认",
            "status": "已受理",
            "required_documents": docs,
            "expected_review_time": "5-10个工作日",
        }

    @engine.register
    def check_claim_status(claim_id=None, policy_number=None):
        """查询理赔进度。支持按理赔单号或保单号查询。"""
        if not (claim_id or policy_number):
            return {"hint": "请提供理赔单号或保单号"}
        return {
            "claim_id": claim_id or "CLM-2026-001",
            "policy_number": policy_number,
            "status": "审核中",
            "current_step": "医疗材料核查（第2步，共4步）",
            "submitted_date": "2026-02-01",
            "expected_completion": "2026-03-01",
        }


# ---------------------------------------------------------------------------
# 安逸花外呼促活场景 API
# ---------------------------------------------------------------------------

def _register_anyihua_outbound_apis(engine: ExecutionEngine) -> None:
    """为安逸花外呼促活场景注册演示 API 函数。"""

    @engine.register
    def verify_customer(name: str = None, phone_suffix: str = None) -> dict:
        """核实客户身份：验证来电人提供的姓名和手机尾号。"""
        if not name and not phone_suffix:
            return {"hint": "请提供客户姓名或手机尾号进行核实"}
        return {
            "identity_confirmed": bool(name or phone_suffix),
            "name_provided": name,
            "phone_suffix_provided": phone_suffix,
            "status": "核实完成" if (name and phone_suffix) else "部分核实",
            "message": f"身份核实{'成功' if name else '部分完成'}，已确认{'姓名' if name else ''}{'和手机尾号' if phone_suffix else ''}",
        }

    @engine.register
    def query_account(customer_name: str = None) -> dict:
        """查询客户账户信息（可用额度、利率、账单日、绑定银行等）。"""
        return {
            "customer_name": customer_name or "客户",
            "available_credit": 18000,
            "authorized_credit": 18000,
            "temp_credit": 26500,
            "temp_credit_status": "临时提额有效期内",
            "annual_rate_pct": 24,
            "cash_ratio_pct": 100,
            "bound_bank": "农业银行",
            "billing_day": 27,
            "repayment_date": "下月1日",
            "loan_count": 3,
            "last_loan_date": "2025-05-02",
            "loan_outstanding": True,
            "message": f"账户可用额度1.8万元，年化利率24%，绑定农业银行，账单日每月27号",
        }

    @engine.register
    def query_loan_records(disputed_date: str = None) -> dict:
        """查询借款记录，支持按日期查询指定借款详情。"""
        if not disputed_date:
            return {
                "loan_records": [
                    {"date": "2025-05-02", "amount": 600, "status": "已还清"},
                ],
                "total_loans": 1,
                "message": "当前系统记录的借款信息",
            }
        return {
            "query_date": disputed_date,
            "found": False,
            "message": f"系统中未查询到{disputed_date}的借款记录，建议客户提供更多信息或联系人工核查",
        }

    @engine.register
    def calculate_repayment(amount: int = None, months: int = None) -> dict:
        """计算指定金额和期数的每月还款金额。"""
        if not amount:
            return {"hint": "请提供借款金额"}
        months = months or 12
        annual_rate = 0.24
        monthly_rate = annual_rate / 12
        monthly_payment = round(amount * monthly_rate * (1 + monthly_rate) ** months
                                / ((1 + monthly_rate) ** months - 1), 2)
        total_interest = round(monthly_payment * months - amount, 2)
        return {
            "amount": amount,
            "months": months,
            "monthly_payment": monthly_payment,
            "total_interest": total_interest,
            "annual_rate_pct": 24,
            "message": f"借款{amount}元，分{months}期，每月还款约{monthly_payment}元，总利息{total_interest}元",
        }

    @engine.register
    def handle_complaint(complaint_type: str = None, description: str = None) -> dict:
        """受理用户投诉，生成工单并告知处理时限。"""
        if not complaint_type:
            return {"hint": "请提供投诉类型"}
        return {
            "ticket_id": f"CMP-ANYIHUA-{complaint_type[:4].upper()}-001",
            "complaint_type": complaint_type,
            "status": "已受理",
            "expected_response_time": "1-3个工作日",
            "escalation_channel": "官方APP > 我的 > 在线客服",
            "message": f"您的{complaint_type}投诉已受理，工单号已生成，将在1-3个工作日内处理并回复",
        }

    @engine.register
    def end_call(outcome: str = None) -> dict:
        """结束通话，记录通话结果。"""
        farewell_map = {
            "用户拒绝借款": "感谢您接听，祝您生活愉快，有需要随时欢迎使用安逸花，再见！",
            "投诉已处理": "感谢您的反馈，我们会尽快处理，祝您生活愉快，再见！",
            "用户有借款意向": "好的，感谢您的信任，祝您借款顺利，有任何问题随时联系我们，再见！",
        }
        farewell = farewell_map.get(outcome or "", "感谢您接听，祝您生活愉快，也邀请您多登录安逸花APP看看，再见！")
        return {
            "outcome": outcome or "通话结束",
            "farewell_message": farewell,
            "status": "通话已结束",
        }

    @engine.register
    def get_agent_history() -> dict:
        """
        获取本次通话中坐席已使用过的引导话术列表（演示版，返回空历史）。

        供对话管理器（LLM）判断某一话术是否已重复使用——
        若同一话术出现 2 次以上，应改用 escalate_to_human（转接人工）
        而非继续重复。生产环境中应传入实际对话历史。
        """
        return {
            "agent_utterances": [],
            "utterance_count": 0,
            "has_repeated": False,
            "message": "演示模式：暂无历史话术记录，可继续引导操作",
        }

    @engine.register
    def query_unresolved_issues() -> dict:
        """
        查询用户当前是否还有未解决的问题或诉求（演示版，默认无未解决诉求）。

        供对话管理器（LLM）在执行 say_goodbye（告别）意图前调用，
        确认 issue_count=0（无未解决诉求）才可结束通话，
        否则继续帮助用户解决问题或转接人工。
        生产环境中应根据实际对话历史计算未解决诉求数量。
        """
        return {
            "issue_count": 0,
            "unresolved_snippets": [],
            "safe_to_close": True,
            "message": "演示模式：未检测到未解决诉求，可以礼貌告别",
        }


# ---------------------------------------------------------------------------
# 公共注册表
# ---------------------------------------------------------------------------

#: 场景名称 → API 注册函数映射
SCENARIO_API_REGISTRY: Dict[str, Callable[[ExecutionEngine], None]] = {
    "chat": _register_chat_apis,
    "闲聊": _register_chat_apis,
    "callcenter": _register_callcenter_apis,
    "客服": _register_callcenter_apis,
    "insurance": _register_insurance_apis,
    "保险": _register_insurance_apis,
    "保险挽回": _register_insurance_apis,
    "anyihua": _register_anyihua_outbound_apis,
    "安逸花": _register_anyihua_outbound_apis,
    "安逸花外呼": _register_anyihua_outbound_apis,
    "安逸花外呼促活": _register_anyihua_outbound_apis,
}


def get_scenario_key(scenario_name: str) -> Optional[str]:
    """从场景名称（可能含中文别名）查找注册表键，找不到时返回 None。"""
    if scenario_name in SCENARIO_API_REGISTRY:
        return scenario_name
    for key in SCENARIO_API_REGISTRY:
        if key in scenario_name or scenario_name in key:
            return key
    return None
