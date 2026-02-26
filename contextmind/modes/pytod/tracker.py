"""
PyTODTracker — 面向场景的 PyTOD 对话追踪器

实现与 DST / FnCTOD 追踪器完全一致的接口（from_scenario / process_turn /
get_current_state / reset），可直接插入 cli_demo / batch_demo / web_demo 的
已有模式分派框架，无需修改调用侧的框架逻辑。

算法三步流程（参考 docs/algorithms/pytod.md）::

    用户输入
      ↓
    [步骤一] 动作解析器（Action Parser）
        → LLM 根据可用 API 列表和对话历史，生成多行 PyTOD 程序::

            x1 service_1_api(param='value')
            x2 Hint('request value: slot_name')
            x3 say(x2)

      ↓
    [步骤二] 执行引擎（Execution Engine）
        → 安全解析并执行程序语句
        → 调用已注册的模拟 API 函数（或真实 API）
        → 返回结构化执行结果

      ↓
    [步骤三] 对话管理器（Dialogue Manager）
        → LLM 根据执行结果生成面向用户的自然语言回复

内置场景 API（演示用）：
    - chat:       get_weather / search_info / tell_joke / translate_text / calculate
    - callcenter: lookup_order / submit_complaint / process_refund / check_refund_status / transfer_to_agent
    - insurance:  query_insurance / calculate_premium / get_policy_details / submit_claim / check_claim_status
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .execution_engine import ExecutionEngine, ProgramExecutionResult
from .prompt_builder import PyTODPromptBuilder, ConversationTurn

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 内置场景 API 注册
# --------------------------------------------------------------------------- #

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
        # 常见核保参考（简化演示）
        excluded = ["恶性肿瘤", "白血病", "艾滋病", "先天性心脏病（重度）"]
        has_risk = any(kw in condition for kw in excluded)
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


#: 场景名称 → API 注册函数映射
_SCENARIO_API_REGISTRY: Dict[str, Any] = {
    "chat": _register_chat_apis,
    "闲聊": _register_chat_apis,
    "callcenter": _register_callcenter_apis,
    "客服": _register_callcenter_apis,
    "insurance": _register_insurance_apis,
    "保险": _register_insurance_apis,
    "保险挽回": _register_insurance_apis,
}


def _get_scenario_key(scenario_name: str) -> Optional[str]:
    """从场景名称（可能含中文）查找注册表键。"""
    # 精确匹配
    if scenario_name in _SCENARIO_API_REGISTRY:
        return scenario_name
    # 子串匹配（e.g. "保险挽回场景" → "保险挽回"）
    for key in _SCENARIO_API_REGISTRY:
        if key in scenario_name or scenario_name in key:
            return key
    return None


# --------------------------------------------------------------------------- #
# PyTODTracker
# --------------------------------------------------------------------------- #


@dataclass
class PyTODTurnResult:
    """单轮 PyTOD 对话结果。"""

    response: str = ""
    program_text: str = ""
    execution: Optional[ProgramExecutionResult] = None
    state: Dict[str, Any] = field(default_factory=dict)


class PyTODTracker:
    """
    PyTOD 风格对话追踪器

    实现与 ``DialogueStateTracker`` / ``FnCTODTracker`` 完全一致的接口，
    可直接插入已有 Demo 的模式分派逻辑，无需修改调用侧框架。

    **算法三步流程**：

    1. 动作解析器（Action Parser）：LLM 生成多行 PyTOD 程序
    2. 执行引擎（Execution Engine）：安全执行程序，调用注册 API
    3. 对话管理器（Dialogue Manager）：LLM 根据执行结果生成回复

    **开放域模式**（默认）：无需预定义 schema，LLM 自由命名意图和槽位。

    使用示例::

        tracker = PyTODTracker.from_scenario(
            llm_client=llm_client,
            scenario_config=insurance_scenario,
        )
        result = await tracker.process_turn(user_utterance="我想了解癌症险")
        print(result["response"])   # 自然语言回复
        print(result["state"])      # 当前累积状态
    """

    def __init__(
        self,
        llm_client: Any,
        execution_engine: ExecutionEngine,
        prompt_builder: PyTODPromptBuilder,
        scenario_name: str = "",
        max_history_turns: int = 10,
    ) -> None:
        """
        初始化追踪器。

        通常通过 ``from_scenario()`` 工厂方法创建，而非直接调用构造函数。
        """
        self.llm_client = llm_client
        self.execution_engine = execution_engine
        self.prompt_builder = prompt_builder
        self.scenario_name = scenario_name
        self.max_history_turns = max_history_turns

        # 运行时状态
        self.history: List[ConversationTurn] = []
        self.current_state: Dict[str, Any] = {}
        self.turn_count: int = 0

        logger.info(
            f"PyTODTracker 初始化完成 "
            f"(场景: {scenario_name or '未指定'}, "
            f"已注册 API: {execution_engine.list_functions()})"
        )

    # ------------------------------------------------------------------ #
    # 工厂方法
    # ------------------------------------------------------------------ #

    @classmethod
    def from_scenario(
        cls,
        llm_client: Any,
        scenario_config: Any,
        max_history_turns: int = 10,
        response_language: str = "中文",
    ) -> "PyTODTracker":
        """
        从场景配置创建 PyTODTracker 实例。

        自动根据场景名称注册匹配的演示 API 函数（chat / callcenter / insurance）。
        若场景无匹配 API，返回空注册表的追踪器（仍可运行开放域对话）。

        参数:
            llm_client:        LLM 客户端实例（需支持 chat_async 或 chat）
            scenario_config:   场景配置对象（ScenarioConfig）
            max_history_turns: 保留的最大历史轮数
            response_language: LLM 回复使用的语言

        返回:
            PyTODTracker 实例
        """
        engine = ExecutionEngine()
        scenario_name = getattr(scenario_config, "name", "")

        # 注册场景对应的 API 函数
        key = _get_scenario_key(scenario_name)
        if key:
            _SCENARIO_API_REGISTRY[key](engine)
            logger.info(
                f"✅ 已为场景 '{scenario_name}' 注册 API: {engine.list_functions()}"
            )
        else:
            logger.warning(
                f"⚠️  场景 '{scenario_name}' 无预置 API，使用空注册表运行开放域模式"
            )

        builder = PyTODPromptBuilder(
            schema=None,  # 开放域模式
            max_history_turns=max_history_turns,
            response_language=response_language,
        )

        return cls(
            llm_client=llm_client,
            execution_engine=engine,
            prompt_builder=builder,
            scenario_name=scenario_name,
            max_history_turns=max_history_turns,
        )

    # ------------------------------------------------------------------ #
    # 公开接口（与 DST / FnCTOD 一致）
    # ------------------------------------------------------------------ #

    async def process_turn(
        self,
        user_utterance: str,
        system_utterance: str = "",
    ) -> Dict[str, Any]:
        """
        处理单轮对话。

        按照 PyTOD 三步流程执行：

        1. **动作解析器**：调用 LLM 生成多行 PyTOD 程序
        2. **执行引擎**：执行程序，调用注册 API
        3. **对话管理器**：调用 LLM 根据执行结果生成自然语言回复

        参数:
            user_utterance:   当前轮用户话语
            system_utterance: 上一轮系统回复（可选，用于历史上下文）

        返回:
            包含以下键的字典::

                {
                    "response":     str,  # 面向用户的自然语言回复
                    "program_text": str,  # 动作解析器生成的程序文本
                    "state":        dict, # 当前累积状态（变量值 + Hint 等）
                    "execution":    ProgramExecutionResult | None,
                }
        """
        self.turn_count += 1
        logger.info(f"\n{'='*50}")
        logger.info(f"PyTOD 第 {self.turn_count} 轮对话")
        logger.info(f"用户: {user_utterance}")

        # -------- 步骤一：动作解析器 -------- #
        ap_messages = self.prompt_builder.build_action_parser_messages(
            user_input=user_utterance,
            execution_engine=self.execution_engine,
            history=self.history,
        )
        try:
            program_text = await self._call_llm(ap_messages)
        except Exception as exc:
            logger.error(f"动作解析器 LLM 调用失败: {exc}")
            program_text = "NONE()"

        program_text = program_text.strip()
        logger.info(f"[Action Parser] 程序:\n{program_text}")

        # -------- 步骤二：执行引擎 -------- #
        exec_result: Optional[ProgramExecutionResult] = None
        if program_text and program_text != "NONE()":
            try:
                exec_result = self.execution_engine.execute_program(program_text)
                if exec_result.success:
                    self._update_state(exec_result)
                    logger.info(f"[Execution Engine] 成功，变量: {list(exec_result.variable_values.keys())}")
                else:
                    logger.warning(f"[Execution Engine] 执行失败: {exec_result.errors}")
            except Exception as exc:
                logger.error(f"[Execution Engine] 异常: {exc}")
                exec_result = None

        # -------- 步骤三：对话管理器 -------- #
        # 优化 1：当程序已通过 say() 明确给出回复文本，直接使用，无需再次调用 LLM
        if exec_result is not None and exec_result.say_output:
            response = exec_result.say_output
            logger.info(f"[Dialogue Manager] 直接使用 say() 输出: {response[:80]}...")
        elif exec_result is not None:
            # 有 API 执行结果（非 say），由对话管理器 LLM 生成回复
            dm_messages = self.prompt_builder.build_dialogue_manager_messages(
                user_input=user_utterance,
                execution_result=exec_result,
                history=self.history,
                current_state=self.current_state if self.current_state else None,
            )
            try:
                response = await self._call_llm(dm_messages)
            except Exception as exc:
                logger.error(f"对话管理器 LLM 调用失败: {exc}")
                response = "抱歉，处理您的请求时出现了问题，请稍后重试。"
            logger.info(f"[Dialogue Manager] 回复: {response[:80]}...")
        else:
            # 优化 2：NONE() 情况使用纯自然语言后备提示，避免输出 JSON
            dm_messages = self.prompt_builder.build_fallback_messages(
                user_input=user_utterance,
                history=self.history,
                scenario_description=self.scenario_name,
                current_state=self.current_state if self.current_state else None,
            )
            try:
                response = await self._call_llm(dm_messages)
            except Exception as exc:
                logger.error(f"后备对话 LLM 调用失败: {exc}")
                response = "抱歉，处理您的请求时出现了问题，请稍后重试。"
            logger.info(f"[Dialogue Manager] 后备回复: {response[:80]}...")

        # -------- 更新历史 -------- #
        self.history.append(ConversationTurn(role="user", content=user_utterance))
        self.history.append(ConversationTurn(role="assistant", content=response))
        # 保持历史在 max_history_turns 范围内
        if len(self.history) > self.max_history_turns * 2:
            self.history = self.history[-(self.max_history_turns * 2):]

        return {
            "response": response,
            "program_text": program_text,
            "state": dict(self.current_state),
            "execution": exec_result,
        }

    def get_current_state(self) -> Dict[str, Any]:
        """
        返回当前累积对话状态。

        状态包含执行引擎各轮次返回的变量值和 Hint 消息列表。
        """
        return dict(self.current_state)

    def reset(self) -> None:
        """重置对话状态，清空历史、状态和轮次计数。"""
        self.history = []
        self.current_state = {}
        self.turn_count = 0
        logger.info("PyTODTracker 对话状态已重置")

    # ------------------------------------------------------------------ #
    # 内部方法
    # ------------------------------------------------------------------ #

    async def _call_llm(self, messages: List[Dict[str, str]]) -> str:
        """
        调用 LLM，优先使用 chat_async，降级为同步 chat。

        参数:
            messages: OpenAI 兼容的 messages 列表

        返回:
            LLM 生成的文本
        """
        if hasattr(self.llm_client, "chat_async"):
            return await self.llm_client.chat_async(messages=messages)
        elif hasattr(self.llm_client, "chat"):
            import asyncio

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, lambda: self.llm_client.chat(messages=messages)
            )
        raise RuntimeError("llm_client 既无 chat_async 也无 chat 方法")

    def _update_state(self, exec_result: ProgramExecutionResult) -> None:
        """
        将执行结果中的变量值合并到累积状态。

        跳过 say() 产生的字符串变量，保留 API 调用返回的结构化数据和
        Hint 消息列表。
        """
        for var, val in exec_result.variable_values.items():
            if not isinstance(val, str):
                self.current_state[var] = val
        # Replace hints with the current turn's hints (don't accumulate stale hints)
        if exec_result.hint_messages:
            self.current_state["_hints"] = exec_result.hint_messages
        else:
            self.current_state.pop("_hints", None)
        if exec_result.say_output:
            self.current_state["_say"] = exec_result.say_output
        else:
            self.current_state.pop("_say", None)
