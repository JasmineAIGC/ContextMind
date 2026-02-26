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
    - chat:       search_info / tell_joke / play_music
    - callcenter: lookup_order / process_refund / transfer_to_agent
    - insurance:  query_insurance / calculate_premium / check_claim_status
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
    def search_info(query=None, language=None):
        """搜索信息"""
        if not query:
            return {"result": "请提供搜索关键词"}
        return {
            "query": query,
            "result": f"关于「{query}」的搜索结果（模拟）",
            "source": "演示数据库",
        }

    @engine.register
    def tell_joke(topic=None, style=None):
        """讲一个笑话"""
        jokes = {
            "程序员": "为什么程序员喜欢暗色主题？——因为 light 会吸引 bug。",
            "数学": "为什么数学书总是忧伤？——因为它有太多的问题。",
            None: "人生就像一盒巧克力，你永远不知道你会遇到什么 bug。",
        }
        return {"joke": jokes.get(topic, jokes[None])}

    @engine.register
    def play_music(genre=None, mood=None, artist=None):
        """播放音乐（模拟）"""
        return {
            "status": "playing",
            "genre": genre or "流行",
            "mood": mood or "轻松",
            "artist": artist or "随机",
            "message": f"正在为您播放{mood or '轻松'}风格的{genre or '流行'}音乐",
        }


def _register_callcenter_apis(engine: ExecutionEngine) -> None:
    """为客服场景注册演示 API 函数。"""

    @engine.register
    def lookup_order(order_id=None, customer_id=None):
        """查询订单状态"""
        if not (order_id or customer_id):
            return {"error": "请提供订单号或客户ID"}
        return {
            "order_id": order_id or "ORD-UNKNOWN",
            "status": "已发货",
            "shipping_date": "2026-02-20",
            "estimated_delivery": "2026-02-28",
            "carrier": "顺丰快递",
        }

    @engine.register
    def process_refund(order_id=None, reason=None, amount=None):
        """处理退款申请"""
        if not order_id:
            return {"error": "请提供订单号"}
        return {
            "refund_id": f"REF-{order_id}-001",
            "status": "受理中",
            "expected_time": "3-5个工作日",
            "amount": amount or "全额退款",
            "reason": reason,
        }

    @engine.register
    def transfer_to_agent(department=None, issue_type=None, priority=None):
        """转接人工客服"""
        return {
            "status": "转接中",
            "department": department or "综合客服",
            "estimated_wait": "约5分钟",
            "ticket_id": "TKT-20260226-001",
        }


def _register_insurance_apis(engine: ExecutionEngine) -> None:
    """为保险场景注册演示 API 函数。"""

    @engine.register
    def query_insurance(insurance_type=None, customer_age=None, coverage_type=None):
        """查询保险产品信息"""
        return {
            "insurance_type": insurance_type or "癌症险",
            "monthly_premium": 114.0,
            "coverage_amount": 1000000,
            "coverage_items": ["确诊赔付", "手术津贴", "住院津贴", "身故赔付"],
            "waiting_period": "90天",
            "description": "适合30-60岁健康人群，无等待期续保",
        }

    @engine.register
    def calculate_premium(insurance_type=None, customer_age=None, coverage_amount=None):
        """计算保费"""
        base = float(coverage_amount or 1000000) / 1000000 * 100
        age_factor = 1.0 + max(0, (int(customer_age or 40) - 30)) * 0.05
        monthly = round(base * age_factor, 2)
        return {
            "insurance_type": insurance_type or "癌症险",
            "customer_age": customer_age or 40,
            "coverage_amount": coverage_amount or 1000000,
            "monthly_premium": monthly,
            "annual_premium": round(monthly * 12, 2),
        }

    @engine.register
    def check_claim_status(claim_id=None, policy_number=None):
        """查询理赔进度"""
        if not (claim_id or policy_number):
            return {"error": "请提供理赔单号或保单号"}
        return {
            "claim_id": claim_id or "CLM-2026-001",
            "status": "审核中",
            "submitted_date": "2026-02-01",
            "expected_completion": "2026-03-01",
            "notes": "材料齐全，正在进行医疗材料核查",
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
        if exec_result.hint_messages:
            existing = self.current_state.get("_hints", [])
            self.current_state["_hints"] = existing + exec_result.hint_messages
        if exec_result.say_output:
            self.current_state["_say"] = exec_result.say_output
