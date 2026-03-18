"""
ADK Bridge — 将 Google ADK (Agent Development Kit) 与 PyTOD 模式集成

提供三种集成方式，可按需选用：

1. **adk_tools_from_engine(engine)**
   将 ``ExecutionEngine`` 中已注册的 Python 函数自动转换为 ADK ``FunctionTool``
   列表，以便直接传给 ``LlmAgent(tools=...)``，利用本地 LLM 原生函数调用能力。

2. **AdkLlmClientBridge(agent)**
   将 ADK ``LlmAgent`` + ``InMemoryRunner`` 包装成与 ``SimpleLLMClient`` 兼容的
   ``chat_async(messages)`` 接口，无需修改 ``PyTODTracker`` 即可切换底层模型。

3. **AdkPyTODAgent(engine)**
   完整的 ADK 原生 PyTOD 代理，不使用自定义程序解析器，而是让 ADK 的原生函数调用
   机制直接调用 ExecutionEngine 中的 API，并由本地 LLM 生成最终自然语言回复。
   与 ``PyTODTracker`` 接口完全一致。

集成优势
--------
- **无需自定义程序解析**：LLM 原生工具调用替代手写 PyTOD 程序解析器
- **自动生成工具描述**：ADK 从函数签名和 docstring 自动提取参数 schema
- **统一会话管理**：ADK InMemoryRunner 管理多轮上下文，无需手动拼接 history
- **开箱即用的请求管理**：ADK Runner 内置重试、限速等机制
- **本地部署**：通过 LiteLlm 接入 .env 配置的 vLLM/OpenAI 兼容端点
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from .execution_engine import ExecutionEngine
    from contextmind.infra.llm_client import LLMConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1. adk_tools_from_engine — ExecutionEngine → FunctionTool 列表
# ---------------------------------------------------------------------------


def adk_tools_from_engine(engine: "ExecutionEngine") -> List[Any]:
    """将 ``ExecutionEngine`` 中已注册的函数包装为 ADK ``FunctionTool`` 列表。

    ADK 会自动从函数签名和 docstring 生成参数描述（JSON Schema），
    以便本地 LLM 理解各 API 的用途和参数格式。

    参数:
        engine: 已注册了 API 函数的 ``ExecutionEngine`` 实例

    返回:
        可直接传给 ``LlmAgent(tools=...)`` 的 ``FunctionTool`` 列表

    示例::

        from contextmind.modes.pytod import ExecutionEngine
        from contextmind.modes.pytod.adk_bridge import adk_tools_from_engine
        from contextmind.infra.llm_client import create_local_adk_model
        from google.adk.agents import LlmAgent

        engine = ExecutionEngine()

        @engine.register
        def query_account(customer_id: str = None):
            \"\"\"查询客户账户信息。\"\"\"
            return {"balance": 5000, "status": "正常"}

        tools = adk_tools_from_engine(engine)
        agent = LlmAgent(model=create_local_adk_model(), tools=tools, ...)
    """
    try:
        from google.adk.tools import FunctionTool  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "google-adk 未安装，无法创建 ADK 工具。\n"
            "请运行: pip install google-adk"
        ) from exc

    wrapped_tools: List[Any] = []
    for name, func in engine.registry.items():
        adk_tool = FunctionTool(func=func)
        wrapped_tools.append(adk_tool)
        logger.debug(f"已将 ExecutionEngine 函数 '{name}' 包装为 ADK FunctionTool")

    logger.info(
        f"adk_tools_from_engine: 共包装 {len(wrapped_tools)} 个工具: "
        f"{list(engine.registry.keys())}"
    )
    return wrapped_tools


# ---------------------------------------------------------------------------
# 2. AdkLlmClientBridge — LlmAgent → SimpleLLMClient 兼容接口
# ---------------------------------------------------------------------------


class AdkLlmClientBridge:
    """将 ADK ``LlmAgent`` 包装成 ``SimpleLLMClient`` 兼容的接口。

    现有 ``PyTODTracker`` 无需任何修改，只需将构造函数的 ``llm_client``
    参数替换为本类的实例，即可通过 ADK 驱动的本地 LLM 进行对话。

    适用场景
    --------
    - 希望保留 PyTOD 三步流程（Action Parser → Execution Engine → Dialogue Manager）
    - 仅需替换 LLM 客户端，不修改追踪器逻辑
    - 需要有状态会话（跨多轮复用同一 ADK session）

    参数:
        agent:    ``LlmAgent`` 实例（需已配置 model）
        app_name: ADK 应用名称（默认 "pytod_bridge"）
        user_id:  ADK 用户标识符（默认 "default_user"）

    示例::

        from contextmind.modes.pytod.adk_bridge import AdkLlmClientBridge
        from contextmind.infra.llm_client import create_local_adk_model
        from google.adk.agents import LlmAgent

        llm_agent = LlmAgent(model=create_local_adk_model(), name="bridge_agent",
                             instruction="请用中文简洁回答。")
        bridge = AdkLlmClientBridge(agent=llm_agent)
    """

    #: sync chat() 的最大等待秒数（可通过子类覆盖）
    SYNC_CHAT_TIMEOUT: float = 120.0

    def __init__(
        self,
        agent: Any,
        app_name: str = "pytod_bridge",
        user_id: str = "default_user",
    ) -> None:
        try:
            from google.adk.runners import InMemoryRunner  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "google-adk 未安装，无法创建 AdkLlmClientBridge。\n"
                "请运行: pip install google-adk"
            ) from exc

        self._agent = agent
        self._runner = InMemoryRunner(agent=agent, app_name=app_name)
        self._user_id = user_id
        self._session_id: Optional[str] = None

    # ------------------------------------------------------------------ #
    # 会话管理
    # ------------------------------------------------------------------ #

    async def _get_or_create_session(self) -> str:
        """懒加载创建 ADK session；同一对话生命周期内复用同一 session。"""
        if self._session_id is None:
            session = await self._runner.session_service.create_session(
                app_name=self._runner.app_name,
                user_id=self._user_id,
            )
            self._session_id = session.id
            logger.debug(f"AdkLlmClientBridge: ADK session 已创建 (id={self._session_id})")
        return self._session_id

    def reset_session(self) -> None:
        """重置 ADK session；通常在 PyTODTracker.reset() 后调用。"""
        self._session_id = None
        logger.debug("AdkLlmClientBridge: ADK session 已重置")

    # ------------------------------------------------------------------ #
    # SimpleLLMClient 兼容接口
    # ------------------------------------------------------------------ #

    async def chat_async(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,  # noqa: ARG002 – ignored, ADK 由 agent 配置
    ) -> str:
        """将 OpenAI 消息格式转换为 ADK Content，运行代理并返回文本回复。

        参数:
            messages:    OpenAI 兼容的消息列表 [{"role": ..., "content": ...}]
            temperature: 当前版本忽略此参数（由 LlmAgent 的 generate_content_config
                         控制），保留此参数是为了与 SimpleLLMClient 接口兼容。

        返回:
            代理生成的文本回复
        """
        try:
            from google.genai import types as genai_types  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "google-genai 未安装。请运行: pip install google-adk"
            ) from exc

        user_text = _messages_to_text(messages)
        new_message = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=user_text)],
        )

        session_id = await self._get_or_create_session()
        final_text = ""

        async for event in self._runner.run_async(
            user_id=self._user_id,
            session_id=session_id,
            new_message=new_message,
        ):
            if event.is_final_response() and event.content:
                for part in event.content.parts or []:
                    if hasattr(part, "text") and part.text:
                        final_text += part.text

        return final_text.strip()

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
    ) -> str:
        """同步版 chat，内部通过事件循环调用 chat_async。"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            # 已在 async 上下文中（如 Jupyter / pytest-asyncio），
            # 在独立线程中运行新事件循环以避免嵌套循环限制
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    asyncio.run,
                    self.chat_async(messages=messages, temperature=temperature),
                )
                return future.result(timeout=self.SYNC_CHAT_TIMEOUT)
        else:
            return asyncio.run(
                self.chat_async(messages=messages, temperature=temperature)
            )


# ---------------------------------------------------------------------------
# 3. AdkPyTODAgent — 完整的 ADK 原生 PyTOD 代理
# ---------------------------------------------------------------------------


class AdkPyTODAgent:
    """ADK 原生 PyTOD 代理，与 ``PyTODTracker`` 接口完全兼容。

    使用 ADK 原生函数调用（function calling / tool use）代替 PyTOD 自定义
    程序解析器，让本地 LLM 直接决定调用哪个 API、传入什么参数，并最终生成
    自然语言回复。整个三步流程（Action Parser → Execution Engine → Dialogue Manager）
    统一由 ADK ``LlmAgent`` 内部完成。

    适用场景
    --------
    - 希望利用本地 LLM 的原生 Function Calling 能力
    - 不想维护自定义 PyTOD 程序解析逻辑
    - 需要 ADK 内置的多轮会话管理、重试机制

    参数:
        engine:           ``ExecutionEngine`` 实例（其注册函数将转为 ADK 工具）
        config:           本地 LLM 配置；若为 None 则从 ``.env`` 自动加载
        scenario_context: 注入 system instruction 的业务场景描述
        max_history_turns: 最大保留对话轮数（由 ADK session 自动管理）
        app_name:         ADK 应用名称
        user_id:          ADK 用户标识符

    示例::

        from contextmind.modes.pytod import ExecutionEngine
        from contextmind.modes.pytod.registry import SCENARIO_API_REGISTRY
        from contextmind.modes.pytod.adk_bridge import AdkPyTODAgent

        engine = ExecutionEngine()
        SCENARIO_API_REGISTRY["callcenter"](engine)

        agent = AdkPyTODAgent(
            engine=engine,
            scenario_context="这是一个电商客服场景，需处理退款和物流查询。",
        )

        result = asyncio.run(agent.process_turn("我的订单什么时候发货？"))
        print(result["response"])
    """

    def __init__(
        self,
        engine: "ExecutionEngine",
        config: Optional["LLMConfig"] = None,
        scenario_context: str = "",
        max_history_turns: int = 10,
        app_name: str = "pytod_adk",
        user_id: str = "default_user",
    ) -> None:
        try:
            from google.adk.agents import LlmAgent  # type: ignore[import]
            from google.adk.runners import InMemoryRunner  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "google-adk 未安装，无法创建 AdkPyTODAgent。\n"
                "请运行: pip install google-adk litellm"
            ) from exc

        from contextmind.infra.llm_client import LLMConfig, create_local_adk_model
        self._llm_config = config if isinstance(config, LLMConfig) else LLMConfig.from_env()
        adk_model = create_local_adk_model(self._llm_config)

        self.engine = engine
        self.scenario_context = scenario_context
        self.max_history_turns = max_history_turns
        self._user_id = user_id

        tools = adk_tools_from_engine(engine)
        instruction = _build_agent_instruction(scenario_context)

        self._adk_agent = LlmAgent(
            name="pytod_adk_agent",
            model=adk_model,
            description="PyTOD 任务型对话代理（ADK 原生函数调用版）",
            instruction=instruction,
            tools=tools,
        )
        self._runner = InMemoryRunner(agent=self._adk_agent, app_name=app_name)
        self._session_id: Optional[str] = None

        # 兼容 PyTODTracker 的公开属性
        self.current_state: Dict[str, Any] = {}
        self.turn_count: int = 0

        logger.info(
            f"AdkPyTODAgent 初始化完成 (model={self._llm_config.model}, "
            f"工具数={len(tools)}: {list(engine.registry.keys())})"
        )

    # ------------------------------------------------------------------ #
    # PyTODTracker 兼容接口
    # ------------------------------------------------------------------ #

    async def process_turn(
        self,
        user_utterance: str,
        system_utterance: str = "",  # noqa: ARG002 – kept for interface parity
    ) -> Dict[str, Any]:
        """处理单轮对话（与 ``PyTODTracker.process_turn`` 接口完全一致）。

        ADK 原生流程：

        1. 用户输入传入 ``LlmAgent``
        2. 本地 LLM 决定调用哪个工具（等同于 Action Parser）
        3. ADK 自动执行工具并将结果回传给模型（等同于 Execution Engine）
        4. 本地 LLM 生成最终自然语言回复（等同于 Dialogue Manager）

        返回与 ``PyTODTracker.process_turn`` 相同结构的字典::

            {
                "response":     str,   # 面向用户的自然语言回复
                "program_text": str,   # 工具调用文本（格式：func_name({args})）
                "state":        dict,  # 本轮工具返回的结果（累积）
                "execution":    None,  # ADK 原生模式无 ProgramExecutionResult
            }
        """
        try:
            from google.genai import types as genai_types  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "google-genai 未安装。请运行: pip install google-adk"
            ) from exc

        self.turn_count += 1
        logger.info(f"\n{'='*50}")
        logger.info(f"AdkPyTODAgent 第 {self.turn_count} 轮对话")
        logger.info(f"用户: {user_utterance}")

        session_id = await self._get_or_create_session()

        new_message = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=user_utterance)],
        )

        final_text = ""
        tool_call_parts: List[str] = []

        async for event in self._runner.run_async(
            user_id=self._user_id,
            session_id=session_id,
            new_message=new_message,
        ):
            # 记录工具调用（供 program_text 兼容字段使用）
            for fc in event.get_function_calls() or []:
                call_repr = f"{fc.name}({fc.args})"
                tool_call_parts.append(call_repr)
                logger.info(f"[ADK Tool Call] {call_repr}")

            # 将工具结果合并到累积状态
            for fr in event.get_function_responses() or []:
                if isinstance(fr.response, dict):
                    var_key = f"x{self.turn_count}_{fr.name}"
                    self.current_state[var_key] = fr.response
                logger.info(
                    f"[ADK Tool Response] {fr.name}: "
                    f"{str(fr.response)[:120]}"
                )

            # 提取最终文本回复
            if event.is_final_response() and event.content:
                for part in event.content.parts or []:
                    if hasattr(part, "text") and part.text:
                        final_text += part.text

        response = final_text.strip()
        program_text = "\n".join(tool_call_parts) if tool_call_parts else "NONE()"

        logger.info(f"[ADK Agent] 工具调用摘要: {program_text[:200]}")
        logger.info(f"[ADK Agent] 回复: {response[:80]}...")

        return {
            "response": response,
            "program_text": program_text,
            "state": dict(self.current_state),
            "execution": None,  # ADK 原生模式下无 ProgramExecutionResult
        }

    def get_current_state(self) -> Dict[str, Any]:
        """返回当前累积对话状态（工具执行结果）。"""
        return dict(self.current_state)

    def reset(self) -> None:
        """重置对话状态，创建新的 ADK session。"""
        self._session_id = None
        self.current_state = {}
        self.turn_count = 0
        logger.info("AdkPyTODAgent 对话状态已重置")

    # ------------------------------------------------------------------ #
    # 内部方法
    # ------------------------------------------------------------------ #

    async def _get_or_create_session(self) -> str:
        """懒加载创建 ADK session；同一对话生命周期内复用同一 session。"""
        if self._session_id is None:
            session = await self._runner.session_service.create_session(
                app_name=self._runner.app_name,
                user_id=self._user_id,
            )
            self._session_id = session.id
            logger.debug(f"AdkPyTODAgent: ADK session 已创建 (id={self._session_id})")
        return self._session_id


# ---------------------------------------------------------------------------
# 内部工具函数
# ---------------------------------------------------------------------------


def _messages_to_text(messages: List[Dict[str, str]]) -> str:
    """将 OpenAI 格式的 messages 列表合并为单个文本字符串。

    供 ``AdkLlmClientBridge`` 将多条消息转换为 ADK Content 时使用。
    系统提示添加 "[系统指令]" 前缀，用户/助手消息按角色标注后依次拼接。
    """
    parts: List[str] = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "system":
            parts.append(f"[系统指令]\n{content}")
        elif role == "user":
            parts.append(f"[用户]\n{content}")
        elif role == "assistant":
            parts.append(f"[助手]\n{content}")
    return "\n\n".join(parts)


def _build_agent_instruction(scenario_context: str) -> str:
    """构建 ADK Agent 的 instruction（系统指令）。

    参数:
        scenario_context: 业务场景描述（可为空）

    返回:
        完整的系统指令文本
    """
    base = (
        "你是一个任务型对话助手。当用户提出需求时，优先调用合适的工具（函数）来完成任务，"
        "然后根据工具返回结果用自然语言给出友好、简洁的回复。\n\n"
        "规则：\n"
        "1. 尽量调用工具完成任务，而非猜测数据\n"
        "2. 工具返回 hint 字段时，向用户说明需要提供哪些信息\n"
        "3. 工具返回 error 字段时，向用户说明情况并请求补充信息\n"
        "4. 回复语言：中文\n"
    )
    if scenario_context:
        base += f"\n业务场景说明：\n{scenario_context}\n"
    return base
