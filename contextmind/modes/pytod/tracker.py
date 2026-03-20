"""
PyTOD Tracker — 两种实现版本

PyTODTracker（论文原版三步流程）
    严格遵循论文 "Task-Oriented Dialogue as Dataflow Synthesis"，
    显式执行 AP → EE → DM 三步：
        Step 1  Action Parser (AP)：LLM 根据对话历史 + Schema 生成 Python-like 程序
        Step 2  Execution Engine (EE)：安全解析并执行程序
        Step 3  Dialogue Manager (DM)：LLM 根据执行结果生成自然语言回复
    适合研究复现、可解释性分析、需要显式程序中间表示的场景。

AdkPyTODTracker（ADK 原生函数调用实现）
    以 ADK 原生 Function Calling 替代显式三步流程；LLM 直接决定调用哪个 API
    并生成回复，省去手工程序解析，适合生产部署。

使用示例::

    # 论文三步流程版本（推荐用于研究）
    from contextmind.modes.pytod import PyTODTracker, ExecutionEngine
    from contextmind.infra.llm_client import AdkLLMClient

    engine = ExecutionEngine()
    # ... 注册 API ...
    llm = AdkLLMClient()
    tracker = PyTODTracker(llm_client=llm, engine=engine)
    result = await tracker.process_turn("查询我的账户余额")
    print(result["program_text"])   # AP 生成的程序
    print(result["response"])       # DM 生成的回复

    # ADK 原生版本（推荐用于生产）
    from contextmind.modes.pytod import AdkPyTODTracker
    from contextmind.scenarios import get_callcenter_scenario

    config = get_callcenter_scenario()
    tracker = AdkPyTODTracker.from_scenario(llm, config)
    result = await tracker.process_turn("查询我的账户余额")
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

from contextmind.infra.llm_client import LLMConfig, create_local_adk_model
from contextmind.infra.logger import get_logger
from contextmind.modes.pytod.execution_engine import ExecutionEngine, ProgramExecutionResult
from contextmind.modes.pytod.prompts import ConversationTurn, PyTODPromptBuilder
from contextmind.modes.pytod.registry import SCENARIO_API_REGISTRY, get_scenario_key
from contextmind.modes.pytod.schemas import ServiceSchema

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


def _load_scenario_schema(key: Optional[str]) -> Optional[ServiceSchema]:
    """按场景 key 懒加载对应的预定义 ServiceSchema。

    避免在顶层导入可能不存在的场景模块，仅在需要时动态加载。

    Args:
        key: SCENARIO_API_REGISTRY 中的场景键（如 ``"anyihua"``）。

    Returns:
        对应场景的 ServiceSchema，找不到时返回 None。
    """
    if key in ("anyihua", "安逸花", "安逸花外呼", "安逸花外呼促活"):
        try:
            from contextmind.scenarios.anyihua.generation.schema import (  # type: ignore[import]
                ANYIHUA_SCHEMA,
            )
            return ANYIHUA_SCHEMA
        except ImportError:
            logger.warning("无法加载 ANYIHUA_SCHEMA，将不使用 schema 约束")
    return None


# ---------------------------------------------------------------------------
# PyTODTracker — 论文原版三步流程（AP → EE → DM）
# ---------------------------------------------------------------------------

class PyTODTracker:
    """论文原版三步流程 PyTOD 追踪器（Action Parser → Execution Engine → Dialogue Manager）。

    严格遵循论文 "Task-Oriented Dialogue as Dataflow Synthesis"：
    - Step 1 AP：LLM 根据对话历史和 Schema 生成 Python-like 程序
    - Step 2 EE：ExecutionEngine 安全解析并执行程序，填充变量值
    - Step 3 DM：LLM 根据执行结果生成自然语言回复

    与 ``AdkPyTODTracker`` 的区别：
    - 有显式的程序中间表示（program_text），可解释性更强
    - 每轮对话调用 LLM 两次（AP + DM），延迟略高
    - Schema 通过 PyTODPromptBuilder 注入 AP prompt，严格约束意图和槽位

    参数
    ----
    llm_client : Any
        实现 ``chat_async(messages: List[dict]) -> str`` 的 LLM 客户端
        （如 ``AdkLLMClient``）。
    engine : ExecutionEngine
        已注册 API 函数的执行引擎。
    schema : ServiceSchema | None
        服务 Schema，约束 AP 阶段可生成的意图和槽位。
        为 None 时 PyTODPromptBuilder 使用空 Schema（开放域模式）。
    scenario_context : str
        业务场景描述，嵌入 AP 和 DM 的 system prompt。
    max_history_turns : int
        AP/DM prompt 中保留的最近历史轮次数。
    """

    def __init__(
        self,
        llm_client: Any,
        engine: ExecutionEngine,
        schema: Optional[ServiceSchema] = None,
        scenario_context: str = "",
        max_history_turns: int = 10,
    ) -> None:
        self.llm_client = llm_client
        self.engine = engine
        self.schema = schema or ServiceSchema(service_name="default", description="")
        self.scenario_context = scenario_context
        self.prompt_builder = PyTODPromptBuilder(
            schema=self.schema,
            max_history_turns=max_history_turns,
        )
        self._history: List[ConversationTurn] = []
        self.current_state: Dict[str, Any] = {}
        self.api_call_log: List[Dict[str, Any]] = []
        self.turn_count: int = 0
        # 各步骤耗时（web_demo 的 timing_breakdown 会合并此字典）
        self.step_timings: Dict[str, float] = {}

        logger.info(
            f"PyTODTracker 初始化完成 (schema={self.schema.service_name}, "
            f"APIs: {engine.list_functions()})"
        )

    @classmethod
    def from_scenario(
        cls,
        llm_client: Any,
        scenario_config: Any,
        config: Optional[Any] = None,  # noqa: ARG003 — 保持接口兼容
        **kwargs: Any,
    ) -> "PyTODTracker":
        """从场景配置创建 PyTODTracker。

        自动注册场景 API、加载 ServiceSchema 并填充场景描述。

        Args:
            llm_client:      LLM 客户端（如 ``AdkLLMClient``）。
            scenario_config: ScenarioConfig 实例。
            config:          忽略（保持与 AdkPyTODTracker.from_scenario 接口一致）。
            **kwargs:        忽略未知参数，保持接口宽容。
        """
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

        schema = _load_scenario_schema(key)
        scenario_context = kwargs.pop(
            "scenario_context",
            getattr(scenario_config, "description", ""),
        )
        return cls(
            llm_client=llm_client,
            engine=engine,
            schema=schema,
            scenario_context=scenario_context,
            **kwargs,
        )

    async def process_turn(
        self,
        user_utterance: str,
        system_utterance: str = "",  # noqa: ARG002 — 保持接口兼容
    ) -> Dict[str, Any]:
        """执行一轮三步对话处理（AP → EE → DM）。

        Returns:
            包含 ``response``、``program_text``、``state``、``execution`` 的字典。
            ``step_timings`` 属性同步更新为各步骤耗时。
        """
        self.turn_count += 1
        logger.info(f"PyTODTracker 第 {self.turn_count} 轮 | AP→EE→DM | 用户: {user_utterance}")
        self.step_timings = {}

        # ------------------------------------------------------------------ #
        # Step 1: Action Parser (AP)
        # ------------------------------------------------------------------ #
        t0 = time.time()
        ap_messages = self.prompt_builder.build_action_parser_prompt(
            self._history, user_utterance, self.scenario_context,
        )
        program_text: str = await self.llm_client.chat_async(ap_messages)
        # 剥除 LLM 可能输出的 markdown 代码块包裹
        program_text = re.sub(r"```[^\n]*\n?", "", program_text).strip()
        self.step_timings["AP (动作解析)"] = round(time.time() - t0, 3)
        logger.info(f"[AP] 程序: {program_text[:80]}")

        # ------------------------------------------------------------------ #
        # Step 2: Execution Engine (EE)
        # ------------------------------------------------------------------ #
        t1 = time.time()
        execution_result: ProgramExecutionResult = self.engine.execute_program(program_text)
        self.step_timings["EE (执行引擎)"] = round(time.time() - t1, 3)

        # 将本轮 API 调用结果合并进累积状态，并记录调用日志
        if execution_result.variable_values:
            for var, val in execution_result.variable_values.items():
                self.current_state[var] = val
                self.api_call_log.append({
                    "turn": self.turn_count,
                    "variable": var,
                    "result": val,
                })
        if not execution_result.success:
            logger.warning(f"[EE] 执行错误: {execution_result.errors}")

        # ------------------------------------------------------------------ #
        # Step 3: Dialogue Manager (DM)
        # ------------------------------------------------------------------ #
        t2 = time.time()
        dm_messages = self.prompt_builder.build_dm_prompt(
            self._history, user_utterance, program_text, execution_result, self.scenario_context,
        )
        response: str = await self.llm_client.chat_async(dm_messages)
        response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
        self.step_timings["DM (对话管理)"] = round(time.time() - t2, 3)
        logger.info(f"[DM] 回复: {response[:80]}")

        # 更新对话历史
        self._history.append(ConversationTurn(role="user", content=user_utterance))
        self._history.append(ConversationTurn(role="assistant", content=response))

        return {
            "response": response,
            "program_text": program_text,
            "state": dict(self.current_state),
            "execution": execution_result,
        }

    def get_current_state(self) -> Dict[str, Any]:
        """返回当前累积对话状态（API 执行结果 + API 调用日志）。"""
        state = dict(self.current_state)
        if self.api_call_log:
            state["_api_call_log"] = list(self.api_call_log)
        return state

    def reset(self) -> None:
        """重置对话状态，开始新的会话。"""
        self._history = []
        self.current_state = {}
        self.api_call_log = []
        self.turn_count = 0
        self.step_timings = {}
        logger.info("PyTODTracker 对话状态已重置")


# ---------------------------------------------------------------------------
# AdkPyTODTracker — ADK 原生函数调用实现
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
    schema : ServiceSchema | None
        服务 Schema；若提供则将意图/槽位摘要嵌入 system instruction，
        帮助 LLM 选择更准确的工具（问题5：轻量意图约束方案）。
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
        schema: Optional[ServiceSchema] = None,
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
        instruction = self._build_instruction(scenario_context, schema)

        self._agent = LlmAgent(
            name="pytod_agent",
            model=adk_model,
            instruction=instruction,
            tools=tools,
        )
        self._runner = InMemoryRunner(agent=self._agent, app_name=app_name)
        self._session_id: Optional[str] = None

        self.current_state: Dict[str, Any] = {}
        # api_call_log: 按轮次记录每次工具调用的 {name, args, result}
        self.api_call_log: list = []
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

        自动根据场景名称注册匹配的演示 API 函数，并懒加载对应场景的
        ServiceSchema 注入 system instruction，实现轻量意图约束（问题5方案）。

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

        # 自动加载场景 schema，嵌入 instruction 实现意图约束
        schema = kwargs.pop("schema", None) or _load_scenario_schema(key)

        scenario_context = kwargs.pop(
            "scenario_context",
            getattr(scenario_config, "description", ""),
        )
        return cls(
            engine=engine,
            config=config,
            scenario_context=scenario_context,
            schema=schema,
            **kwargs,
        )

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
        # 本轮工具调用的中间结构：{fn_name -> {args, result}}
        turn_calls: Dict[str, Any] = {}

        async for event in self._runner.run_async(
            user_id=self._user_id, session_id=session_id, new_message=new_message,
        ):
            for fc in event.get_function_calls() or []:
                call_repr = f"{fc.name}({fc.args})"
                tool_call_parts.append(call_repr)
                # 记录调用参数，等响应到来时补充 result
                turn_calls[fc.name] = {"args": dict(fc.args or {}), "result": None}
                logger.info(f"[Tool Call] {call_repr}")

            for fr in event.get_function_responses() or []:
                if isinstance(fr.response, dict):
                    self.current_state[f"x{self.turn_count}_{fr.name}"] = fr.response
                # 补充对应工具的执行结果
                if fr.name in turn_calls:
                    turn_calls[fr.name]["result"] = fr.response
                logger.info(f"[Tool Response] {fr.name}: {str(fr.response)[:120]}")

            if event.is_final_response() and event.content:
                for part in event.content.parts or []:
                    if hasattr(part, "text") and part.text:
                        # 跳过思考内容（reasoning_content 被 ADK 转为 thought=True 的 part）
                        if getattr(part, "thought", False):
                            continue
                        final_text += part.text

        # 将本轮工具调用记录追加到 api_call_log（即使没有调用也记录空占位）
        if turn_calls:
            for fn_name, call_info in turn_calls.items():
                self.api_call_log.append({
                    "turn": self.turn_count,
                    "api": fn_name,
                    "args": call_info["args"],
                    "result": call_info["result"],
                })

        # 剥除思考模型可能残留的 <think>…</think> 推理块
        final_text = re.sub(r"<think>.*?</think>", "", final_text, flags=re.DOTALL)
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
        """返回当前累积对话状态（工具执行结果 + API 调用日志）。"""
        state = dict(self.current_state)
        if self.api_call_log:
            state["_api_call_log"] = list(self.api_call_log)
        return state

    def reset(self) -> None:
        """重置对话状态，创建新的 ADK session。"""
        self._session_id = None
        self.current_state = {}
        self.api_call_log = []
        self.turn_count = 0
        logger.info("AdkPyTODTracker 对话状态已重置")

    @staticmethod
    def _build_instruction(
        scenario_context: str,
        schema: Optional[ServiceSchema] = None,
    ) -> str:
        """构建 ADK Agent 的系统指令。

        当提供 ServiceSchema 时，将意图/槽位摘要嵌入指令，
        帮助 LLM 了解业务约束并选择正确的工具（轻量意图路由方案）。
        这比将所有 API 签名全量展示更结构化，且随 API 数量增长也不会让 LLM 迷失。
        """
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
        if schema is not None and schema.service_name != "default":
            base += f"\n{schema.to_prompt_text()}\n"
        return base



