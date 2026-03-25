"""
通用知识库构建器

将任意对话数据集经过两步处理，输出标准 SGD 格式 ``schema.json``：

1. **发现阶段**（Discovery）：
   使用 :class:`~contextmind.knowledge.discoverer.GenericDialogueDiscoverer` 以开放式模式
   扫描样本对话，通过 ``langextract`` 逐轮提取知识并为每条结果附加原文溯源。
   不依赖任何特定场景模块，可用于任意业务场景。

2. **合成阶段**（Synthesis）：
   将发现阶段收集到的槽位/意图计数及样本，调用 LLM 第二次，
   输出规范化的 SGD ServiceSchema JSON。

输出的 ``schema.json`` 格式为标准 SGD ServiceSchema，
可直接传入 :class:`~contextmind.modes.pytod.AdkPyTODTracker` 使用。

**模块独立性**：本模块不依赖 ``contextmind.modes`` 或
``contextmind.scenarios`` 等其他子模块，仅依赖 ``contextmind.infra``
（基础设施）和 ``langextract``（知识溯源）。

典型用法::

    import json
    from pathlib import Path
    from contextmind.knowledge import KnowledgeBaseBuilder

    dialogues = json.loads(Path("my_dialogues.json").read_text())

    builder = KnowledgeBaseBuilder(
        scene_name="银行贷款外呼",
        scene_description="银行客服主动致电老客户推介个人贷款产品",
    )
    schema_dict = builder.build(dialogues[:20])   # 用前 20 条做发现
    builder.save(schema_dict, Path("output/schema.json"))

    # Phase 1 → Phase 2 桥接（在调用方完成，不在 kb 模块内）：
    from contextmind.modes.pytod.schemas import ServiceSchema
    service_schema = ServiceSchema.from_dict(schema_dict)
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from contextmind.infra.llm_client import AdkLLMClient, LLMConfig
from contextmind.infra.logger import get_logger
from .discoverer import GenericDialogueDiscoverer
from .normalizer import normalize_dialogues
from .synthesizer import SchemaSynthesizer

logger = get_logger(__name__)


def _extract_slot_char_positions(
    item: Any,
    utterance: str,
) -> Tuple[Optional[int], Optional[int]]:
    """从 DiscoveryItem 中提取字符区间，用于 SGD slot 的 start/exclusive_end 字段。

    优先从 provenance 字符串解析位置（格式：「...」[... 位置 X:Y]）；
    若 provenance 无位置信息，则在话语中搜索 extraction_text；
    若 extraction_text 不在话语中，尝试搜索 value。
    """
    provenance: Optional[str] = item.provenance
    if provenance:
        m = re.search(r"位置\s*(\d+):(\d+)", provenance)
        if m:
            return int(m.group(1)), int(m.group(2))

    # 在话语中搜索 extraction_text
    extraction_text: str = getattr(item, "extraction_text", "")
    if extraction_text:
        idx = utterance.find(extraction_text)
        if idx >= 0:
            return idx, idx + len(extraction_text)

    # 最后尝试搜索 value
    value: str = item.value or ""
    if value:
        idx = utterance.find(value)
        if idx >= 0:
            return idx, idx + len(value)

    return None, None


class KnowledgeBaseBuilder:
    """
    通用知识库构建器：任意对话数据 → SGD ``schema.json``。

    参数
    ----
    scene_name:
        业务场景的中文名称（如 ``"银行贷款外呼"``），用于 LLM 提示词。
    scene_description:
        场景简短描述（一句话），可为空；留空则使用 ``scene_name``。
    llm_client:
        :class:`~contextmind.infra.llm_client.AdkLLMClient` 实例；
        若为 ``None``，从 ``.env`` 自动加载。
    discovery_sample:
        发现阶段最多使用的对话条数（默认 20）。
        数量越多、发现越全面，但 LLM 调用次数也越多。
    context_window:
        langextract 逐轮提取时的历史轮次窗口大小（默认 3）。
        传入 ``additional_context`` 的历史轮次数；0 = 不传历史上下文。

    属性
    ----
    last_slot_counter:
        最近一次 :meth:`build` 发现阶段产生的槽位计数器（供调试）。
    last_intent_counter:
        最近一次 :meth:`build` 发现阶段产生的意图计数器（供调试）。
    """

    def __init__(
        self,
        scene_name: str,
        scene_description: str = "",
        llm_client: Optional[AdkLLMClient] = None,
        discovery_sample: int = 20,
        context_window: int = 3,
    ) -> None:
        self.scene_name = scene_name
        self.scene_description = scene_description or scene_name
        self.discovery_sample = discovery_sample
        self.context_window = context_window

        # 延迟初始化：避免在无 LLM 环境下导入时崩溃
        self._llm_client: Optional[AdkLLMClient] = llm_client

        self.last_slot_counter: Counter = Counter()
        self.last_intent_counter: Counter = Counter()
        # 最近一次 build_dataset() 发现阶段的逐轮原始 DiscoveryItem 列表。
        # 结构：List[ List[ (turn_idx, speaker, utterance, [DiscoveryItem, ...]) ] ]
        # 每项对应一条对话，可通过 save_dataset() 写入 discovery_raw.json。
        self.last_discovery_turns: List[Any] = []

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def build(
        self,
        dialogues: List[Any],
    ) -> Dict[str, Any]:
        """
        对输入对话执行完整的两阶段知识库构建流程。

        参数
        ----
        dialogues:
            对话列表，每项可为以下任一格式：

            - ``str``：平铺文本（换行分隔，每行含说话人前缀）
            - ``List[str]``：每项为一轮话语
            - ``dict``（chat_test 格式，含 ``对话历史``）
            - ``dict``（SGD 格式，含 ``turns``）

        返回
        ----
        SGD 格式的 **单服务** schema dict（不带顶层列表包裹）::

            {
              "service_name": "...",
              "description": "...",
              "slots": [...],
              "intents": [...]
            }

        将其包入列表 ``[schema_dict]`` 即可写入标准 ``schema.json``。
        """
        # -- Step 0: 归一化 --
        logger.info(
            f"[KnowledgeBaseBuilder] 场景: {self.scene_name!r}，"
            f"输入对话: {len(dialogues)} 条"
        )
        normalized = normalize_dialogues(dialogues)
        sample = normalized[: self.discovery_sample]
        logger.info(
            f"[KnowledgeBaseBuilder] 发现阶段使用前 {len(sample)} 条对话"
        )

        # -- Step 1: 发现阶段 --
        slot_counter, intent_counter, slot_samples, intent_samples = (
            self._run_discovery(sample)
        )
        self.last_slot_counter = slot_counter
        self.last_intent_counter = intent_counter

        logger.info(
            f"[KnowledgeBaseBuilder] 发现阶段完成 — "
            f"槽位类型 {len(slot_counter)} 个，意图类型 {len(intent_counter)} 个"
        )

        # -- Step 2: 合成阶段 --
        synthesizer = SchemaSynthesizer(llm_client=self._get_llm())
        schema_dict = synthesizer.synthesize(
            scene_name=self.scene_name,
            scene_description=self.scene_description,
            slot_counter=slot_counter,
            intent_counter=intent_counter,
            slot_sample_values=slot_samples,
            intent_sample_descs=intent_samples,
            n_dialogues=len(sample),
        )
        return schema_dict

    def save(
        self,
        schema_dict: Dict[str, Any],
        path: Union[str, Path],
    ) -> None:
        """
        将 schema dict 包入列表并写入标准 SGD ``schema.json`` 文件。

        参数
        ----
        schema_dict:
            :meth:`build` 返回的单服务 schema dict。
        path:
            输出文件路径（如 ``"output/schema.json"``）。
            父目录不存在时自动创建。
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([schema_dict], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"[KnowledgeBaseBuilder] schema.json 已写入: {path}")

    def build_dataset(
        self,
        dialogues: List[Any],
    ) -> Dict[str, Any]:
        """
        构建完整的 SGD 格式数据集：``schema.json`` + ``dialogues_*.json``。

        与 :meth:`build` 相比，此方法额外生成 SGD 格式的标注对话文件，
        将输入对话转换为含 ``turns / frames / state`` 的 SGD 标注结构。

        参数
        ----
        dialogues:
            对话列表，格式同 :meth:`build`。

        返回
        ----
        ::

            {
              "schema": schema_dict,            # 单服务 schema（同 build() 返回值）
              "dialogues": [sgd_dlg, ...],      # SGD 格式标注对话列表
            }

        使用 :meth:`save_dataset` 将结果写入磁盘。
        """
        logger.info(
            f"[KnowledgeBaseBuilder] 数据集构建：场景 {self.scene_name!r}，"
            f"输入对话 {len(dialogues)} 条"
        )
        normalized = normalize_dialogues(dialogues)
        # build_dataset() 使用全部归一化对话，确保知识提取不遗漏；
        # 调用方通过传入的 dialogues 数量来控制处理范围。

        # -- Step 1: 发现阶段（逐轮，保留每轮提取结果用于 SGD 标注） --
        (
            slot_counter,
            intent_counter,
            slot_samples,
            intent_samples,
            per_dlg_turns,
            fact_counter,
            fact_samples,
        ) = self._run_discovery_per_turn(normalized)
        self.last_slot_counter = slot_counter
        self.last_intent_counter = intent_counter
        self.last_discovery_turns = per_dlg_turns

        logger.info(
            f"[KnowledgeBaseBuilder] 发现阶段完成 — "
            f"槽位类型 {len(slot_counter)} 个，意图类型 {len(intent_counter)} 个，"
            f"事实类型 {len(fact_counter)} 个"
        )

        # -- Step 2: 合成阶段 --
        synthesizer = SchemaSynthesizer(llm_client=self._get_llm())
        schema_dict = synthesizer.synthesize(
            scene_name=self.scene_name,
            scene_description=self.scene_description,
            slot_counter=slot_counter,
            intent_counter=intent_counter,
            slot_sample_values=slot_samples,
            intent_sample_descs=intent_samples,
            n_dialogues=len(normalized),
            fact_counter=fact_counter,
            fact_sample_descs=fact_samples,
        )

        # -- Step 3: 转换为 SGD 对话格式 --
        service_name = schema_dict.get("service_name", self.scene_name)
        sgd_dialogues = []
        for dlg_idx, (dlg, per_turn) in enumerate(zip(normalized, per_dlg_turns)):
            sgd_dlg = self._convert_to_sgd_dialogue(
                dlg, per_turn, service_name, dlg_idx
            )
            sgd_dialogues.append(sgd_dlg)

        return {"schema": schema_dict, "dialogues": sgd_dialogues}

    def save_dataset(
        self,
        dataset: Dict[str, Any],
        output_dir: Union[str, Path],
        dialogues_per_file: int = 999,
    ) -> None:
        """
        将 :meth:`build_dataset` 返回的数据集写入 SGD 格式目录。

        目录结构::

            output_dir/
                schema.json              # 服务 schema（标准 SGD 格式，顶层列表）
                dialogues_001.json       # SGD 对话文件（每文件最多 dialogues_per_file 条）
                dialogues_002.json       # 若对话超过单文件上限则自动分片
                conversion_summary.json  # 转换摘要

        参数
        ----
        dataset:
            :meth:`build_dataset` 的返回值。
        output_dir:
            输出目录（不存在时自动创建）。
        dialogues_per_file:
            每个 ``dialogues_*.json`` 文件最多包含的对话条数（默认 999）。
        """
        import datetime

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        schema_dict = dataset["schema"]
        sgd_dialogues = dataset["dialogues"]
        service_name = schema_dict.get("service_name", self.scene_name)

        # 写入 schema.json
        schema_path = output_dir / "schema.json"
        schema_path.write_text(
            json.dumps([schema_dict], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"[KnowledgeBaseBuilder] schema.json 已写入: {schema_path}")

        # 写入 dialogues_*.json（按 dialogues_per_file 分片）
        dialogue_files: List[str] = []
        for chunk_idx, start in enumerate(
            range(0, max(1, len(sgd_dialogues)), dialogues_per_file), start=1
        ):
            chunk = sgd_dialogues[start : start + dialogues_per_file]
            fname = f"dialogues_{chunk_idx:03d}.json"
            fpath = output_dir / fname
            fpath.write_text(
                json.dumps(chunk, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            dialogue_files.append(fname)
            logger.info(
                f"[KnowledgeBaseBuilder] {fname} 已写入: {fpath} "
                f"({len(chunk)} 条对话)"
            )

        # 统计总轮次
        total_turns = sum(len(d.get("turns", [])) for d in sgd_dialogues)

        # 写入 discovery_raw.json（逐轮原始提取结果，含 langextract 溯源信息）
        if self.last_discovery_turns:
            raw_records = []
            for sgd_dlg, per_turn in zip(sgd_dialogues, self.last_discovery_turns):
                turn_records = []
                for turn_idx, speaker, utterance, items in per_turn:
                    extractions = [
                        {
                            "extraction_class": item.extraction_class,
                            "label": item.label,
                            "value": item.value,
                            "provenance": item.provenance,
                        }
                        for item in items
                    ]
                    turn_records.append(
                        {
                            "turn_idx": turn_idx,
                            "speaker": speaker,
                            "utterance": utterance,
                            "extractions": extractions,
                        }
                    )
                raw_records.append(
                    {
                        "dialogue_id": sgd_dlg.get("dialogue_id", ""),
                        "turns": turn_records,
                    }
                )
            raw_path = output_dir / "discovery_raw.json"
            raw_path.write_text(
                json.dumps(raw_records, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info(
                f"[KnowledgeBaseBuilder] discovery_raw.json 已写入: {raw_path} "
                f"（{len(raw_records)} 条对话）"
            )

        # 写入 conversion_summary.json
        summary = {
            "output_dir": str(output_dir),
            "dialogues": len(sgd_dialogues),
            "turns": total_turns,
            "failed": 0,
            "dialogue_files": len(dialogue_files),
            "services": [service_name],
            "converted_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "discovered_schema_items": len(self.last_slot_counter)
            + len(self.last_intent_counter),
            "schema_coverage": {
                "extracted_slots": list(self.last_slot_counter.keys()),
                "extracted_intents": list(self.last_intent_counter.keys()),
                "schema_slots": [
                    s["name"] for s in schema_dict.get("slots", [])
                ],
                "schema_intents": [
                    i["name"] for i in schema_dict.get("intents", [])
                ],
            },
        }
        summary_path = output_dir / "conversion_summary.json"
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(
            f"[KnowledgeBaseBuilder] 数据集保存完成 → {output_dir} "
            f"（{len(sgd_dialogues)} 条对话，{total_turns} 轮）"
        )

    # ------------------------------------------------------------------
    # Phase 1 → Phase 2 桥接方法
    # ------------------------------------------------------------------

    @classmethod
    def to_service_schema(cls, schema_dict: Dict[str, Any]) -> Any:
        """将 :meth:`build` 返回的 schema dict 转换为 ``ServiceSchema`` 实例。

        这是 **Phase 1 → Phase 2 桥接** 的便捷方法，无需调用方手动导入
        ``ServiceSchema``。

        参数
        ----
        schema_dict:
            :meth:`build` 或 :meth:`build_dataset` 中 ``dataset["schema"]`` 的返回值。

        返回
        ----
        :class:`~contextmind.modes.pytod.schemas.ServiceSchema` 实例，
        可直接传入 ``AdkPyTODTracker``。

        示例
        ----
        ::

            schema_dict = builder.build(dialogues)
            service_schema = KnowledgeBaseBuilder.to_service_schema(schema_dict)
            tracker = AdkPyTODTracker(llm_client=llm, engine=engine, schema=service_schema)
        """
        from contextmind.modes.pytod.schemas import load_schema_from_dict

        return load_schema_from_dict(schema_dict)

    @classmethod
    def load_schema(cls, path: Union[str, Path]) -> Any:
        """从磁盘上的 ``schema.json`` 文件加载并返回 ``ServiceSchema`` 实例。

        这是 **Phase 1 → Phase 2 桥接** 的便捷方法，适用于已保存知识库的场景。

        参数
        ----
        path:
            ``schema.json`` 文件路径（由 :meth:`save` 或 :meth:`save_dataset` 生成）。

        返回
        ----
        :class:`~contextmind.modes.pytod.schemas.ServiceSchema` 实例。

        示例
        ----
        ::

            # Phase 1 已运行，schema.json 已保存
            service_schema = KnowledgeBaseBuilder.load_schema("output/schema.json")
            tracker = AdkPyTODTracker(llm_client=llm, engine=engine, schema=service_schema)
        """
        from contextmind.modes.pytod.schemas import load_schema_from_dict

        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return load_schema_from_dict(data)

    async def build_async(
        self,
        dialogues: List[Any],
    ) -> Dict[str, Any]:
        """异步版本的 :meth:`build`：在线程池中运行同步构建流程。

        与 :meth:`build` 功能完全相同，但以 ``async/await`` 方式运行，
        适用于已有异步事件循环的应用场景（如 web 服务、ADK agent 等）。

        参数
        ----
        dialogues:
            对话列表，格式同 :meth:`build`。

        返回
        ----
        SGD 格式的单服务 schema dict（同 :meth:`build`）。
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.build, dialogues)

    async def build_dataset_async(
        self,
        dialogues: List[Any],
    ) -> Dict[str, Any]:
        """异步版本的 :meth:`build_dataset`：在线程池中运行同步构建流程。

        参数
        ----
        dialogues:
            对话列表，格式同 :meth:`build_dataset`。

        返回
        ----
        ``{"schema": schema_dict, "dialogues": [sgd_dlg, ...]}``（同 :meth:`build_dataset`）。
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.build_dataset, dialogues)

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

    def _run_discovery(
        self,
        normalized_dialogues: List[Dict[str, Any]],
    ) -> tuple[Counter, Counter, Dict[str, List[str]], Dict[str, List[str]]]:
        """
        发现阶段：对每条对话运行开放式 LLM + langextract 提取，汇总槽位和意图。

        使用 :class:`~contextmind.knowledge.discoverer.GenericDialogueDiscoverer`
        逐轮提取，通过 langextract 附加溯源信息。

        返回
        ----
        (slot_counter, intent_counter, slot_sample_values, intent_sample_descs)

        - slot_counter: ``Counter({slot_name: 出现次数})``
        - intent_counter: ``Counter({intent_name: 出现次数})``
        - slot_sample_values: ``{slot_name: [value, ...]}``（最多 5 个）
        - intent_sample_descs: ``{intent_name: [description, ...]}``（最多 3 个）
        """
        discoverer = GenericDialogueDiscoverer(
            llm_client=self._get_llm(),
            scene_name=self.scene_name,
            context_window=self.context_window,
        )

        slot_counter: Counter = Counter()
        intent_counter: Counter = Counter()
        slot_sample_values: Dict[str, List[str]] = {}
        intent_sample_descs: Dict[str, List[str]] = {}

        for i, dlg in enumerate(normalized_dialogues):
            dialogue_id = dlg.get("session_id", f"dlg_{i}")
            logger.info(
                f"[KnowledgeBaseBuilder] 发现对话 {i+1}/{len(normalized_dialogues)} "
                f"({dialogue_id})"
            )
            try:
                items = discoverer.extract(dlg)
            except Exception as exc:
                logger.warning(
                    f"[KnowledgeBaseBuilder] 对话 {dialogue_id} 提取失败，跳过: {exc}"
                )
                continue

            for item in items:
                if item.extraction_class == "slot_value" and item.label:
                    slot_counter[item.label] += 1
                    samples = slot_sample_values.setdefault(item.label, [])
                    if item.value and len(samples) < 5:
                        if item.value not in samples:
                            samples.append(item.value)

                elif item.extraction_class == "intent" and item.label:
                    intent_counter[item.label] += 1
                    descs = intent_sample_descs.setdefault(item.label, [])
                    if item.value and len(descs) < 3:
                        if item.value not in descs:
                            descs.append(item.value)

        return slot_counter, intent_counter, slot_sample_values, intent_sample_descs

    def _run_discovery_per_turn(
        self,
        normalized_dialogues: List[Dict[str, Any]],
    ) -> tuple[
        Counter,
        Counter,
        Dict[str, List[str]],
        Dict[str, List[str]],
        List[List[Any]],
        Counter,
        Dict[str, List[str]],
    ]:
        """
        发现阶段（逐轮版），汇总统计的同时保留每条对话的逐轮提取结果。

        返回
        ----
        (slot_counter, intent_counter, slot_sample_values,
         intent_sample_descs, per_dialogue_turns,
         fact_counter, fact_sample_descs)

        ``per_dialogue_turns`` 是一个列表，每项对应一条对话，内容为
        ``[(turn_idx, speaker, utterance, [DiscoveryItem, ...]), ...]``。
        """
        from .discoverer import DiscoveryItem

        discoverer = GenericDialogueDiscoverer(
            llm_client=self._get_llm(),
            scene_name=self.scene_name,
            context_window=self.context_window,
        )

        slot_counter: Counter = Counter()
        intent_counter: Counter = Counter()
        fact_counter: Counter = Counter()
        slot_sample_values: Dict[str, List[str]] = {}
        intent_sample_descs: Dict[str, List[str]] = {}
        fact_sample_descs: Dict[str, List[str]] = {}
        per_dialogue_turns: List[List[Any]] = []

        for i, dlg in enumerate(normalized_dialogues):
            dialogue_id = dlg.get("session_id", f"dlg_{i}")
            logger.info(
                f"[KnowledgeBaseBuilder] 发现对话 {i+1}/{len(normalized_dialogues)} "
                f"({dialogue_id})"
            )
            try:
                per_turn = discoverer.extract_per_turn(dlg)
            except Exception as exc:
                logger.warning(
                    f"[KnowledgeBaseBuilder] 对话 {dialogue_id} 提取失败，跳过: {exc}"
                )
                per_dialogue_turns.append([])
                continue

            per_dialogue_turns.append(per_turn)

            for _, _, _, items in per_turn:
                for item in items:
                    if item.extraction_class == "slot_value" and item.label:
                        slot_counter[item.label] += 1
                        samples = slot_sample_values.setdefault(item.label, [])
                        if item.value and len(samples) < 5:
                            if item.value not in samples:
                                samples.append(item.value)
                    elif item.extraction_class == "intent" and item.label:
                        intent_counter[item.label] += 1
                        descs = intent_sample_descs.setdefault(item.label, [])
                        if item.value and len(descs) < 3:
                            if item.value not in descs:
                                descs.append(item.value)
                    elif item.extraction_class == "fact" and item.label:
                        fact_counter[item.label] += 1
                        descs = fact_sample_descs.setdefault(item.label, [])
                        if item.value and len(descs) < 3:
                            if item.value not in descs:
                                descs.append(item.value)

        return (
            slot_counter,
            intent_counter,
            slot_sample_values,
            intent_sample_descs,
            per_dialogue_turns,
            fact_counter,
            fact_sample_descs,
        )

    def _convert_to_sgd_dialogue(
        self,
        normalized_dlg: Dict[str, Any],
        per_turn: List[Any],
        service_name: str,
        dialogue_index: int,
    ) -> Dict[str, Any]:
        """将归一化对话及其逐轮提取结果转换为 SGD 格式对话 dict。

        参数
        ----
        normalized_dlg:
            归一化后的对话 dict。
        per_turn:
            ``[(turn_idx, speaker, utterance, [DiscoveryItem, ...]), ...]``
        service_name:
            SGD 服务名称（来自 schema）。
        dialogue_index:
            对话在样本集中的下标，用于生成 dialogue_id。

        返回
        ----
        SGD 格式对话 dict，含 ``dialogue_id / services / turns``。
        """
        import re as _re

        dialogue_id = (
            normalized_dlg.get("session_id")
            or normalized_dlg.get("dialogue_id")
            or f"{service_name}_{dialogue_index + 1:04d}"
        )

        sgd_turns: List[Dict[str, Any]] = []
        cumulative_slot_values: Dict[str, List[str]] = {}
        current_intent = "NONE"

        _SYSTEM_SPEAKERS = {"机器人", "坐席", "agent", "system", "assistant", "SYSTEM"}

        for turn_idx, speaker, utterance, items in per_turn:
            sgd_speaker = "SYSTEM" if speaker in _SYSTEM_SPEAKERS else "USER"

            # 当前轮的槽位提及 + INFORM actions
            turn_slot_mentions: List[Dict[str, Any]] = []
            turn_actions: List[Dict[str, Any]] = []
            for item in items:
                if item.extraction_class == "slot_value" and item.label and item.value:
                    slot_entry: Dict[str, Any] = {
                        "slot": item.label,
                        "value": item.value,
                    }
                    # 从 provenance 字符串解析字符位置，或直接在话语中搜索
                    char_start, char_end = _extract_slot_char_positions(
                        item, utterance
                    )
                    if char_start is not None:
                        slot_entry["start"] = char_start
                        slot_entry["exclusive_end"] = char_end
                    turn_slot_mentions.append(slot_entry)
                    cumulative_slot_values[item.label] = [item.value]
                    turn_actions.append(
                        {
                            "act": "INFORM",
                            "slot": item.label,
                            "values": [item.value],
                            "canonical_values": [item.value],
                        }
                    )
                elif item.extraction_class == "intent" and item.label:
                    current_intent = item.label

            frame: Dict[str, Any] = {
                "service": service_name,
                "slots": turn_slot_mentions,
                "actions": turn_actions,
            }
            if sgd_speaker == "USER":
                frame["state"] = {
                    "active_intent": current_intent,
                    "requested_slots": [],
                    "slot_values": dict(cumulative_slot_values),
                }

            sgd_turns.append(
                {
                    "speaker": sgd_speaker,
                    "utterance": utterance,
                    "frames": [frame],
                }
            )

        return {
            "dialogue_id": dialogue_id,
            "services": [service_name],
            "turns": sgd_turns,
        }
