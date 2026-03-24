"""
FnCTOD Agent — ADK 原生函数调用对话状态追踪器

基于 "Large Language Models as Zero-shot Dialogue State Tracker through Function Calling"
（ACL 2024）论文思想，将对话状态追踪（DST）转化为函数调用：每个业务域对应一个函数，
槽位对应参数，LLM 通过调用函数提取对话中的槽位值，实现零样本 DST。

使用示例::

    from contextmind.modes.fnctod import FnCTODTracker, FunctionManager
    from contextmind.modes.fnctod.schemas import get_function_schema_for_scenario

    fm = FunctionManager()
    fm.add_domain(get_function_schema_for_scenario("callcenter"))
    tracker = FnCTODTracker(function_manager=fm)
    updates = await tracker.process_turn("我的订单什么时候到？")
    print(tracker.get_current_state())
"""

from __future__ import annotations

import inspect
import types
from typing import Any, Dict, List, Optional

from contextmind.infra.llm_client import LLMConfig, create_local_adk_model
from contextmind.infra.logger import get_logger
from contextmind.modes.fnctod.function_manager import FunctionManager
from contextmind.modes.fnctod.schemas import get_function_schema_for_scenario

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
    "google-adk 未安装，无法创建 FnCTODTracker。\n"
    "请运行: pip install google-adk litellm"
)


def _domain_to_adk_tool(domain_spec: Any) -> Any:
    """将 DomainSpec 转换为 ADK FunctionTool。

    动态生成与 DomainSpec.parameters 一一对应的 Python 函数，
    再包装为 FunctionTool，ADK 会自动从签名生成 JSON Schema。
    """
    if not _ADK_AVAILABLE:
        raise ImportError(_ADK_INSTALL_MSG)

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
    if not _ADK_AVAILABLE:
        raise ImportError(_ADK_INSTALL_MSG)

    tools = [_domain_to_adk_tool(d) for d in function_manager.get_all_domains()]
    logger.info(
        f"adk_tools_from_function_manager: 共 {len(tools)} 个工具: "
        f"{function_manager.get_domain_names()}"
    )
    return tools


class FnCTODTracker:
    """ADK 原生函数调用对话状态追踪器（FnCTOD）。

    利用 ADK 原生 Function Calling 实现零样本 DST：
    每个业务域映射为一个函数，槽位映射为参数，LLM 通过调用函数
    逐轮提取并累积对话状态（Dialogue State Tracking）。

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
        if not _ADK_AVAILABLE:
            raise ImportError(_ADK_INSTALL_MSG)

        self._llm_config = config if isinstance(config, LLMConfig) else LLMConfig.from_env()
        adk_model = create_local_adk_model(self._llm_config)
        self.function_manager = function_manager

        if system_instruction is None:
            domain_names = function_manager.get_domain_names()
            system_instruction = (
                "你是一个任务型对话助手，通过调用函数提取对话中的关键信息，然后给出自然语言回复。\n"
                f"可用的业务域: {', '.join(domain_names)}。\n"
                "处理规则：\n"
                "1. 每轮对话调用相应函数，一次性填入对话中已识别的槽位值；\n"
                "2. 未在本轮对话中提及的槽位保持为空，不要猜测；\n"
                "3. 函数调用完成后，立即用简洁的中文给出对话回复。"
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
        self.last_turn_updates: Dict[str, Any] = {}

        logger.info(
            f"FnCTODTracker 初始化完成 (model={self._llm_config.model}, "
            f"domains={function_manager.get_domain_names()})"
        )

    @classmethod
    def from_scenario(
        cls,
        llm_client: Any,
        scenario_config: Any,
        **kwargs: Any,
    ) -> "FnCTODTracker":
        """从场景配置创建 FnCTODTracker。

        Args:
            llm_client:      LLM 客户端实例（用于提取 LLMConfig；若传入 LLMConfig 则直接使用）。
            scenario_config: ScenarioConfig 实例。
            **kwargs: 其他传递给构造函数的参数（如 system_instruction）。
                      未知参数（如 use_two_stage、max_history_turns）会被安全过滤。
        """
        # 若调用方直接传入 LLMConfig，则优先使用；否则尝试从 llm_client 中提取
        config: Any = kwargs.pop("config", None)
        if config is None and hasattr(llm_client, "_config"):
            config = llm_client._config
        # 过滤掉本类构造函数不认识的参数，保持接口宽容
        kwargs.pop("use_two_stage", None)
        kwargs.pop("max_history_turns", None)
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
        if config is not None:
            kwargs["config"] = config
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
        self.last_turn_updates = {}

    async def process_turn(self, user_utterance: str, **kwargs: Any) -> Dict[str, Any]:
        """处理单轮用户输入，通过 ADK 原生 Function Calling 提取槽位并生成回复。

        Returns:
            包含以下键的字典:
                - ``response``  : LLM 生成的自然语言回复文本
                - ``state``     : 当前累积的对话状态（所有轮次槽位合并）
                - ``updates``   : 本轮新增或更新的槽位条目
        """
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
                        if not getattr(part, "thought", False):
                            final_text += part.text

        self._current_state.update(turn_updates)
        self.last_turn_updates = turn_updates
        self._dialogue_history.append({"role": "user", "content": user_utterance})
        response_text = final_text.strip()
        if response_text:
            self._dialogue_history.append({"role": "assistant", "content": response_text})

        logger.info(f"[turn {self.turn_count}] 更新: {turn_updates}, 累积: {self._current_state}")
        return {
            "response": response_text,
            "state": dict(self._current_state),
            "updates": turn_updates,
        }

    def get_current_state(self) -> Dict[str, Any]:
        """返回累积的对话状态。"""
        return dict(self._current_state)
