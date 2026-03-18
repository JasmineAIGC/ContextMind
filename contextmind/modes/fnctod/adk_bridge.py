"""
FnCTOD × Google ADK 集成桥接模块

将 FnCTOD 的 FunctionManager / DomainSpec 体系与 Google ADK
（Agent Development Kit）原生 Function Calling 能力打通。
LLM 通过 ``.env`` 配置的本地 vLLM/OpenAI 兼容端点（LiteLlm）接入。

模块提供两个主要工具
--------------------

1. ``adk_tools_from_function_manager(function_manager)``
   将 :class:`~contextmind.modes.fnctod.FunctionManager` 中所有已注册的
   DomainSpec 转换为 ADK ``FunctionTool`` 列表。
   ADK 会自动把 DomainSpec 的参数定义生成 JSON Schema 并注入到本地 LLM
   的 function-calling 协议中，无需再手写 XML 格式的 function_call 提示词。

2. ``AdkFnCTODAgent``
   ADK 原生的 FnCTOD 代理，提供与 :class:`~contextmind.modes.fnctod.FnCTODTracker`
   相同的外部接口（``process_turn`` / ``get_current_state`` / ``reset``），
   但底层改用 ADK 原生 Function Calling + InMemoryRunner + 本地 LLM。

集成后的好处
------------
* **无需手写 XML 提示词**：ADK 自动处理 function call 的序列化/反序列化。
* **原生 function calling 精度更高**：相比"用提示词模拟"，原生 function calling
  在槽位提取准确率和多 domain 判断上显著提升。
* **代码更少，扩展更容易**：新增 domain 只需往 FunctionManager 里
  ``add_domain()``，无需修改提示词模板。
* **本地部署**：通过 LiteLlm 接入 .env 配置的本地 vLLM 端点。

使用示例
--------
::

    from contextmind.modes.fnctod import FunctionManager
    from contextmind.modes.fnctod.adk_bridge import (
        adk_tools_from_function_manager,
        AdkFnCTODAgent,
    )
    from contextmind.scenarios.registry import scenario_registry

    scenario = scenario_registry.get("callcenter")
    function_manager = FunctionManager()
    # ... add_domain 或 add_domain_from_slots ...

    # 方式一：只需要 ADK FunctionTool 列表（自行集成到 LlmAgent）
    tools = adk_tools_from_function_manager(function_manager)

    # 方式二：直接使用完整代理（接口与 FnCTODTracker 兼容）
    agent = AdkFnCTODAgent(
        function_manager=function_manager,
    )
    result = await agent.process_turn("我的订单什么时候到？")
    print(agent.get_current_state())
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from contextmind.infra.llm_client import LLMConfig

from contextmind.infra.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 辅助函数：DomainSpec → ADK FunctionTool
# ---------------------------------------------------------------------------

def adk_tools_from_function_manager(function_manager: Any) -> List[Any]:
    """将 FunctionManager 中所有已注册的 DomainSpec 转换为 ADK FunctionTool 列表。

    每个 DomainSpec 对应一个可被本地 LLM 原生调用的 ADK ``FunctionTool``。
    ADK 会从函数签名和 docstring 自动生成 JSON Schema；此处我们为每个 domain
    动态创建一个 Python 函数，其参数签名完全对应 DomainSpec 的槽位定义。

    Args:
        function_manager: 已注册了一个或多个 domain 的 FunctionManager 实例。

    Returns:
        可直接传给 ``LlmAgent(tools=...)`` 的 ADK FunctionTool 列表。

    Raises:
        ImportError: 若 ``google-adk`` 未安装。
    """
    try:
        from google.adk.tools import FunctionTool  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "google-adk 未安装，无法创建 ADK FunctionTool。\n"
            "请运行: pip install google-adk"
        ) from exc

    wrapped_tools: List[Any] = []

    for domain in function_manager.get_all_domains():
        # 为每个 DomainSpec 动态生成对应的 Python 函数
        adk_tool = _domain_spec_to_function_tool(domain, FunctionTool)
        wrapped_tools.append(adk_tool)
        logger.debug(f"DomainSpec '{domain.name}' → ADK FunctionTool 包装完成")

    logger.info(
        f"adk_tools_from_function_manager: 共包装 {len(wrapped_tools)} 个工具: "
        f"{[d.name for d in function_manager.get_all_domains()]}"
    )
    return wrapped_tools


def _domain_spec_to_function_tool(domain_spec: Any, FunctionTool: Any) -> Any:
    """将单个 DomainSpec 转换为 ADK FunctionTool。

    使用 :mod:`inspect` 和 :class:`types.FunctionType` 安全地动态创建
    Python 函数，参数列表与 DomainSpec.parameters 一一对应，完全避免
    ``exec()`` / ``eval()`` 带来的安全隐患。

    Args:
        domain_spec: DomainSpec 实例。
        FunctionTool: google.adk.tools.FunctionTool 类。

    Returns:
        ADK FunctionTool 实例。
    """
    import inspect
    import types

    param_names: List[str] = [p.name for p in domain_spec.parameters]

    # 构造 docstring：域描述 + 参数说明（英文标记，兼容 ASCII 环境）
    doc_lines = [domain_spec.description, ""]
    for p in domain_spec.parameters:
        required_mark = "(required)" if p.required else "(optional)"
        enum_info = f", values: {p.enum_values}" if p.enum_values else ""
        doc_lines.append(f"    {p.name}: {p.description} {required_mark}{enum_info}")
    docstring = "\n".join(doc_lines)

    # 构建函数签名（全部参数带 Optional[str] 默认值 None）
    parameters = []
    for name in param_names:
        param = inspect.Parameter(
            name,
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=None,
            annotation=Optional[str],
        )
        parameters.append(param)
    sig = inspect.Signature(parameters, return_annotation=Dict[str, Any])

    def _slot_extractor(**kwargs: Any) -> Dict[str, Any]:
        return {k: v for k, v in kwargs.items() if v is not None}

    # 使用 types.FunctionType 克隆 bytecode，注入正确的签名和名称
    generated_func = types.FunctionType(
        _slot_extractor.__code__,
        _slot_extractor.__globals__,
        name=domain_spec.name,
        argdefs=_slot_extractor.__defaults__,
        closure=_slot_extractor.__closure__,
    )
    generated_func.__doc__ = docstring
    generated_func.__signature__ = sig  # type: ignore[attr-defined]

    return FunctionTool(func=generated_func)


# ---------------------------------------------------------------------------
# AdkFnCTODAgent：ADK 原生 FnCTOD 代理
# ---------------------------------------------------------------------------

class AdkFnCTODAgent:
    """ADK 原生 FnCTOD 代理。

    提供与 :class:`~contextmind.modes.fnctod.FnCTODTracker` 相同的
    公共接口（``process_turn`` / ``get_current_state`` / ``reset`` /
    ``from_scenario``），但底层改用 ADK 原生 Function
    Calling + 本地 LLM（via LiteLlm）替代手工 XML 提示词解析。

    集成优势
    --------
    * **无需 XML 解析**：LLM 原生 function calling 输出结构化参数，
      直接写入状态字典，不再依赖脆弱的正则提取。
    * **零改造成本**：调用方代码无需修改，直接替换 ``FnCTODTracker``。
    * **多 domain 路由自动化**：LLM 自主选择调用哪个 function，
      无需显式的两阶段 domain 选择逻辑。

    参数
    ----
    function_manager : FunctionManager
        已注册 domain 的函数管理器。
    system_instruction : str | None
        系统指令；若为 None 则自动从 FunctionManager 生成。
    config : LLMConfig | None
        本地 LLM 配置；若为 None 则从 ``.env`` 环境变量自动加载。
    """

    #: sync process_turn 的最大等待秒数
    SYNC_TURN_TIMEOUT: float = 120.0

    def __init__(
        self,
        function_manager: Any,
        system_instruction: Optional[str] = None,
        config: Optional["LLMConfig"] = None,
    ) -> None:
        try:
            from google.adk.agents import LlmAgent  # type: ignore[import]
            from google.adk.runners import InMemoryRunner  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "google-adk 未安装，无法创建 AdkFnCTODAgent。\n"
                "请运行: pip install google-adk litellm"
            ) from exc

        from contextmind.infra.llm_client import LLMConfig, create_local_adk_model
        self._llm_config = config if isinstance(config, LLMConfig) else LLMConfig.from_env()
        adk_model = create_local_adk_model(self._llm_config)

        self.function_manager = function_manager

        # 自动生成系统指令（若未提供）
        if system_instruction is None:
            domain_names = function_manager.get_domain_names()
            system_instruction = (
                "你是一个任务型对话助手，能够通过调用函数提取对话中的关键信息。\n"
                f"可用的业务域: {', '.join(domain_names)}。\n"
                "根据用户的话语调用对应函数，将槽位值作为参数传入。"
            )
        self.system_instruction = system_instruction

        # 构建 ADK FunctionTool 列表
        self._tools = adk_tools_from_function_manager(function_manager)

        # 构建 ADK agent（无状态，每轮复用同一 runner）
        self._agent = LlmAgent(
            name="fnctod_adk_agent",
            model=adk_model,
            instruction=system_instruction,
            tools=self._tools,
        )
        self._runner = InMemoryRunner(
            agent=self._agent,
            app_name="contextmind_fnctod",
        )

        # 对话状态
        self._current_state: Dict[str, Any] = {}
        self._dialogue_history: List[Dict[str, str]] = []
        self.turn_count: int = 0
        self._session_id: Optional[str] = None

        logger.info(
            f"AdkFnCTODAgent 初始化完成 (model={self._llm_config.model}, "
            f"domains={function_manager.get_domain_names()})"
        )

    # ------------------------------------------------------------------ #
    # 工厂方法
    # ------------------------------------------------------------------ #

    @classmethod
    def from_scenario(
        cls,
        scenario_config: Any,
        **kwargs: Any,
    ) -> "AdkFnCTODAgent":
        """从场景配置创建 AdkFnCTODAgent。

        Args:
            scenario_config: ScenarioConfig 实例。
            **kwargs: 其他传递给构造函数的参数（如 config、system_instruction）。

        Returns:
            初始化完成的 AdkFnCTODAgent 实例。
        """
        from contextmind.modes.fnctod import FunctionManager
        from contextmind.modes.fnctod.schemas import get_function_schema_for_scenario

        function_manager = FunctionManager()
        schema = get_function_schema_for_scenario(scenario_config.name)
        if schema is not None:
            function_manager.add_domain(schema)
        elif hasattr(scenario_config, "dst_slots") and scenario_config.dst_slots:
            function_manager.add_domain_from_slots(
                domain_name=scenario_config.name,
                domain_description=getattr(scenario_config, "description", scenario_config.name),
                slots={k: v for k, v in scenario_config.dst_slots.items()},
            )
        else:
            logger.warning(
                f"场景 '{scenario_config.name}' 没有预定义 FunctionSchema，"
                "AdkFnCTODAgent 将使用空 FunctionManager"
            )

        return cls(function_manager=function_manager, **kwargs)

    # ------------------------------------------------------------------ #
    # 会话管理
    # ------------------------------------------------------------------ #

    async def _get_or_create_session(self) -> str:
        """懒加载创建 ADK session，同一对话生命周期内复用。"""
        if self._session_id is None:
            session = await self._runner.session_service.create_session(
                app_name="contextmind_fnctod",
                user_id="default_user",
            )
            self._session_id = session.id
            logger.debug(f"AdkFnCTODAgent: session 已创建 (id={self._session_id})")
        return self._session_id

    def reset(self) -> None:
        """重置对话状态，开始新会话（与 FnCTODTracker.reset 兼容）。"""
        self._current_state = {}
        self._dialogue_history = []
        self.turn_count = 0
        self._session_id = None
        logger.debug("AdkFnCTODAgent: 状态已重置")

    # ------------------------------------------------------------------ #
    # 核心处理逻辑
    # ------------------------------------------------------------------ #

    async def process_turn(
        self,
        user_utterance: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """处理单轮用户输入，通过 ADK native function calling 提取槽位。

        Args:
            user_utterance: 用户本轮输入文本。
            **kwargs: 忽略，保持与 FnCTODTracker 签名兼容。

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
            # 捕获函数调用事件，提取槽位参数
            if (
                hasattr(event, "content")
                and event.content
                and event.content.parts
            ):
                for part in event.content.parts:
                    # ADK function call part
                    if hasattr(part, "function_call") and part.function_call:
                        fc = part.function_call
                        args = dict(fc.args or {})
                        # 只收录非空参数
                        filtered = {k: v for k, v in args.items() if v not in (None, "", [])}
                        turn_updates.update(filtered)
                        logger.debug(
                            f"[turn {self.turn_count}] ADK function call "
                            f"'{fc.name}': {filtered}"
                        )
                    # 最终文本回复
                    if (
                        event.is_final_response()
                        and hasattr(part, "text")
                        and part.text
                    ):
                        final_text += part.text

        # 累积状态
        self._current_state.update(turn_updates)

        # 记录历史
        self._dialogue_history.append({
            "role": "user",
            "content": user_utterance,
        })
        if final_text:
            self._dialogue_history.append({
                "role": "assistant",
                "content": final_text.strip(),
            })

        logger.info(
            f"[turn {self.turn_count}] 本轮更新: {turn_updates}, "
            f"累积状态: {self._current_state}"
        )
        return turn_updates

    def get_current_state(self) -> Dict[str, Any]:
        """返回截至当前的累积对话状态（与 FnCTODTracker.get_current_state 兼容）。"""
        return dict(self._current_state)

    def process_turn_sync(
        self,
        user_utterance: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """``process_turn`` 的同步版本，供非 async 调用方使用。"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    asyncio.run,
                    self.process_turn(user_utterance, **kwargs),
                )
                return future.result(timeout=self.SYNC_TURN_TIMEOUT)
        else:
            return asyncio.run(self.process_turn(user_utterance, **kwargs))
