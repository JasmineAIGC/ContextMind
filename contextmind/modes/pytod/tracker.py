"""
PyTODTracker — 面向场景的 PyTOD 对话追踪器

实现与 DST / FnCTOD 追踪器一致的接口（from_scenario / process_turn /
get_current_state / reset），按照三步流程处理每轮对话：
动作解析器 → 执行引擎 → 对话管理器。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .api_registry import SCENARIO_API_REGISTRY, get_scenario_key
from .execution_engine import ExecutionEngine, ProgramExecutionResult
from .prompts import PyTODPromptBuilder, ConversationTurn

logger = logging.getLogger(__name__)

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

    实现与 ``DialogueStateTracker`` / ``FnCTODTracker`` 一致的接口，
    按三步流程处理每轮对话：动作解析器 → 执行引擎 → 对话管理器。
    默认启用开放域模式（无需预定义 schema）。

    温度策略
    --------
    动作解析器（Action Parser）生成**结构化代码**（如 ``x1 = query_account()``），
    随机采样会导致不同运行中选择不同的 API 或输出 ``NONE()``，引发完全不同的
    执行路径，进而使最终回复内容差异巨大。因此：

    - ``AP_TEMPERATURE``：动作解析器专用低温（默认 0.1），保证代码生成稳定。
    - 对话管理器（Dialogue Manager）生成自然语言，可使用较高温度（由
      ``LLMConfig.temperature`` 控制，默认 0.3），在语言流畅度与稳定性之间
      取得平衡。
    """

    #: 动作解析器专用温度——代码生成任务需接近 0，以避免随机选择不同 API
    AP_TEMPERATURE: float = 0.1

    def __init__(
        self,
        llm_client: Any,
        execution_engine: ExecutionEngine,
        prompt_builder: PyTODPromptBuilder,
        scenario_name: str = "",
        max_history_turns: int = 10,
        scenario_context: str = "",
    ) -> None:
        """
        初始化追踪器。

        通常通过 ``from_scenario()`` 工厂方法创建，而非直接调用构造函数。

        参数:
            llm_client:        LLM 客户端实例（需支持 chat_async 或 chat）
            execution_engine:  已注册 API 函数的 ExecutionEngine 实例
            prompt_builder:    PyTODPromptBuilder 实例
            scenario_name:     场景名称（用于日志和后备提示）
            max_history_turns: 保留的最大历史轮数
            scenario_context:  业务场景描述（可选），注入到 Action Parser 和
                               Dialogue Manager 系统提示中，帮助 LLM 理解业务背景。
                               例如："这是一个外呼小额借款推介场景，坐席正在联系老用户
                               激活闲置额度，应先核实身份，再告知额度并引导借款操作。"
        """
        self.llm_client = llm_client
        self.execution_engine = execution_engine
        self.prompt_builder = prompt_builder
        self.scenario_name = scenario_name
        self.max_history_turns = max_history_turns
        self.scenario_context = scenario_context

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

        key = get_scenario_key(scenario_name)
        if key:
            SCENARIO_API_REGISTRY[key](engine)
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

        ap_messages = self.prompt_builder.build_action_parser_messages(
            user_input=user_utterance,
            execution_engine=self.execution_engine,
            history=self.history,
            scenario_context=self.scenario_context,
        )
        try:
            program_text = await self._call_llm(ap_messages, temperature=self.AP_TEMPERATURE)
        except Exception as exc:
            logger.error(f"动作解析器 LLM 调用失败: {exc}")
            program_text = "NONE()"

        program_text = program_text.strip()
        logger.info(f"[Action Parser] 程序:\n{program_text}")

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
                scenario_context=self.scenario_context,
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

        self.history.append(ConversationTurn(role="user", content=user_utterance))
        self.history.append(ConversationTurn(role="assistant", content=response))
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

    async def _call_llm(self, messages: List[Dict[str, str]], temperature: Optional[float] = None) -> str:
        """
        调用 LLM，优先使用 chat_async，降级为同步 chat。

        参数:
            messages: OpenAI 兼容的 messages 列表
            temperature: 采样温度覆盖值。传入 None 时由 LLM 客户端自动回退到
                ``LLMConfig.temperature``（默认 0.3）。动作解析器调用时应
                显式传入 ``self.AP_TEMPERATURE``（0.1）以保证代码生成稳定。

        返回:
            LLM 生成的文本
        """
        if hasattr(self.llm_client, "chat_async"):
            return await self.llm_client.chat_async(messages=messages, temperature=temperature)
        elif hasattr(self.llm_client, "chat"):
            import asyncio

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, lambda: self.llm_client.chat(messages=messages, temperature=temperature)
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
        # 每轮替换提示值，不累积过期的旧提示
        if exec_result.hint_messages:
            self.current_state["_hints"] = exec_result.hint_messages
        else:
            self.current_state.pop("_hints", None)
        if exec_result.say_output:
            self.current_state["_say"] = exec_result.say_output
        else:
            self.current_state.pop("_say", None)
