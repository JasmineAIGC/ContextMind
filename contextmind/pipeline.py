"""
ContextPipeline — 通用上下文工程流水线

将三步框架（知识库构建 → Schema 数据生成 → 算法执行）统一为一个高层接口。

三步框架
--------
1. **建立知识库**（Phase 1）：针对任意对话数据集，通过 LLM 自动发现槽位和意图，
   合成标准 SGD 格式 ``schema.json``。统一使用 ``examples/build_kb.py``。
2. **Schema 数据生成**（Phase 2，可选）：将 schema.json 转换为算法专用数据
   （如 PyTOD 的 API 代码文件）。DST / FnCTOD / Evolve 不需要此步骤。
3. **算法执行**（Phase 3）：基于 SGD 知识库，在对话中提取有效的上下文，提升对话质量。
   支持四种算法：DST、FnCTOD、PyTOD、Evolve。

算法与 schema.json 的关系
--------------------------
- ``"pytod"``（默认）：**需要** schema.json。PyTOD AP→EE→DM 三步流程，适合任务型对话。
- ``"fnctod"``：**需要** schema.json。ADK 原生函数调用，自动将 schema 槽位转为 FunctionTool。
- ``"dst"``：**可选** schema.json。对话状态追踪，纯槽位提取，无 API 调用。
- ``"evolve"``：**不需要** schema.json。演化式上下文优化（会话历史 + 长期记忆检索）。

``ContextPipeline`` 灵活整合三步流程，用户无需了解底层算法细节。

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

**注册自定义 API 函数（PyTOD 专用）**::

    pipeline = ContextPipeline(llm_client=AdkLLMClient())
    pipeline.load_kb("output/schema.json")

    @pipeline.register_api("query_loan_info")
    def query_loan_info(customer_name: str) -> dict:
        return {"credit_limit": 50000, "interest_rate": 0.12}

    result = await pipeline.process_turn("查询一下我的额度")

**不需要 schema 的模式（DST / Evolve）**::

    # DST：直接初始化，无需 build_kb/load_kb
    pipeline = ContextPipeline(llm_client=AdkLLMClient(), mode="dst")
    result = await pipeline.process_turn("我想了解贷款利率")

    # Evolve：上下文优化，基于会话历史和长期记忆
    pipeline = ContextPipeline(llm_client=AdkLLMClient(), mode="evolve",
                               scene_name="银行贷款外呼")
    result = await pipeline.process_turn("我想了解贷款利率")
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from contextmind.infra.llm_client import AdkLLMClient, LLMConfig
from contextmind.infra.logger import get_logger
from contextmind.knowledge.builder import KnowledgeBaseBuilder

logger = get_logger(__name__)


class _EvolveTrackerAdapter:
    """将 EvolveEngine 适配为与 BaseTracker 兼容的 process_turn / get_current_state / reset 接口。

    Evolve 的核心功能是上下文优化（会话历史 + 长期记忆检索），与 PyTOD/DST 的意图-槽位
    提取范式不同。本适配器将 ``optimize() + update()`` 组合封装为统一的 ``process_turn()``：

    - ``response``   : 最近 N 条上下文项拼接而成的可读文本（供调用方参考上下文）
    - ``state``      : 本轮检索到的上下文统计（session 条数、记忆条数）
    - ``turn_updates``: 同 state
    """

    def __init__(self, engine: Any) -> None:
        self._engine = engine
        self._state: Dict[str, Any] = {}

    async def process_turn(
        self, user_utterance: str, system_utterance: str = "", **kwargs: Any
    ) -> Dict[str, Any]:
        ctx_result = await self._engine.optimize(user_utterance)
        items = ctx_result.items or []
        # 最多取前 5 条上下文项拼成可读摘要
        response_parts = [item.content for item in items[:5]]
        response = "\n".join(response_parts) if response_parts else "(暂无历史上下文)"
        # 记录本轮对话到会话历史
        await self._engine.update(user_utterance, response)
        self._state = {
            "session_history_count": ctx_result.metadata.get("session_history_count", 0),
            "long_term_memory_count": ctx_result.metadata.get("long_term_memory_count", 0),
            "context_items": len(items),
        }
        return {
            "response": response,
            "state": dict(self._state),
            "turn_updates": dict(self._state),
        }

    def get_current_state(self) -> Dict[str, Any]:
        return dict(self._state)

    def reset(self) -> None:
        import asyncio

        self._state = {}
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._engine.clear_session())
            else:
                loop.run_until_complete(self._engine.clear_session())
        except RuntimeError:
            pass


class ContextPipeline:
    """
    通用上下文工程流水线。

    将知识库构建（Phase 1）和对话上下文提取（Phase 2）统一为一个简洁接口。

    参数
    ----
    llm_client:
        LLM 客户端实例（如 ``AdkLLMClient``）；为 None 时从 ``.env`` 自动加载。
    mode:
        执行模式（四选一）：

        - ``"pytod"``（默认）：PyTOD AP→EE→DM 三步流程，适合任务型对话。**需要 schema。**
        - ``"fnctod"``：ADK 原生函数调用对话状态追踪。**需要 schema。**
        - ``"dst"``：对话状态追踪，纯槽位提取，无 API 调用。**schema 可选。**
        - ``"evolve"``：演化式上下文优化（会话记忆 + 长期记忆检索）。**不需要 schema。**

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
        worksheet_path: Optional[Union[str, Path]] = None,
        genie_intent: Optional[str] = None,
    ) -> None:
        self._llm_client = llm_client
        self.mode = mode
        self.scene_name = scene_name
        self.scene_description = scene_description or scene_name
        self.discovery_sample = discovery_sample
        self.max_history_turns = max_history_turns
        # Genie 模式专用：Worksheet 文件路径 + 目标意图名称
        self._worksheet_path: Optional[Path] = Path(worksheet_path) if worksheet_path else None
        self._genie_intent: Optional[str] = genie_intent

        self.schema: Optional[Any] = None
        self.tracker: Optional[Any] = None
        self._engine: Optional[Any] = None
        self._kb_builder: Optional[KnowledgeBaseBuilder] = None
        # schema.json 路径（load_kb() 时设置），用于自动加载同目录下的
        # companion *_pytod_apis.py 预生成函数文件
        self._schema_path: Optional[Path] = None

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

    def load_kb(
        self,
        schema_path: Union[str, Path],
        merge: bool = False,
        worksheet_path: Optional[Union[str, Path]] = None,
    ) -> None:
        """
        Phase 1 → Phase 2 桥接：从磁盘加载已保存的 ``schema.json``。

        自动初始化 Phase 2 追踪器，可立即调用 :meth:`process_turn`。

        参数
        ----
        schema_path:
            由 :meth:`build_kb` 或
            :meth:`~contextmind.kb.KnowledgeBaseBuilder.save` 生成的
            ``schema.json`` 文件路径。
        merge:
            若为 ``True`` 且已有 :attr:`schema`，则将文件中的 schema **合并**到
            现有 schema（同名槽位/意图以文件中的定义为准，新增项追加）；
            若为 ``False``（默认），则完全替换现有 schema。
        worksheet_path:
            （Genie 模式专用）Worksheet 文件路径（CSV 或 JSON）；
            指定后将覆盖构造函数中的 ``worksheet_path``。
        """
        new_schema = KnowledgeBaseBuilder.load_schema(schema_path)
        if merge and self.schema is not None:
            self.schema = self.schema.merge(new_schema)
        else:
            self.schema = new_schema
        # 保存 schema 文件路径，供 _init_tracker() 加载 companion *_pytod_apis.py
        self._schema_path = Path(schema_path)
        if worksheet_path is not None:
            self._worksheet_path = Path(worksheet_path)
        self._init_tracker()
        logger.info(
            f"[ContextPipeline] 已加载 schema: {self.schema.service_name}，"
            f"槽位={len(self.schema.slots)}，意图={len(self.schema.intents)}"
        )

    def set_schema(self, schema: Any, merge: bool = False) -> None:
        """
        直接设置 ``ServiceSchema`` 实例（无需从文件加载）。

        适用于已有 :class:`~contextmind.modes.pytod.schemas.ServiceSchema` 对象的场景。

        参数
        ----
        schema:
            :class:`~contextmind.modes.pytod.schemas.ServiceSchema` 实例，
            或可通过 :func:`~contextmind.modes.pytod.schemas.load_schema_from_dict`
            转换的字典。
        merge:
            若为 ``True`` 且已有 :attr:`schema`，则将传入 schema **合并**到
            现有 schema（同名槽位/意图以传入值为准，新增项追加）；
            若为 ``False``（默认），则完全替换现有 schema。
        """
        from contextmind.modes.pytod.schemas import ServiceSchema

        if isinstance(schema, dict):
            from contextmind.modes.pytod.schemas import load_schema_from_dict

            new_schema = load_schema_from_dict(schema)
        elif isinstance(schema, ServiceSchema):
            new_schema = schema
        else:
            raise TypeError(
                f"schema 必须是 ServiceSchema 实例或字典，得到: {type(schema)}"
            )
        if merge and self.schema is not None:
            self.schema = self.schema.merge(new_schema)
        else:
            self.schema = new_schema
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
        # DST 和 Evolve 不需要 schema；PyTOD 和 FnCTOD 需要 schema；
        # Genie 可用 worksheet_path 替代 schema，此处仅在两者均缺失时报错
        _schema_optional = self.mode in ("dst", "evolve")
        _genie_ok = self.mode == "genie" and self._worksheet_path is not None
        if self.schema is None and not _schema_optional and not _genie_ok:
            raise RuntimeError(
                "尚未设置 schema，请先调用 build_kb() 或 load_kb()。\n"
                "提示：若使用 mode='dst' 或 mode='evolve'，可直接调用 process_turn() 无需 schema。"
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

        - PyTOD / FnCTOD 需要 schema，缺少时推迟到 schema 就绪后再调用。
        - DST / Evolve 不需要 schema，可立即初始化。
        - Genie 需要 schema 或 worksheet_path，两者均缺失时推迟初始化。
        - 若 LLM 客户端尚未提供（``_llm_client is None``），则跳过初始化，
          等待 :meth:`process_turn` 时再延迟初始化。
        """
        # PyTOD / FnCTOD 必须有 schema 才能初始化
        _requires_schema = self.mode in ("pytod", "fnctod")
        if _requires_schema and self.schema is None:
            return

        # Genie 需要 schema 或 worksheet_path
        if self.mode == "genie" and self.schema is None and self._worksheet_path is None:
            return

        # 若 LLM 客户端还未提供，延迟到 process_turn() 时初始化
        if self._llm_client is None:
            return

        if self.mode == "pytod":
            from contextmind.modes.pytod.tracker import AdkPyTODTracker
            from contextmind.modes.pytod.registry import SCENARIO_API_REGISTRY, get_scenario_key
            from contextmind.modes.pytod.tracker import load_pytod_api_module

            engine = self._get_engine()
            # 优先注册预定义的场景 API（如 callcenter、insurance 等），
            # 使得 schema.json 意图名与预置函数名匹配时可直接调用真实实现。
            # 已通过 register_api() 手动注册的函数不会被覆盖（engine.registry 已有）。
            _scene_key = get_scenario_key(self.scene_name)
            if _scene_key and _scene_key in SCENARIO_API_REGISTRY:
                SCENARIO_API_REGISTRY[_scene_key](engine)
                logger.debug(
                    f"[ContextPipeline] 已为场景 '{self.scene_name}' 注册预置 API: "
                    f"{engine.list_functions()}"
                )
            # 尝试从与 schema.json 同目录的 companion *_pytod_apis.py 加载预生成函数。
            # 预生成函数含真实业务逻辑，优先级高于存根；已注册的函数不会被覆盖。
            if self._schema_path is not None:
                api_funcs = load_pytod_api_module(self._schema_path)
                if api_funcs:
                    for func_name, func in api_funcs.items():
                        if func_name not in engine.registry:
                            engine.registry[func_name] = func
                    logger.info(
                        f"[ContextPipeline] 已从 companion 文件加载 {len(api_funcs)} 个预生成 API 函数"
                    )
            # 为 schema 中尚未注册的意图自动生成存根，确保 AP 程序可执行
            self._register_schema_stubs(engine)
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

        elif self.mode == "fnctod":
            from contextmind.modes.fnctod.tracker import FnCTODTracker
            from contextmind.modes.fnctod.function_manager import FunctionManager

            # 将 ServiceSchema 转换为 FunctionManager（槽位 → 函数参数）
            fm = FunctionManager()
            slots_dict = {s.name: s.description for s in self.schema.slots}
            categorical = {
                s.name: s.possible_values
                for s in self.schema.slots
                if s.is_categorical and s.possible_values
            }
            required: List[str] = []
            for intent in self.schema.intents:
                required.extend(intent.required_slots)
            fm.add_domain_from_slots(
                domain_name=self.schema.service_name,
                domain_description=self.schema.description or self.scene_description,
                slots=slots_dict,
                categorical_slots=categorical or None,
                required_slots=list(set(required)) or None,
            )
            # FnCTODTracker 使用 LLMConfig.from_env() 作为默认配置
            llm = self._get_llm()
            config = getattr(llm, "_config", None)
            self.tracker = FnCTODTracker(
                function_manager=fm,
                config=config,
            )
            logger.debug(
                f"[ContextPipeline] FnCTOD 追踪器已初始化: "
                f"schema={self.schema.service_name}, "
                f"槽位={len(slots_dict)}"
            )

        elif self.mode == "dst":
            from contextmind.modes.dst.tracker import DialogueStateTracker
            from contextmind.modes.dst.prompts import PromptManager

            prompt_manager = PromptManager(
                domain=self.scene_name,
                enable_dynamic_slots=True,
            )
            # 将 schema 槽位注入 DST prompt 管理器（schema 可能为 None）
            if self.schema is not None and hasattr(prompt_manager, "slots"):
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

        elif self.mode == "evolve":
            from contextmind.modes.evolve import EvolveEngine

            engine = EvolveEngine(
                app_name=self.scene_name,
                user_id="default_user",
                llm_client=self._get_llm(),
            )
            self.tracker = _EvolveTrackerAdapter(engine)
            logger.debug(
                f"[ContextPipeline] Evolve 追踪器已初始化: "
                f"app={self.scene_name}"
            )

        elif self.mode == "genie":
            from contextmind.modes.genie.tracker import GenieTracker
            from contextmind.schema_builder.genie_worksheets import WorksheetLoader

            # 优先使用 worksheet_path 加载含 policy_fields 的 schema；
            # 若无 worksheet_path，则从已加载的 schema 推导（schema 必须存在）。
            genie_schema = self.schema
            if self._worksheet_path is not None:
                ws_path = self._worksheet_path
                if ws_path.suffix.lower() == ".csv":
                    genie_schema = WorksheetLoader.from_csv(
                        ws_path,
                        service_name=self.scene_name,
                        service_description=self.scene_description,
                    )
                elif ws_path.suffix.lower() in (".json", ".jsonl"):
                    genie_schema = WorksheetLoader.from_json(ws_path)
                else:
                    raise ValueError(
                        f"worksheet_path 只支持 .csv 或 .json，得到: {ws_path.suffix}"
                    )
                logger.info(
                    f"[ContextPipeline] Genie 模式：从 Worksheet 加载 schema: {ws_path.name}"
                )
            elif genie_schema is None:
                raise RuntimeError(
                    "Genie 模式需要提供 schema 或 worksheet_path。\n"
                    "提示：先调用 load_kb() 或在构造时传入 worksheet_path=..."
                )

            self.tracker = GenieTracker(
                llm_client=self._get_llm(),
                schema=genie_schema,
                scene_description=self.scene_description,
                intent_name=self._genie_intent,
                max_history_turns=self.max_history_turns,
            )
            logger.debug(
                f"[ContextPipeline] Genie 追踪器已初始化: "
                f"schema={genie_schema.service_name}, "
                f"intent={self._genie_intent or '(auto)'}"
            )

        else:
            raise ValueError(
                f"不支持的执行模式: {self.mode!r}。\n"
                "支持的模式:\n"
                "  'pytod'  — PyTOD 三步流程，需要 schema（默认）\n"
                "  'fnctod' — ADK 原生函数调用，需要 schema\n"
                "  'dst'    — 对话状态追踪，schema 可选\n"
                "  'evolve' — 演化式上下文优化，不需要 schema\n"
                "  'genie'  — Genie Worksheets 声明式策略，需要 schema 或 worksheet_path"
            )

    def _register_schema_stubs(self, engine: Any) -> None:
        """为 schema 中尚未注册的意图自动注册存根函数。

        存根函数接受任意关键字参数，返回包含所有 result_slots 的字典
        （值为空字符串占位符）。这样动作解析器生成的意图调用不会被执行引擎
        拒绝，同时也不影响用户通过 :meth:`register_api` 注册的真实函数。

        仅在 ``mode == "pytod"`` 时由 :meth:`_init_tracker` 调用。
        """
        if self.schema is None:
            return

        registered = 0
        for intent in self.schema.intents:
            if intent.name in engine.registry:
                continue  # 已有真实实现，不覆盖

            result_slots: List[str] = list(intent.result_slots)

            # 使用闭包捕获 result_slots，避免循环变量绑定问题
            def _make_stub(slots: List[str]) -> Callable:
                def _stub(**kwargs: Any) -> Dict[str, Any]:
                    return {s: "" for s in slots}
                return _stub

            stub = _make_stub(result_slots)
            stub.__name__ = intent.name
            engine.registry[intent.name] = stub
            registered += 1

        if registered:
            logger.debug(
                f"[ContextPipeline] 已为 {registered} 个 schema 意图注册存根函数: "
                f"{[i.name for i in self.schema.intents if i.name in engine.registry]}"
            )
