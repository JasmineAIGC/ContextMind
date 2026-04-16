"""
FnCTOD Agent — ADK 原生函数调用对话状态追踪器

基于 "Large Language Models as Zero-shot Dialogue State Tracker through Function Calling"
（ACL 2024）论文思想，将对话状态追踪（DST）转化为函数调用：每个业务域对应一个函数，
槽位对应参数，LLM 通过调用函数提取对话中的槽位值，实现零样本 DST。

FnCTOD 不在算法代码内部硬编码场景 Schema 数据。所有 Schema 均通过外部文件传入：

使用示例::

    from contextmind.modes.fnctod import FnCTODTracker, FunctionManager
    from contextmind.modes.fnctod.schemas import load_domain_spec_from_file

    domain_spec = load_domain_spec_from_file("schema/callcenter_fnctod_domain.json")
    fm = FunctionManager()
    fm.add_domain(domain_spec)
    tracker = FnCTODTracker(function_manager=fm)
    updates = await tracker.process_turn("我的订单什么时候到？")
    print(tracker.get_current_state())
"""

from __future__ import annotations

import inspect
import json
import re
import types
from typing import Any, Dict, List, Optional, Tuple

from contextmind.infra.llm_client import AdkLLMClient, LLMConfig, create_local_adk_model
from contextmind.infra.logger import get_logger
from contextmind.modes.fnctod.function_manager import FunctionManager

from google.adk.agents import LlmAgent  # type: ignore[import]
from google.adk.runners import InMemoryRunner  # type: ignore[import]
from google.adk.tools import FunctionTool  # type: ignore[import]
from google.genai import types as genai_types  # type: ignore[import]

logger = get_logger(__name__)


def _domain_to_adk_tool(domain_spec: Any) -> Any:
    """将 DomainSpec 转换为 ADK FunctionTool。

    动态生成与 DomainSpec.parameters 一一对应的 Python 函数，
    再包装为 FunctionTool，ADK 会自动从签名生成 JSON Schema。
    """
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
        若同时提供 ``scenario_context``，背景信息会追加到自动生成的指令末尾。
    scenario_context : str
        业务场景背景描述（可选）。追加到系统指令中，让 LLM 了解对话所处的
        业务场景（如"安逸花外呼促活"），从而生成符合场景的回复。
        若提供了显式的 ``system_instruction``，则此参数被忽略。
    config : LLMConfig | None
        本地 LLM 配置；若为 None 则从 ``.env`` 自动加载。
    """

    def __init__(
        self,
        function_manager: Any,
        system_instruction: Optional[str] = None,
        scenario_context: str = "",
        config: Optional[LLMConfig] = None,
    ) -> None:
        self._llm_config = config if isinstance(config, LLMConfig) else LLMConfig.from_env()
        adk_model = create_local_adk_model(self._llm_config)
        self.function_manager = function_manager
        self.scenario_context = scenario_context

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
            if scenario_context:
                system_instruction += f"\n\n## 业务场景背景\n{scenario_context}"
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

        # Fallback client used when the backend does not support tool_choice="auto"
        # (e.g. vLLM started without --enable-auto-tool-choice).
        self._llm_client = AdkLLMClient(config=self._llm_config)
        # True  → try ADK native function calling first
        # False → permanently use JSON-prompt fallback (set after first tool_choice error)
        self._use_native_tools: bool = True
        # Cached fallback system prompt (built lazily on first use)
        self._fallback_system_prompt: Optional[str] = None

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
        # 业务场景背景（可选，注入到系统指令中让 LLM 了解对话场景）
        scenario_context = kwargs.pop("scenario_context", "")
        # 若调用方未显式传入 scenario_context，且也未传入 system_instruction，
        # 则使用场景配置自带的 system_prompt 作为背景，确保机器人身份与场景匹配。
        if (
            not scenario_context
            and "system_instruction" not in kwargs
            and hasattr(scenario_config, "system_prompt")
            and scenario_config.system_prompt
        ):
            scenario_context = scenario_config.system_prompt
        # 外部 DomainSpec（来自 --schema 参数），FnCTOD 不再内置场景 Schema
        domain_spec = kwargs.pop("domain_spec", None)
        fm = FunctionManager()
        if domain_spec is not None:
            fm.add_domain(domain_spec)
            logger.info(f"FnCTODTracker: 使用外部 DomainSpec '{domain_spec.name}'")
        else:
            logger.warning(
                f"FnCTODTracker: 场景 '{getattr(scenario_config, 'name', '')}' 未传入 domain_spec，"
                "使用空 FunctionManager（追踪器将无法提取槽位）。"
                "请通过 --schema 参数传入 *_fnctod_domain.json 文件。"
            )
        if config is not None:
            kwargs["config"] = config
        if scenario_context:
            kwargs["scenario_context"] = scenario_context
        return cls(function_manager=fm, **kwargs)

    async def _get_or_create_session(self) -> str:
        if self._session_id is None:
            session = await self._runner.session_service.create_session(
                app_name="contextmind_fnctod", user_id="default_user",
            )
            self._session_id = session.id
        return self._session_id

    def reset(self) -> None:
        """重置对话状态，开始新会话。

        注意：后端能力探测结果（``_use_native_tools``、``_fallback_system_prompt``）
        不在此处重置——若本次运行已确认后端不支持原生函数调用，下一个会话将
        直接使用 JSON 备用方案，避免在批量处理时每条会话首轮都触发
        ``tool_choice`` 错误警告。
        """
        self._current_state = {}
        self._dialogue_history = []
        self.turn_count = 0
        self._session_id = None
        self.last_turn_updates = {}

    def _build_fallback_system_prompt(self) -> str:
        """构建无需原生函数调用的槽位提取系统提示词。

        当后端不支持 ``tool_choice="auto"``（如 vLLM 未启用 ``--enable-auto-tool-choice``）
        时使用。模型被要求以 ``<SLOTS>…</SLOTS>`` 标签输出 JSON 槽位，随后输出自然语言回复。
        """
        lines = [
            "你是一个任务型对话助手。分析对话内容，提取槽位信息并给出回复。",
            "",
            "# 业务域和参数定义",
        ]
        for domain in self.function_manager.get_all_domains():
            lines.append(f"\n## 域: {domain.name}")
            if domain.description:
                lines.append(domain.description)
            lines.append("参数:")
            for p in domain.parameters:
                mark = "（必填）" if p.required else "（可选）"
                enum_info = f"，可选值: {p.enum_values}" if p.enum_values else ""
                lines.append(f"  - {p.name}: {p.description}{mark}{enum_info}")
        lines += [
            "",
            "# 输出格式（严格遵守）",
            "先输出 <SLOTS> 标签包裹的 JSON（仅填入本轮对话中明确提及的槽位，未提及的省略）：",
            "<SLOTS>",
            '{"槽位名": "槽位值"}',
            "</SLOTS>",
            "然后立即输出自然语言回复，不要输出任何其他内容。",
            "若本轮无槽位更新，输出 <SLOTS>{}</SLOTS> 后直接给出回复。",
        ]
        if self.scenario_context:
            lines += ["", "# 业务场景背景", self.scenario_context]
        return "\n".join(lines)

    async def _process_turn_fallback(
        self, effective_user_text: str
    ) -> Tuple[str, Dict[str, Any]]:
        """用结构化 JSON 提示词提取槽位并生成回复（不依赖原生函数调用）。

        当后端不支持 ``tool_choice="auto"`` 时由 :meth:`process_turn` 调用。
        模型输出格式为 ``<SLOTS>{...}</SLOTS>`` + 自然语言回复。

        Returns:
            ``(response_text, turn_updates)`` 元组。
        """
        if self._fallback_system_prompt is None:
            self._fallback_system_prompt = self._build_fallback_system_prompt()

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self._fallback_system_prompt}
        ]
        messages.extend(self._dialogue_history)
        messages.append({"role": "user", "content": effective_user_text})

        raw = await self._llm_client.chat_async(messages)

        # 解析 <SLOTS>…</SLOTS> 块中的 JSON
        turn_updates: Dict[str, Any] = {}
        slots_match = re.search(r"<SLOTS>\s*(.*?)\s*</SLOTS>", raw, re.DOTALL)
        response_text = raw
        if slots_match:
            try:
                slots = json.loads(slots_match.group(1))
                if isinstance(slots, dict):
                    turn_updates = {k: v for k, v in slots.items() if v not in (None, "", [])}
            except json.JSONDecodeError:
                logger.warning(
                    f"[turn {self.turn_count}] fallback 模式 JSON 解析失败: "
                    f"{slots_match.group(1)!r}"
                )
            # 去掉 <SLOTS>…</SLOTS> 块，剩余部分为自然语言回复
            response_text = raw[slots_match.end():].strip()

        logger.debug(
            f"[turn {self.turn_count}] fallback 模式 槽位: {turn_updates}, "
            f"回复: {response_text[:80]}"
        )
        return response_text, turn_updates

    async def process_turn(
        self,
        user_utterance: str,
        agent_utterance: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """处理单轮用户输入，提取槽位并生成回复。

        优先使用 ADK 原生 Function Calling；若后端返回
        ``tool_choice="auto"`` 不支持的错误（如 vLLM 未启用
        ``--enable-auto-tool-choice``），则自动切换为基于结构化 JSON
        提示词的备用方案，并对后续所有轮次保持该模式。

        Args:
            user_utterance:  本轮用户话语。
            agent_utterance: 本轮用户话语之前坐席/机器人说的内容（可选）。
                             外呼场景中每轮对话是"坐席先说 → 用户回应"的形式，
                             传入 ``agent_utterance`` 可让 LLM 理解用户话语所针对的上下文，
                             避免 LLM 在缺乏上下文时生成与业务无关的回复。

        Returns:
            包含以下键的字典:
                - ``response``  : LLM 生成的自然语言回复文本
                - ``state``     : 当前累积的对话状态（所有轮次槽位合并）
                - ``updates``   : 本轮新增或更新的槽位条目
        """
        self.turn_count += 1

        # 若本轮有坐席先说的内容，将其与用户话语合并为完整对话对，
        # 使 LLM 能理解用户回复的上下文（外呼场景：坐席先说→用户回应）。
        if agent_utterance:
            effective_user_text = f"坐席: {agent_utterance}\n用户: {user_utterance}"
        else:
            effective_user_text = user_utterance

        turn_updates: Dict[str, Any] = {}
        response_text = ""

        if self._use_native_tools:
            session_id = await self._get_or_create_session()
            content = genai_types.Content(
                role="user",
                parts=[genai_types.Part(text=effective_user_text)],
            )
            final_text = ""
            try:
                async for event in self._runner.run_async(
                    user_id="default_user",
                    session_id=session_id,
                    new_message=content,
                ):
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if hasattr(part, "function_call") and part.function_call:
                                fc = part.function_call
                                filtered = {
                                    k: v
                                    for k, v in (fc.args or {}).items()
                                    if v not in (None, "", [])
                                }
                                turn_updates.update(filtered)
                                logger.debug(
                                    f"[turn {self.turn_count}] function call "
                                    f"'{fc.name}': {filtered}"
                                )
                            if (
                                event.is_final_response()
                                and hasattr(part, "text")
                                and part.text
                            ):
                                if not getattr(part, "thought", False):
                                    final_text += part.text
                response_text = final_text.strip()
            except Exception as exc:
                exc_str = str(exc)
                if "tool choice" in exc_str.lower() or "tool_choice" in exc_str.lower():
                    # 后端不支持 tool_choice="auto"，永久切换到 JSON 提示词备用方案
                    logger.warning(
                        f"[turn {self.turn_count}] 原生函数调用不支持 "
                        f"(tool_choice error)，切换到 JSON 提示词备用模式: {exc}"
                    )
                    self._use_native_tools = False
                    response_text, turn_updates = await self._process_turn_fallback(
                        effective_user_text
                    )
                else:
                    raise
        else:
            response_text, turn_updates = await self._process_turn_fallback(
                effective_user_text
            )

        self._current_state.update(turn_updates)
        self.last_turn_updates = turn_updates
        self._dialogue_history.append({"role": "user", "content": effective_user_text})
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
