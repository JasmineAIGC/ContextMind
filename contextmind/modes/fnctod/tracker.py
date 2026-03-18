"""
FnCTOD Agent — ADK 原生函数调用对话状态追踪器

基于 Google ADK 原生 Function Calling 能力，将 FunctionManager 中定义的
DomainSpec 自动转换为 ADK FunctionTool，无需手写 XML 提示词。

使用示例::

    from contextmind.modes.fnctod import FnCTODAgent, FunctionManager
    from contextmind.modes.fnctod.schemas import get_function_schema_for_scenario

    fm = FunctionManager()
    fm.add_domain(get_function_schema_for_scenario("callcenter"))
    agent = FnCTODAgent(function_manager=fm)
    updates = await agent.process_turn("我的订单什么时候到？")
    print(agent.get_current_state())
"""

from __future__ import annotations

import inspect
import types
from typing import Any, Dict, List, Optional

from contextmind.infra.llm_client import LLMConfig, create_local_adk_model
from contextmind.infra.logger import get_logger

logger = get_logger(__name__)


def _domain_to_adk_tool(domain_spec: Any) -> Any:
    """将 DomainSpec 转换为 ADK FunctionTool。

    动态生成与 DomainSpec.parameters 一一对应的 Python 函数，
    再包装为 FunctionTool，ADK 会自动从签名生成 JSON Schema。
    """
    from google.adk.tools import FunctionTool  # type: ignore[import]

    param_names: List[str] = [p.name for p in domain_spec.parameters]

    doc_lines = [domain_spec.description, ""]
    for p in domain_spec.parameters:
        mark = "(required)" if p.required else "(optional)"
        enum_info = f", values: {p.enum_values}" if p.enum_values else ""
        doc_lines.append(f"    {p.name}: {p.description} {mark}{enum_info}")

    parameters = [
        inspect.Parameter(
            name,
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=None,
            annotation=Optional[str],
        )
        for name in param_names
    ]
    sig = inspect.Signature(parameters, return_annotation=Dict[str, Any])

    def _extractor(**kwargs: Any) -> Dict[str, Any]:
        return {k: v for k, v in kwargs.items() if v is not None}

    func = types.FunctionType(
        _extractor.__code__,
        _extractor.__globals__,
        name=domain_spec.name,
        argdefs=_extractor.__defaults__,
        closure=_extractor.__closure__,
    )
    func.__doc__ = "\n".join(doc_lines)
    func.__signature__ = sig  # type: ignore[attr-defined]
    return FunctionTool(func=func)


def adk_tools_from_function_manager(function_manager: Any) -> List[Any]:
    """将 FunctionManager 中所有 DomainSpec 转换为 ADK FunctionTool 列表。

    Args:
        function_manager: 已注册了一个或多个 domain 的 FunctionManager 实例。

    Returns:
        可直接传给 ``LlmAgent(tools=...)`` 的 ADK FunctionTool 列表。
    """
    try:
        from google.adk.tools import FunctionTool  # noqa: F401 – ensure available
    except ImportError as exc:
        raise ImportError(
            "google-adk 未安装，无法创建 ADK FunctionTool。\n"
            "请运行: pip install google-adk"
        ) from exc

    tools = [_domain_to_adk_tool(d) for d in function_manager.get_all_domains()]
    logger.info(
        f"adk_tools_from_function_manager: 共 {len(tools)} 个工具: "
        f"{function_manager.get_domain_names()}"
    )
    return tools


class FnCTODAgent:
    """ADK 原生函数调用对话状态追踪器。

    利用 ADK 原生 Function Calling 替代 XML 提示词解析，
    实现对话状态的结构化提取。接口与原 FnCTODTracker 完全兼容。

    参数
    ----
    function_manager : FunctionManager
        已注册 domain 的函数管理器。
    system_instruction : str | None
        系统指令；若为 None 则自动从 FunctionManager 生成。
    config : LLMConfig | None
        本地 LLM 配置；若为 None 则从 ``.env`` 自动加载。
    """

    def __init__(
        self,
        function_manager: Any,
        system_instruction: Optional[str] = None,
        config: Optional[LLMConfig] = None,
    ) -> None:
        try:
            from google.adk.agents import LlmAgent  # type: ignore[import]
            from google.adk.runners import InMemoryRunner  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "google-adk 未安装，无法创建 FnCTODAgent。\n"
                "请运行: pip install google-adk litellm"
            ) from exc

        self._llm_config = config if isinstance(config, LLMConfig) else LLMConfig.from_env()
        adk_model = create_local_adk_model(self._llm_config)
        self.function_manager = function_manager

        if system_instruction is None:
            domain_names = function_manager.get_domain_names()
            system_instruction = (
                "你是一个任务型对话助手，能够通过调用函数提取对话中的关键信息。\n"
                f"可用的业务域: {', '.join(domain_names)}。\n"
                "根据用户的话语调用对应函数，将槽位值作为参数传入。"
            )
        self.system_instruction = system_instruction

        tools = adk_tools_from_function_manager(function_manager)
        self._agent = LlmAgent(
            name="fnctod_agent",
            model=adk_model,
            instruction=system_instruction,
            tools=tools,
        )
        self._runner = InMemoryRunner(agent=self._agent, app_name="contextmind_fnctod")

        self._current_state: Dict[str, Any] = {}
        self._dialogue_history: List[Dict[str, str]] = []
        self.turn_count: int = 0
        self._session_id: Optional[str] = None

        logger.info(
            f"FnCTODAgent 初始化完成 (model={self._llm_config.model}, "
            f"domains={function_manager.get_domain_names()})"
        )

    @classmethod
    def from_scenario(
        cls,
        scenario_config: Any,
        **kwargs: Any,
    ) -> "FnCTODAgent":
        """从场景配置创建 FnCTODAgent。

        Args:
            scenario_config: ScenarioConfig 实例。
            **kwargs: 其他传递给构造函数的参数（如 config、system_instruction）。
        """
        from contextmind.modes.fnctod.function_manager import FunctionManager
        from contextmind.modes.fnctod.schemas import get_function_schema_for_scenario

        fm = FunctionManager()
        try:
            schema = get_function_schema_for_scenario(scenario_config.name)
            fm.add_domain(schema)
        except (ValueError, KeyError):
            if hasattr(scenario_config, "dst_slots") and scenario_config.dst_slots:
                fm.add_domain_from_slots(
                    domain_name=scenario_config.name,
                    domain_description=getattr(scenario_config, "description", scenario_config.name),
                    slots=dict(scenario_config.dst_slots),
                )
            else:
                logger.warning(f"场景 '{scenario_config.name}' 无预定义 schema，使用空 FunctionManager")
        return cls(function_manager=fm, **kwargs)

    async def _get_or_create_session(self) -> str:
        if self._session_id is None:
            session = await self._runner.session_service.create_session(
                app_name="contextmind_fnctod", user_id="default_user",
            )
            self._session_id = session.id
        return self._session_id

    def reset(self) -> None:
        """重置对话状态，开始新会话。"""
        self._current_state = {}
        self._dialogue_history = []
        self.turn_count = 0
        self._session_id = None

    async def process_turn(self, user_utterance: str, **kwargs: Any) -> Dict[str, Any]:
        """处理单轮用户输入，通过 ADK 原生 Function Calling 提取槽位。

        Returns:
            本轮新增或更新的状态条目字典。
        """
        from google.genai import types as genai_types  # type: ignore[import]

        session_id = await self._get_or_create_session()
        self.turn_count += 1

        content = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=user_utterance)],
        )

        turn_updates: Dict[str, Any] = {}
        final_text = ""

        async for event in self._runner.run_async(
            user_id="default_user",
            session_id=session_id,
            new_message=content,
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "function_call") and part.function_call:
                        fc = part.function_call
                        filtered = {k: v for k, v in (fc.args or {}).items() if v not in (None, "", [])}
                        turn_updates.update(filtered)
                        logger.debug(f"[turn {self.turn_count}] function call '{fc.name}': {filtered}")
                    if event.is_final_response() and hasattr(part, "text") and part.text:
                        final_text += part.text

        self._current_state.update(turn_updates)
        self._dialogue_history.append({"role": "user", "content": user_utterance})
        if final_text:
            self._dialogue_history.append({"role": "assistant", "content": final_text.strip()})

        logger.info(f"[turn {self.turn_count}] 更新: {turn_updates}, 累积: {self._current_state}")
        return turn_updates

    def get_current_state(self) -> Dict[str, Any]:
        """返回累积的对话状态。"""
        return dict(self._current_state)
