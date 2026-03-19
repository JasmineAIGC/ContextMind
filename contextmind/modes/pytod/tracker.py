"""
PyTOD Tracker — 两种实现：论文三步流程 + ADK 原生函数调用

PyTOD 论文三步流程（PyTODTracker）
------------------------------------
基于 "Task-Oriented Dialogue as Dataflow Synthesis" 系列论文：
    Step 1 — Action Parser (AP): LLM 生成 Python-like 程序
    Step 2 — Execution Engine (EE): 运行程序，得到 API 执行结果
    Step 3 — Dialogue Manager (DM): LLM 根据执行结果生成自然语言回复

ADK 原生函数调用（AdkPyTODTracker / PyTODAgent）
--------------------------------------------------
利用 Google ADK 原生 Function Calling 替代显式程序解析流程，
LLM 直接决定调用哪个 API、传入什么参数，并生成自然语言回复。

使用示例::

    # 论文三步流程（推荐用于精确控制）
    from contextmind.modes.pytod import PyTODTracker, PyTODPromptBuilder, ExecutionEngine
    from contextmind.modes.pytod.schemas import ServiceSchema

    engine = ExecutionEngine()
    # ... 注册 API ...
    builder = PyTODPromptBuilder(schema=my_schema)
    tracker = PyTODTracker(llm_client=llm, execution_engine=engine, prompt_builder=builder)
    result = await tracker.process_turn("查询我的账户余额")

    # ADK 原生（推荐用于快速接入）
    from contextmind.modes.pytod import PyTODAgent, ExecutionEngine
    engine = ExecutionEngine()
    agent = PyTODAgent(engine=engine, scenario_context="客服场景")
    result = await agent.process_turn("查询我的账户余额")
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from contextmind.infra.llm_client import LLMConfig, create_local_adk_model
from contextmind.infra.logger import get_logger
from contextmind.modes.pytod.execution_engine import ExecutionEngine
from contextmind.modes.pytod.prompts import ConversationTurn, PyTODPromptBuilder
from contextmind.modes.pytod.registry import SCENARIO_API_REGISTRY, get_scenario_key

try:
    from google.adk.agents import LlmAgent  # type: ignore[import]
    from google.adk.runners import InMemoryRunner  # type: ignore[import]
    from google.adk.tools import FunctionTool  # type: ignore[import]
    from google.genai import types as genai_types  # type: ignore[import]
    _ADK_AVAILABLE = True
except ImportError:
    _ADK_AVAILABLE = False

logger = get_logger(__name__)

_ADK_INSTALL_MSG = (
    "google-adk 未安装，无法创建 AdkPyTODTracker。\n"
    "请运行: pip install google-adk litellm"
)


def adk_tools_from_engine(engine: Any) -> List[Any]:
    """将 ExecutionEngine 中已注册的函数包装为 ADK FunctionTool 列表。

    ADK 自动从函数签名和 docstring 生成参数描述（JSON Schema）。

    Args:
        engine: 已注册了 API 函数的 ExecutionEngine 实例。

    Returns:
        可直接传给 ``LlmAgent(tools=...)`` 的 FunctionTool 列表。
    """
    if not _ADK_AVAILABLE:
        raise ImportError(_ADK_INSTALL_MSG)

    tools = [FunctionTool(func=func) for func in engine.registry.values()]
    logger.info(
        f"adk_tools_from_engine: 共 {len(tools)} 个工具: {list(engine.registry.keys())}"
    )
    return tools


# ---------------------------------------------------------------------------
# Step 1: PyTODTracker — 论文三步流程实现
# ---------------------------------------------------------------------------

class PyTODTracker:
    """PyTOD 论文三步流程追踪器：AP → EE → DM。

    严格对应原始论文的三步处理流程：
        1. Action Parser (AP)   — LLM 根据对话历史和 Schema 生成程序
        2. Execution Engine (EE)— 运行程序，执行注册的 API 函数
        3. Dialogue Manager (DM)— LLM 根据执行结果生成自然语言回复

    参数
    ----
    llm_client : SimpleLLMClient
        LLM 客户端，同时用于 AP（低温）和 DM 阶段调用。
    execution_engine : ExecutionEngine
        已注册 API 函数的执行引擎。
    prompt_builder : PyTODPromptBuilder
        负责生成 AP 和 DM 两阶段的提示词。
    scenario_name : str
        场景名称（仅用于日志和标识）。
    max_history_turns : int
        构建提示词时保留的最近历史轮次数。
    scenario_context : str
        业务场景描述，嵌入系统指令以帮助 LLM 理解背景。
    """

    #: 动作解析阶段使用低温，保证程序生成的确定性
    AP_TEMPERATURE: float = 0.1
    #: 对话管理阶段使用略高温度，使回复更自然
    DM_TEMPERATURE: float = 0.3

    def __init__(
        self,
        llm_client: Any,
        execution_engine: ExecutionEngine,
        prompt_builder: PyTODPromptBuilder,
        scenario_name: str = "",
        max_history_turns: int = 10,
        scenario_context: str = "",
    ) -> None:
        self.llm_client = llm_client
        self.execution_engine = execution_engine
        self.prompt_builder = prompt_builder
        self.scenario_name = scenario_name
        self.max_history_turns = max_history_turns
        self.scenario_context = scenario_context

        #: 对话历史（ConversationTurn 列表）。可在调用 process_turn 前手动注入历史。
        self.history: List[ConversationTurn] = []
        self.current_state: Dict[str, Any] = {}
        self.turn_count: int = 0

        logger.info(
            f"PyTODTracker (论文三步) 初始化完成 "
            f"(场景={scenario_name}, API={list(execution_engine.registry.keys())})"
        )

    # ------------------------------------------------------------------ #
    # process_turn — 三步流程核心
    # ------------------------------------------------------------------ #

    async def process_turn(
        self,
        user_utterance: str,
        system_utterance: str = "",  # 保持接口兼容，一般不需要传入
    ) -> Dict[str, Any]:
        """处理单轮对话，执行 AP → EE → DM 三步流程。

        Args:
            user_utterance: 用户话语。
            system_utterance: 保留参数，当前实现不使用。

        Returns:
            包含以下键的字典：
                - ``response``     : 对话管理器生成的自然语言回复
                - ``program_text`` : 动作解析器生成的 PyTOD 程序文本
                - ``state``        : 当前累积的执行变量状态
                - ``execution``    : ProgramExecutionResult 对象
        """
        self.turn_count += 1
        logger.info(f"[PyTODTracker] 第 {self.turn_count} 轮: {user_utterance[:80]}")

        # ---- Step 1: Action Parser ----
        ap_messages = self.prompt_builder.build_action_parser_prompt(
            history=self.history,
            user_utterance=user_utterance,
            scenario_context=self.scenario_context,
        )
        program_text = await self.llm_client.chat_async(
            messages=ap_messages,
            temperature=self.AP_TEMPERATURE,
        )
        program_text = (program_text or "NONE()").strip()
        logger.info(f"[AP] 程序: {program_text[:120]}")

        # ---- Step 2: Execution Engine ----
        execution_result = self.execution_engine.execute_program(program_text)
        if execution_result.success:
            self.current_state.update(execution_result.variable_values)
        logger.info(
            f"[EE] 执行 {'成功' if execution_result.success else '失败'}, "
            f"变量: {list(execution_result.variable_values.keys())}"
        )

        # ---- Step 3: Dialogue Manager ----
        dm_messages = self.prompt_builder.build_dm_prompt(
            history=self.history,
            user_utterance=user_utterance,
            program=program_text,
            execution_result=execution_result,
            scenario_context=self.scenario_context,
        )
        response = await self.llm_client.chat_async(
            messages=dm_messages,
            temperature=self.DM_TEMPERATURE,
        )
        response = (response or "").strip()
        logger.info(f"[DM] 回复: {response[:80]}")

        # ---- 更新历史 ----
        self.history.append(ConversationTurn(role="user", content=user_utterance))
        self.history.append(ConversationTurn(role="assistant", content=response))

        return {
            "response": response,
            "program_text": program_text,
            "state": dict(self.current_state),
            "execution": execution_result,
        }

    # ------------------------------------------------------------------ #
    # 辅助方法
    # ------------------------------------------------------------------ #

    def get_current_state(self) -> Dict[str, Any]:
        """返回当前累积的执行变量状态。"""
        return dict(self.current_state)

    def reset(self) -> None:
        """重置对话状态（清空历史、状态和轮次计数）。"""
        self.history = []
        self.current_state = {}
        self.turn_count = 0
        logger.info("PyTODTracker 对话状态已重置")

    @classmethod
    def from_scenario(
        cls,
        llm_client: Any,
        scenario_config: Any,
        **kwargs: Any,
    ) -> "PyTODTracker":
        """从场景配置创建 PyTODTracker（论文三步流程版本）。

        注意：需要在外部提供 prompt_builder；若未提供，则使用内置空 Schema 构建。

        Args:
            llm_client:      LLM 客户端实例。
            scenario_config: ScenarioConfig 实例。
            **kwargs:        额外参数（如 prompt_builder、scenario_context 等）。
        """
        from contextmind.modes.pytod.schemas import ServiceSchema

        engine = ExecutionEngine()
        scenario_name = getattr(scenario_config, "name", "")
        key = get_scenario_key(scenario_name)
        if key:
            SCENARIO_API_REGISTRY[key](engine)

        # 使用调用方提供的 prompt_builder，否则用空 Schema 构建占位符
        prompt_builder: PyTODPromptBuilder = kwargs.pop(
            "prompt_builder",
            PyTODPromptBuilder(
                schema=ServiceSchema(service_name=scenario_name, description=""),
            ),
        )
        max_history_turns: int = kwargs.pop("max_history_turns", 10)
        scenario_context: str = kwargs.pop(
            "scenario_context",
            getattr(scenario_config, "description", ""),
        )
        return cls(
            llm_client=llm_client,
            execution_engine=engine,
            prompt_builder=prompt_builder,
            scenario_name=scenario_name,
            max_history_turns=max_history_turns,
            scenario_context=scenario_context,
        )


# ---------------------------------------------------------------------------
# Step 2: AdkPyTODTracker — ADK 原生函数调用实现
# ---------------------------------------------------------------------------

class AdkPyTODTracker:
    """ADK 原生任务型对话追踪器。

    以 ADK 原生 Function Calling 替代显式的 PyTOD 三步程序解析流程。
    LLM 直接决定调用哪个 API、传入什么参数，并生成自然语言回复。

    参数
    ----
    engine : ExecutionEngine
        已注册 API 函数的执行引擎，其函数将转为 ADK 工具。
    config : LLMConfig | None
        本地 LLM 配置；若为 None 则从 ``.env`` 自动加载。
    scenario_context : str
        注入 system instruction 的业务场景描述（可选）。
    app_name : str
        ADK 应用名称。
    user_id : str
        ADK 用户标识符。
    """

    #: 动作解析使用的低温，保证输出稳定
    AP_TEMPERATURE: float = 0.1

    def __init__(
        self,
        engine: Any,
        config: Optional[LLMConfig] = None,
        scenario_context: str = "",
        app_name: str = "pytod_adk",
        user_id: str = "default_user",
    ) -> None:
        if not _ADK_AVAILABLE:
            raise ImportError(_ADK_INSTALL_MSG)

        self._llm_config = config if isinstance(config, LLMConfig) else LLMConfig.from_env()
        adk_model = create_local_adk_model(self._llm_config)
        self.engine = engine
        self.scenario_context = scenario_context
        self._user_id = user_id

        tools = adk_tools_from_engine(engine)
        instruction = self._build_instruction(scenario_context)

        self._agent = LlmAgent(
            name="pytod_agent",
            model=adk_model,
            instruction=instruction,
            tools=tools,
        )
        self._runner = InMemoryRunner(agent=self._agent, app_name=app_name)
        self._session_id: Optional[str] = None

        self.current_state: Dict[str, Any] = {}
        self.turn_count: int = 0

        logger.info(
            f"AdkPyTODTracker 初始化完成 (model={self._llm_config.model}, "
            f"工具: {list(engine.registry.keys())})"
        )

    @classmethod
    def from_scenario(
        cls,
        llm_client: Any,
        scenario_config: Any,
        config: Optional[LLMConfig] = None,
        **kwargs: Any,
    ) -> "AdkPyTODTracker":
        """从场景配置创建 AdkPyTODTracker。

        自动根据场景名称注册匹配的演示 API 函数。

        Args:
            llm_client:      LLM 客户端实例（用于提取 LLMConfig；若提供 config 则优先使用 config）。
            scenario_config: ScenarioConfig 实例。
            config:          本地 LLM 配置（可选，优先于 llm_client 内部 config）。
            **kwargs:        忽略未知参数（如 max_history_turns），保持接口宽容。
        """
        if config is None and hasattr(llm_client, "_config"):
            config = llm_client._config
        # 过滤掉三步流程专用参数，保持接口宽容
        kwargs.pop("max_history_turns", None)
        kwargs.pop("prompt_builder", None)

        engine = ExecutionEngine()
        scenario_name = getattr(scenario_config, "name", "")
        key = get_scenario_key(scenario_name)
        if key:
            SCENARIO_API_REGISTRY[key](engine)
            logger.info(f"已为场景 '{scenario_name}' 注册 API: {engine.list_functions()}")
        else:
            logger.warning(f"场景 '{scenario_name}' 无预置 API，运行开放域模式")

        scenario_context = kwargs.pop(
            "scenario_context",
            getattr(scenario_config, "description", ""),
        )
        return cls(engine=engine, config=config, scenario_context=scenario_context, **kwargs)

    async def _get_or_create_session(self) -> str:
        if self._session_id is None:
            session = await self._runner.session_service.create_session(
                app_name=self._runner.app_name, user_id=self._user_id,
            )
            self._session_id = session.id
        return self._session_id

    async def process_turn(
        self,
        user_utterance: str,
        system_utterance: str = "",  # noqa: ARG002 — 保持接口兼容
    ) -> Dict[str, Any]:
        """处理单轮对话。

        ADK 流程：用户输入 → LLM 选择工具 → 执行工具 → LLM 生成回复。

        Returns:
            包含 ``response``、``program_text``、``state``、``execution`` 的字典。
        """
        self.turn_count += 1
        logger.info(f"AdkPyTODTracker 第 {self.turn_count} 轮: {user_utterance}")

        session_id = await self._get_or_create_session()
        new_message = genai_types.Content(
            role="user", parts=[genai_types.Part(text=user_utterance)],
        )

        final_text = ""
        tool_call_parts: List[str] = []

        async for event in self._runner.run_async(
            user_id=self._user_id, session_id=session_id, new_message=new_message,
        ):
            for fc in event.get_function_calls() or []:
                call_repr = f"{fc.name}({fc.args})"
                tool_call_parts.append(call_repr)
                logger.info(f"[Tool Call] {call_repr}")

            for fr in event.get_function_responses() or []:
                if isinstance(fr.response, dict):
                    self.current_state[f"x{self.turn_count}_{fr.name}"] = fr.response
                logger.info(f"[Tool Response] {fr.name}: {str(fr.response)[:120]}")

            if event.is_final_response() and event.content:
                for part in event.content.parts or []:
                    if hasattr(part, "text") and part.text:
                        final_text += part.text

        response = final_text.strip()
        program_text = "\n".join(tool_call_parts) if tool_call_parts else "NONE()"
        logger.info(f"[AdkPyTODTracker] 回复: {response[:80]}")

        return {
            "response": response,
            "program_text": program_text,
            "state": dict(self.current_state),
            "execution": None,
        }

    def get_current_state(self) -> Dict[str, Any]:
        """返回当前累积对话状态（工具执行结果）。"""
        return dict(self.current_state)

    def reset(self) -> None:
        """重置对话状态，创建新的 ADK session。"""
        self._session_id = None
        self.current_state = {}
        self.turn_count = 0
        logger.info("AdkPyTODTracker 对话状态已重置")

    @staticmethod
    def _build_instruction(scenario_context: str) -> str:
        """构建 ADK Agent 的系统指令。"""
        base = (
            "你是一个任务型对话助手。优先调用合适的工具完成任务，"
            "然后根据工具返回结果用自然语言给出友好、简洁的回复。\n\n"
            "规则：\n"
            "1. 尽量调用工具完成任务，而非猜测数据\n"
            "2. 工具返回 hint 字段时，向用户说明需要提供哪些信息\n"
            "3. 工具返回 error 字段时，向用户说明情况并请求补充信息\n"
            "4. 回复语言：中文\n"
        )
        if scenario_context:
            base += f"\n业务场景：{scenario_context}\n"
        return base


# ---------------------------------------------------------------------------
# 别名：PyTODAgent 指向 ADK 版本（快速接入，无需显式 Schema）
# ---------------------------------------------------------------------------

#: ADK 原生追踪器的别名，与早期代码兼容。推荐使用 ``AdkPyTODTracker``。
PyTODAgent = AdkPyTODTracker

