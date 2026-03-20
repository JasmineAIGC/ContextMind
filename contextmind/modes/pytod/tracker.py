"""
PyTOD Tracker — AdkPyTODTracker 实现（AP → EE → DM 三步流程）

严格遵循论文 "Task-Oriented Dialogue as Dataflow Synthesis"，
同时以 AdkLLMClient 作为统一 LLM 后端：

    Step 1  Action Parser (AP)：AdkLLMClient 根据对话历史 + Schema 生成 Python-like 程序
    Step 2  Execution Engine (EE)：ExecutionEngine 安全解析并执行程序
    Step 3  Dialogue Manager (DM)：AdkLLMClient 根据执行结果生成自然语言回复

与早前 ADK 原生 Function Calling 版本的区别：
- 不使用 LlmAgent / InMemoryRunner / FunctionTool
- 每轮有显式程序文本（program_text），可解释性强
- Schema 通过 PyTODPromptBuilder 注入 AP prompt，严格约束意图和槽位

使用示例::

    from contextmind.modes.pytod import AdkPyTODTracker, ExecutionEngine
    from contextmind.modes.pytod.registry import SCENARIO_API_REGISTRY
    from contextmind.infra.llm_client import AdkLLMClient

    llm = AdkLLMClient()
    engine = ExecutionEngine()
    SCENARIO_API_REGISTRY["callcenter"](engine)
    tracker = AdkPyTODTracker(llm_client=llm, engine=engine)
    result = await tracker.process_turn("查询我的账户余额")
    print(result["program_text"])  # x1 query_account()
    print(result["response"])      # 您的可用额度为…

    # 或使用工厂方法
    from contextmind.scenarios import get_anyihua_outbound_scenario
    config = get_anyihua_outbound_scenario()
    tracker = AdkPyTODTracker.from_scenario(llm, config)
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

from contextmind.infra.logger import get_logger
from contextmind.modes.pytod.execution_engine import ExecutionEngine, ProgramExecutionResult
from contextmind.modes.pytod.prompts import ConversationTurn, PyTODPromptBuilder
from contextmind.modes.pytod.registry import SCENARIO_API_REGISTRY, get_scenario_key
from contextmind.modes.pytod.schemas import ServiceSchema

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

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
# AdkPyTODTracker — 三步流程（AP → EE → DM），AdkLLMClient 作为 LLM 后端
# ---------------------------------------------------------------------------

class AdkPyTODTracker:
    """基于 AdkLLMClient 的 PyTOD 三步流程追踪器。

    实现论文 "Task-Oriented Dialogue as Dataflow Synthesis" 中的三步流程：
    - Step 1 AP（动作解析器）：LLM 根据对话历史和 Schema 生成 Python-like 程序
    - Step 2 EE（执行引擎）：ExecutionEngine 安全解析并执行程序，填充变量值
    - Step 3 DM（对话管理器）：LLM 根据执行结果生成自然语言回复

    LLM 后端统一使用 AdkLLMClient（或任何实现 ``chat_async()`` 的客户端），
    不依赖 ADK 原生 Function Calling（LlmAgent / InMemoryRunner / FunctionTool）。

    参数
    ----
    llm_client : Any
        实现 ``chat_async(messages: List[dict]) -> str`` 的 LLM 客户端
        （如 ``AdkLLMClient``）。
    engine : ExecutionEngine
        已注册 API 函数的执行引擎。
    schema : ServiceSchema | None
        服务 Schema，约束 AP 阶段可生成的意图和槽位。
        为 None 时使用空 Schema（开放域模式）。
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
            api_signatures=engine.to_prompt_text(),   # 实际函数签名，AP 选函数时的权威来源
            max_history_turns=max_history_turns,
        )
        self._history: List[ConversationTurn] = []
        self.current_state: Dict[str, Any] = {}
        self.api_call_log: List[Dict[str, Any]] = []
        self.turn_count: int = 0
        self.last_program_text: str = ""   # 最近一轮 AP 生成的程序（供 web_demo 展示）
        # 各步骤耗时（web_demo 的 timing_breakdown 会合并此字典）
        self.step_timings: Dict[str, float] = {}

        logger.info(
            f"AdkPyTODTracker 初始化完成 (schema={self.schema.service_name}, "
            f"APIs: {engine.list_functions()})"
        )

    @classmethod
    def from_scenario(
        cls,
        llm_client: Any,
        scenario_config: Any,
        config: Optional[Any] = None,  # noqa: ARG003 — 保持与旧接口兼容
        **kwargs: Any,
    ) -> "AdkPyTODTracker":
        """从场景配置创建 AdkPyTODTracker。

        自动注册场景 API、加载 ServiceSchema 并填充场景描述。

        Args:
            llm_client:      LLM 客户端（如 ``AdkLLMClient``）。
            scenario_config: ScenarioConfig 实例。
            config:          保留参数，已忽略（兼容旧接口）。
            **kwargs:        传递给 ``__init__`` 的额外参数（如 ``max_history_turns``）。
        """
        # 过滤历史遗留的不兼容参数
        kwargs.pop("prompt_builder", None)
        kwargs.pop("app_name", None)
        kwargs.pop("user_id", None)

        engine = ExecutionEngine()
        scenario_name = getattr(scenario_config, "name", "")
        key = get_scenario_key(scenario_name)
        if key:
            SCENARIO_API_REGISTRY[key](engine)
            logger.info(f"已为场景 '{scenario_name}' 注册 API: {engine.list_functions()}")
        else:
            logger.warning(f"场景 '{scenario_name}' 无预置 API，运行开放域模式")

        # 自动加载场景 schema，注入 AP prompt 实现意图约束
        schema = kwargs.pop("schema", None) or _load_scenario_schema(key)

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
            包含以下键的字典：

            - ``response`` (str): DM 生成的自然语言回复。
            - ``program_text`` (str): AP 生成的 PyTOD 程序文本。
            - ``state`` (dict): 本轮后的累积状态（变量值快照）。
            - ``execution`` (ProgramExecutionResult): EE 执行结果。

            ``step_timings`` 属性同步更新为各步骤耗时（供 web_demo 使用）。
        """
        self.turn_count += 1
        logger.info(f"AdkPyTODTracker 第 {self.turn_count} 轮 | AP→EE→DM | 用户: {user_utterance}")
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
        self.last_program_text = program_text   # 记录供 web_demo 展示
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
        self.last_program_text = ""
        self.step_timings = {}
        logger.info("AdkPyTODTracker 对话状态已重置")


# ---------------------------------------------------------------------------
# 向后兼容别名：保留 adk_tools_from_engine 以防外部代码引用
# ---------------------------------------------------------------------------

def adk_tools_from_engine(engine: Any) -> List[Any]:
    """已废弃：此版本不再使用 ADK FunctionTool。

    保留此函数仅为向后兼容，返回空列表。
    若需要 ADK 原生函数调用，请直接使用 google-adk LlmAgent。
    """
    logger.warning(
        "adk_tools_from_engine() 已废弃：AdkPyTODTracker 现使用 AP→EE→DM 三步流程，"
        "不再依赖 ADK FunctionTool。"
    )
    return []
