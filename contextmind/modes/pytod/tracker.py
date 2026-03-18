"""
PyTOD Agent — ADK 原生函数调用任务型对话追踪器

利用 Google ADK 原生 Function Calling 替代 PyTOD 自定义程序解析器。
本地 LLM 直接决定调用哪个 API、传入什么参数，并生成自然语言回复。

使用示例::

    from contextmind.modes.pytod import PyTODAgent, ExecutionEngine
    from contextmind.modes.pytod.registry import SCENARIO_API_REGISTRY

    engine = ExecutionEngine()
    SCENARIO_API_REGISTRY["callcenter"](engine)
    agent = PyTODAgent(engine=engine, scenario_context="电商客服场景")
    result = await agent.process_turn("我的订单什么时候发货？")
    print(result["response"])
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from contextmind.infra.llm_client import LLMConfig, create_local_adk_model
from contextmind.infra.logger import get_logger
from contextmind.modes.pytod.execution_engine import ExecutionEngine
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
    "google-adk 未安装，无法创建 PyTODAgent。\n"
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


class PyTODAgent:
    """ADK 原生任务型对话追踪器。

    以 ADK 原生 Function Calling 替代 PyTOD 三步程序解析流程。

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
        instruction = _build_instruction(scenario_context)

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
            f"PyTODAgent 初始化完成 (model={self._llm_config.model}, "
            f"工具: {list(engine.registry.keys())})"
        )

    @classmethod
    def from_scenario(
        cls,
        scenario_config: Any,
        config: Optional[LLMConfig] = None,
        **kwargs: Any,
    ) -> "PyTODAgent":
        """从场景配置创建 PyTODAgent。

        自动根据场景名称注册匹配的演示 API 函数。

        Args:
            scenario_config: ScenarioConfig 实例。
            config: 本地 LLM 配置。
        """
        engine = ExecutionEngine()
        scenario_name = getattr(scenario_config, "name", "")
        key = get_scenario_key(scenario_name)
        if key:
            SCENARIO_API_REGISTRY[key](engine)
            logger.info(f"已为场景 '{scenario_name}' 注册 API: {engine.list_functions()}")
        else:
            logger.warning(f"场景 '{scenario_name}' 无预置 API，运行开放域模式")

        scenario_context = getattr(scenario_config, "description", "")
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
        logger.info(f"PyTODAgent 第 {self.turn_count} 轮: {user_utterance}")

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
        logger.info(f"[PyTODAgent] 回复: {response[:80]}")

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
        logger.info("PyTODAgent 对话状态已重置")


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
