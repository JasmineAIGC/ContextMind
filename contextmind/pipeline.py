"""
ContextPipeline — 通用上下文工程流水线

将知识库构建（Phase 1）和上下文提取执行（Phase 2）统一为一个高层接口。

上下文工程两步框架
------------------
1. **建立知识库**（Phase 1）：针对任意数据集，通过 LLM 自动发现槽位和意图，
   合成标准 SGD 格式 ``schema.json``。
2. **执行**（Phase 2）：基于知识库，在对话中提取有效的上下文，提升对话质量。

``ContextPipeline`` 将两步整合为一个简洁 API，用户无需了解底层算法细节。

典型用法
--------

**端到端：从原始对话数据到上下文提取**::

    import asyncio
    from contextmind.pipeline import ContextPipeline
    from contextmind.infra.llm_client import AdkLLMClient

    pipeline = ContextPipeline(llm_client=AdkLLMClient())

    # Phase 1: 从原始对话构建知识库
    pipeline.build_kb(
        dialogues=my_dialogues,
        scene_name="银行贷款外呼",
        scene_description="银行客服主动致电老客户推介个人贷款产品",
    )

    # Phase 2: 处理对话轮次，提取上下文
    async def chat():
        result = await pipeline.process_turn("我想查询我的贷款额度")
        print(result["response"])      # 生成的回复
        print(result["context"])       # 提取的上下文（槽位、意图等）
        print(result["program_text"])  # PyTOD 程序（可选，仅 pytod 模式）

    asyncio.run(chat())

**从已保存的 schema.json 加载**::

    pipeline = ContextPipeline(llm_client=AdkLLMClient())
    pipeline.load_kb("output/schema.json")

    result = await pipeline.process_turn("我是李明，想了解贷款利率")

**注册自定义 API 函数**::

    pipeline = ContextPipeline(llm_client=AdkLLMClient())
    pipeline.load_kb("output/schema.json")

    @pipeline.register_api("query_loan_info")
    def query_loan_info(customer_name: str) -> dict:
        return {"credit_limit": 50000, "interest_rate": 0.12}

    result = await pipeline.process_turn("查询一下我的额度")

执行模式
--------
- ``"pytod"``（默认）：PyTOD 三步流程（AP→EE→DM），适用于任务型对话。
  返回 ``program_text`` 和 ``context`` 字段。
- ``"dst"``：对话状态追踪，纯槽位提取，无 API 调用。
  适用于信息提取场景。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from contextmind.infra.llm_client import AdkLLMClient, LLMConfig
from contextmind.infra.logger import get_logger
from contextmind.knowledge.builder import KnowledgeBaseBuilder

logger = get_logger(__name__)


class ContextPipeline:
    """
    通用上下文工程流水线。

    将知识库构建（Phase 1）和对话上下文提取（Phase 2）统一为一个简洁接口。

    参数
    ----
    llm_client:
        LLM 客户端实例（如 ``AdkLLMClient``）；为 None 时从 ``.env`` 自动加载。
    mode:
        执行模式：

        - ``"pytod"``（默认）：PyTOD AP→EE→DM 三步流程，适合任务型对话。
        - ``"dst"``：对话状态追踪，纯槽位提取。

    scene_name:
        业务场景名称（如 ``"银行贷款外呼"``）；用于 KB 构建和 prompt 注入。
    scene_description:
        场景简短描述（一句话）；为空时使用 ``scene_name``。
    discovery_sample:
        Phase 1 发现阶段最多使用的对话条数（默认 20）。
    max_history_turns:
        Phase 2 执行时保留的最近历史轮次数（默认 10）。

    属性
    ----
    schema:
        当前加载的 :class:`~contextmind.modes.pytod.schemas.ServiceSchema`；
        可通过 :meth:`load_kb` 或 :meth:`build_kb` 设置。
    tracker:
        当前使用的对话追踪器（``AdkPyTODTracker`` 或 ``DialogueStateTracker``）；
        调用 :meth:`build_kb` / :meth:`load_kb` 后自动初始化。
    """

    def __init__(
        self,
        llm_client: Optional[AdkLLMClient] = None,
        mode: str = "pytod",
        scene_name: str = "对话场景",
        scene_description: str = "",
        discovery_sample: int = 20,
        max_history_turns: int = 10,
    ) -> None:
        self._llm_client = llm_client
        self.mode = mode
        self.scene_name = scene_name
        self.scene_description = scene_description or scene_name
        self.discovery_sample = discovery_sample
        self.max_history_turns = max_history_turns

        self.schema: Optional[Any] = None
        self.tracker: Optional[Any] = None
        self._engine: Optional[Any] = None
        self._kb_builder: Optional[KnowledgeBaseBuilder] = None

        # 用于记录最近一次 build_kb() 的统计摘要
        self.last_build_summary: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Phase 1: 知识库构建
    # ------------------------------------------------------------------

    def build_kb(
        self,
        dialogues: List[Any],
        scene_name: Optional[str] = None,
        scene_description: Optional[str] = None,
        save_path: Optional[Union[str, Path]] = None,
    ) -> Dict[str, Any]:
        """
        Phase 1：从原始对话数据构建知识库（SGD schema）。

        自动完成对话归一化、LLM 发现、LLM 合成三个子步骤，并将生成的
        ``ServiceSchema`` 设置到 :attr:`schema`，同时初始化 Phase 2 追踪器。

        参数
        ----
        dialogues:
            对话列表，支持四种输入格式（见 :mod:`contextmind.kb.normalizer`）。
        scene_name:
            覆盖实例初始化时的 ``scene_name``（可选）。
        scene_description:
            覆盖实例初始化时的 ``scene_description``（可选）。
        save_path:
            若指定，则将 schema.json 写入此路径（可选）。

        返回
        ----
        SGD 格式的 schema dict（与 :meth:`~contextmind.kb.KnowledgeBaseBuilder.build`
        返回值相同）。
        """
        if scene_name:
            self.scene_name = scene_name
        if scene_description:
            self.scene_description = scene_description

        logger.info(
            f"[ContextPipeline] Phase 1 开始：场景={self.scene_name!r}，"
            f"对话数={len(dialogues)}，模式={self.mode!r}"
        )

        builder = KnowledgeBaseBuilder(
            scene_name=self.scene_name,
            scene_description=self.scene_description,
            llm_client=self._get_llm(),
            discovery_sample=self.discovery_sample,
        )
        self._kb_builder = builder

        schema_dict = builder.build(dialogues)

        # Phase 1 → Phase 2 桥接
        self.schema = KnowledgeBaseBuilder.to_service_schema(schema_dict)

        self.last_build_summary = {
            "scene_name": self.scene_name,
            "n_dialogues": len(dialogues),
            "n_slots": len(schema_dict.get("slots", [])),
            "n_intents": len(schema_dict.get("intents", [])),
            "top_slots": builder.last_slot_counter.most_common(5),
            "top_intents": builder.last_intent_counter.most_common(5),
        }

        if save_path:
            builder.save(schema_dict, save_path)
            logger.info(f"[ContextPipeline] schema.json 已写入: {save_path}")

        # 初始化追踪器
        self._init_tracker()

        logger.info(
            f"[ContextPipeline] Phase 1 完成：{len(schema_dict.get('slots', []))} 个槽位，"
            f"{len(schema_dict.get('intents', []))} 个意图"
        )
        return schema_dict

    async def build_kb_async(
        self,
        dialogues: List[Any],
        scene_name: Optional[str] = None,
        scene_description: Optional[str] = None,
        save_path: Optional[Union[str, Path]] = None,
    ) -> Dict[str, Any]:
        """Phase 1 的异步版本（在线程池中运行，不阻塞事件循环）。

        参数与返回值同 :meth:`build_kb`。
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.build_kb(dialogues, scene_name, scene_description, save_path),
        )

    def load_kb(self, schema_path: Union[str, Path]) -> None:
        """
        Phase 1 → Phase 2 桥接：从磁盘加载已保存的 ``schema.json``。

        自动初始化 Phase 2 追踪器，可立即调用 :meth:`process_turn`。

        参数
        ----
        schema_path:
            由 :meth:`build_kb` 或
            :meth:`~contextmind.kb.KnowledgeBaseBuilder.save` 生成的
            ``schema.json`` 文件路径。
        """
        self.schema = KnowledgeBaseBuilder.load_schema(schema_path)
        self._init_tracker()
        logger.info(
            f"[ContextPipeline] 已加载 schema: {self.schema.service_name}，"
            f"槽位={len(self.schema.slots)}，意图={len(self.schema.intents)}"
        )

    def set_schema(self, schema: Any) -> None:
        """
        直接设置 ``ServiceSchema`` 实例（无需从文件加载）。

        适用于已有 :class:`~contextmind.modes.pytod.schemas.ServiceSchema` 对象的场景。

        参数
        ----
        schema:
            :class:`~contextmind.modes.pytod.schemas.ServiceSchema` 实例，
            或可通过 :func:`~contextmind.modes.pytod.schemas.load_schema_from_dict`
            转换的字典。
        """
        from contextmind.modes.pytod.schemas import ServiceSchema

        if isinstance(schema, dict):
            from contextmind.modes.pytod.schemas import load_schema_from_dict

            self.schema = load_schema_from_dict(schema)
        elif isinstance(schema, ServiceSchema):
            self.schema = schema
        else:
            raise TypeError(
                f"schema 必须是 ServiceSchema 实例或字典，得到: {type(schema)}"
            )
        self._init_tracker()

    # ------------------------------------------------------------------
    # Phase 2: 上下文提取执行
    # ------------------------------------------------------------------

    def register_api(self, name: Optional[str] = None) -> Callable:
        """
        注册业务 API 函数（装饰器）。

        注册后的函数在 Phase 2 执行时由 ExecutionEngine 调用，
        将业务数据注入对话上下文。

        参数
        ----
        name:
            API 函数名称；为 None 时使用被装饰函数的 ``__name__``。

        返回
        ----
        装饰器函数。

        示例
        ----
        ::

            @pipeline.register_api("query_account")
            def query_account(customer_name: str) -> dict:
                return {"credit_limit": 50000, "interest_rate": 0.12}
        """
        if self.mode != "pytod":
            raise RuntimeError(
                f"register_api() 仅在 mode='pytod' 时可用，当前 mode={self.mode!r}"
            )

        def decorator(fn: Callable) -> Callable:
            api_name = name or fn.__name__
            engine = self._get_engine()
            engine.register_as(api_name)(fn)
            logger.info(f"[ContextPipeline] 已注册 API: {api_name}")
            # 重新初始化追踪器以使新 API 生效
            if self.schema is not None:
                self._init_tracker()
            return fn

        return decorator

    async def process_turn(
        self,
        user_utterance: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Phase 2：处理单轮用户输入，提取有效上下文。

        在对话历史和知识库约束下，使用 LLM 提取本轮上下文信息（槽位、意图、
        状态等），并生成系统回复。

        参数
        ----
        user_utterance:
            用户本轮输入文本。
        **kwargs:
            传递给底层追踪器的额外参数。

        返回
        ----
        字典，至少包含以下键：

        ``"response"``
            系统生成的自然语言回复。
        ``"context"``
            本轮提取的结构化上下文（槽位值、意图等）。
        ``"cumulative_context"``
            截至本轮的累积上下文（全量状态）。

        PyTOD 模式额外返回：

        ``"program_text"``
            AP 生成的 PyTOD 程序。
        ``"execution"``
            ExecutionEngine 执行结果。

        异常
        ----
        RuntimeError
            若未通过 :meth:`build_kb` 或 :meth:`load_kb` 设置 schema，
            或 LLM 未配置。
        """
        if self.schema is None:
            raise RuntimeError(
                "尚未设置 schema，请先调用 build_kb() 或 load_kb()"
            )

        # 延迟初始化追踪器（当 llm_client 在 set_schema 时还不可用的情况）
        if self.tracker is None:
            self._init_tracker()

        if self.tracker is None:
            raise RuntimeError(
                "追踪器初始化失败，请确保 LLM 已配置（.env 中设置 LLM_API_KEY）"
            )

        raw = await self.tracker.process_turn(user_utterance, **kwargs)

        # 标准化返回格式，增加通用 context 字段
        result: Dict[str, Any] = dict(raw)
        result["context"] = raw.get("state", raw.get("turn_updates", {}))
        result["cumulative_context"] = self.tracker.get_current_state()
        return result

    def get_context(self) -> Dict[str, Any]:
        """
        返回截至当前的累积上下文（完整对话状态）。

        Returns:
            包含所有已提取槽位/字段的字典。若未初始化则返回空字典。
        """
        if self.tracker is None:
            return {}
        return self.tracker.get_current_state()

    def reset(self) -> None:
        """清空对话历史和累积状态，开始新会话（保留 schema 和 API 注册）。"""
        if self.tracker is not None:
            self.tracker.reset()
        logger.debug("[ContextPipeline] 对话状态已重置")

    # ------------------------------------------------------------------
    # 摘要 & 工具方法
    # ------------------------------------------------------------------

    def summary(self) -> str:
        """返回当前 pipeline 状态的可读摘要字符串。"""
        lines = [
            "=== ContextPipeline 状态摘要 ===",
            f"  模式:     {self.mode}",
            f"  场景:     {self.scene_name}",
        ]
        if self.schema is not None:
            lines += [
                f"  Schema:   {self.schema.service_name}",
                f"  槽位数:   {len(self.schema.slots)}",
                f"  意图数:   {len(self.schema.intents)}",
            ]
        else:
            lines.append("  Schema:   (未加载)")

        if self.tracker is not None:
            lines.append(f"  追踪器:   {type(self.tracker).__name__} (已初始化)")
            ctx = self.get_context()
            if ctx:
                lines.append(f"  当前状态: {ctx}")
        else:
            lines.append("  追踪器:   (未初始化)")

        if self.last_build_summary:
            top_slots = self.last_build_summary.get("top_slots", [])
            top_intents = self.last_build_summary.get("top_intents", [])
            if top_slots:
                lines.append(f"  Top 槽位: {[s for s, _ in top_slots]}")
            if top_intents:
                lines.append(f"  Top 意图: {[i for i, _ in top_intents]}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _get_llm(self) -> AdkLLMClient:
        """延迟初始化 LLM 客户端。"""
        if self._llm_client is None:
            try:
                self._llm_client = AdkLLMClient(config=LLMConfig.from_env())
            except Exception as exc:
                raise RuntimeError(
                    "LLM 客户端初始化失败，请在 .env 中配置 LLM_API_KEY / "
                    f"LLM_BASE_URL / LLM_MODEL。原始错误: {exc}"
                ) from exc
        return self._llm_client

    def _get_engine(self) -> Any:
        """延迟初始化 ExecutionEngine（仅 pytod 模式）。"""
        if self._engine is None:
            from contextmind.modes.pytod.execution_engine import ExecutionEngine

            self._engine = ExecutionEngine()
        return self._engine

    def _init_tracker(self) -> None:
        """根据 mode 和当前 schema 初始化对话追踪器。

        若 LLM 客户端尚未提供（``_llm_client is None``），则跳过初始化，
        等待 :meth:`process_turn` 时再延迟初始化。
        """
        if self.schema is None:
            return

        # 若 LLM 客户端还未提供，延迟到 process_turn() 时初始化
        if self._llm_client is None:
            return

        if self.mode == "pytod":
            from contextmind.modes.pytod.tracker import AdkPyTODTracker

            engine = self._get_engine()
            self.tracker = AdkPyTODTracker(
                llm_client=self._get_llm(),
                engine=engine,
                schema=self.schema,
                scenario_context=self.scene_description,
                max_history_turns=self.max_history_turns,
            )
            logger.debug(
                f"[ContextPipeline] PyTOD 追踪器已初始化: "
                f"schema={self.schema.service_name}"
            )

        elif self.mode == "dst":
            from contextmind.modes.dst.tracker import DialogueStateTracker
            from contextmind.modes.dst.prompts import PromptManager

            prompt_manager = PromptManager(
                domain=self.scene_name,
                enable_dynamic_slots=True,
            )
            # 将 schema 槽位注入 DST prompt 管理器
            if hasattr(prompt_manager, "slots"):
                slot_names = self.schema.get_slot_names()
                prompt_manager.slots = slot_names

            self.tracker = DialogueStateTracker(
                llm_client=self._get_llm(),
                prompt_manager=prompt_manager,
                domain=self.scene_name,
                max_history_turns=self.max_history_turns,
            )
            logger.debug(
                f"[ContextPipeline] DST 追踪器已初始化: "
                f"domain={self.scene_name}"
            )
        else:
            raise ValueError(
                f"不支持的执行模式: {self.mode!r}。"
                "支持的模式: 'pytod', 'dst'"
            )
