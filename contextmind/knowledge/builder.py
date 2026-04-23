"""
通用知识库构建器

将任意对话数据集经过两步处理，输出标准 SGD 格式 ``schema.json``：

1. **发现阶段**（Discovery）：使用 LLM 以开放式模式逐轮提取知识，附加原文溯源。
2. **合成阶段**（Synthesis）：将槽位/意图计数及样本通过 LLM 合成规范化的 SGD ServiceSchema JSON。

输出的 ``schema.json`` 可直接传入 :class:`~contextmind.modes.pytod.AdkPyTODTracker` 使用。
"""

from __future__ import annotations

import json
import queue
import re
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from contextmind.infra.llm_client import AdkLLMClient, LLMConfig
from contextmind.infra.logger import get_logger
from .discoverer import GenericDialogueDiscoverer
from .normalizer import normalize_dialogues
from .synthesizer import SchemaSynthesizer, _merge_service_list, _fill_schema_defaults

logger = get_logger(__name__)

# discovery_raw.json: extraction_class sort order (intents first, then slots, then facts)
_DISCOVERY_CLASS_ORDER: Dict[str, int] = {"intent": 0, "slot_value": 1, "fact": 2}


def _print_schema_brief(prefix: str, schema_dict: Dict[str, Any]) -> None:
    """将 schema 的槽位和意图名称以简洁格式打印到终端。"""
    slots = schema_dict.get("slots", [])
    intents = schema_dict.get("intents", [])
    slot_names = [s.get("name", "?") for s in slots]
    intent_names = [it.get("name", "?") for it in intents]
    print(f"  {prefix}")
    if slot_names:
        print(f"    槽位（{len(slot_names)} 个）: {', '.join(slot_names)}")
    else:
        print("    槽位: （无）")
    if intent_names:
        print(f"    意图（{len(intent_names)} 个）: {', '.join(intent_names)}")
    else:
        print("    意图: （无）")


def _format_dialogue_snippets(
    normalized_dialogues: List[Dict[str, Any]],
    max_dialogues: int = 3,
    max_chars_per_dlg: int = 500,
) -> str:
    """将少量归一化对话格式化为可读文本片段，供 polish prompt 使用。"""
    snippets: List[str] = []
    for i, dlg in enumerate(normalized_dialogues[:max_dialogues], 1):
        lines: List[str] = []
        for turn in dlg.get("对话历史", []):
            if "机器人" in turn and turn["机器人"]:
                lines.append(f"机器人：{turn['机器人']}")
            if "用户" in turn and turn["用户"]:
                lines.append(f"用户：{turn['用户']}")
        text = "\n".join(lines)
        if len(text) > max_chars_per_dlg:
            text = text[:max_chars_per_dlg] + "…"
        if text:
            snippets.append(f"【对话 {i}】\n{text}")
    return "\n\n".join(snippets) if snippets else "（无对话片段）"


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

    discovery_sample: 发现阶段最多使用的对话条数（默认 20）。
    context_window: langextract 逐轮提取时的历史轮次窗口大小（默认 3；0 = 不传历史）。
    workers: 并发线程数（默认 1；受 LLM API 速率限制，建议不超过 8）。
    """

    def __init__(
        self,
        scene_name: str,
        scene_description: str = "",
        llm_client: Optional[AdkLLMClient] = None,
        discovery_sample: int = 20,
        context_window: int = 3,
        workers: int = 1,
        verbose: bool = False,
    ) -> None:
        self.scene_name = scene_name
        self.scene_description = scene_description or scene_name
        self.discovery_sample = discovery_sample
        self.context_window = context_window
        self.workers = max(1, workers)
        self.verbose = verbose

        # 延迟初始化：避免在无 LLM 环境下导入时崩溃
        self._llm_client: Optional[AdkLLMClient] = llm_client

        self.last_slot_counter: Counter = Counter()
        self.last_intent_counter: Counter = Counter()
        self.last_fact_counter: Counter = Counter()
        # 发现阶段逐轮原始 DiscoveryItem 列表，可通过 save_dataset() 写入 discovery_raw.json
        self.last_discovery_turns: List[Any] = []

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def build(
        self,
        dialogues: List[Any],
    ) -> Dict[str, Any]:
        """从对话列表执行两阶段知识库构建，返回单服务 SGD schema dict。

        dialogues 支持多种格式（str、List[str]、chat_test dict、SGD dict）。
        返回值包裹进列表 ``[schema_dict]`` 可直接写入标准 schema.json。
        """
        logger.info(
            f"[KnowledgeBaseBuilder] 场景: {self.scene_name!r}，"
            f"输入对话: {len(dialogues)} 条"
        )
        normalized = normalize_dialogues(dialogues)
        sample = normalized[: self.discovery_sample]
        logger.info(
            f"[KnowledgeBaseBuilder] 发现阶段使用前 {len(sample)} 条对话"
        )

        schema_dict, slot_counter, intent_counter = self._build_schema_from_dialogues(
            sample
        )
        self.last_slot_counter = slot_counter
        self.last_intent_counter = intent_counter
        return schema_dict

    def save(
        self,
        schema_dict: Dict[str, Any],
        path: Union[str, Path],
    ) -> None:
        """将 schema dict 包入列表并写入标准 SGD schema.json，父目录不存在时自动创建。"""
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
        """构建完整的 SGD 数据集：schema + SGD 格式标注对话。

        返回 ``{"schema": schema_dict, "dialogues": [sgd_dlg, ...]}``，
        使用 :meth:`save_dataset` 写入磁盘。
        """
        logger.info(
            f"[KnowledgeBaseBuilder] 数据集构建：场景 {self.scene_name!r}，"
            f"输入对话 {len(dialogues)} 条"
            + (f"，并行线程 {self.workers}" if self.workers > 1 else "")
        )
        normalized = normalize_dialogues(dialogues)

        discoverer = GenericDialogueDiscoverer(
            llm_client=self._get_llm(),
            scene_name=self.scene_name,
            context_window=self.context_window,
        )
        synthesizer = SchemaSynthesizer(llm_client=self._get_llm())

        n_total = len(normalized)
        per_dialogue_turns: List[List[Any]] = []
        accumulated_schema: Optional[Dict[str, Any]] = None
        n_merged: int = 0
        global_slot_counter: Counter = Counter()
        global_intent_counter: Counter = Counter()
        global_fact_counter: Counter = Counter()
        global_slot_samples: Dict[str, List[str]] = {}
        global_intent_samples: Dict[str, List[str]] = {}
        global_fact_samples: Dict[str, List[str]] = {}

        def _accumulate_items(per_turn: List[Any]) -> None:
            """将单条对话的逐轮提取结果累积到全局计数器和样本表中。"""
            for _, _, _, items in per_turn:
                for item in items:
                    if item.extraction_class == "slot_value" and item.label:
                        global_slot_counter[item.label] += 1
                        vals = global_slot_samples.setdefault(item.label, [])
                        if item.value and len(vals) < 5 and item.value not in vals:
                            vals.append(item.value)
                    elif item.extraction_class == "intent" and item.label:
                        global_intent_counter[item.label] += 1
                        descs = global_intent_samples.setdefault(item.label, [])
                        if item.value and len(descs) < 3 and item.value not in descs:
                            descs.append(item.value)
                    elif item.extraction_class == "fact" and item.label:
                        global_fact_counter[item.label] += 1
                        descs = global_fact_samples.setdefault(item.label, [])
                        if item.value and len(descs) < 3 and item.value not in descs:
                            descs.append(item.value)

        def _merge_incremental(
            i_label: str,
            schema_part: Dict[str, Any],
        ) -> None:
            """将 schema_part 增量融合进 accumulated_schema（就地修改闭包变量）。"""
            nonlocal accumulated_schema, n_merged
            if accumulated_schema is None:
                accumulated_schema = schema_part
            else:
                prev_n_slots = len(accumulated_schema.get("slots", []))
                prev_n_intents = len(accumulated_schema.get("intents", []))
                new_merged = _merge_service_list([accumulated_schema, schema_part])
                if new_merged is not None:
                    new_merged = _fill_schema_defaults(new_merged, scene_name=self.scene_name)
                    if (len(new_merged.get("slots", [])) < prev_n_slots or
                            len(new_merged.get("intents", [])) < prev_n_intents):
                        logger.warning(
                            f"[KnowledgeBaseBuilder] {i_label} 融合后条目异常减少，执行恢复合并"
                        )
                        restored = _merge_service_list([new_merged, accumulated_schema])
                        if restored is not None:
                            new_merged = _fill_schema_defaults(
                                restored, scene_name=self.scene_name
                            )
                    accumulated_schema = new_merged
            n_merged += 1
            acc_n_slots = len(accumulated_schema.get("slots", []))
            acc_n_intents = len(accumulated_schema.get("intents", []))
            logger.info(
                f"[KnowledgeBaseBuilder] {i_label} 融合后累积 — "
                f"槽位 {acc_n_slots} 个，意图 {acc_n_intents} 个（已融合 {n_merged} 条）"
            )
            print(
                f"  [{i_label}] 合并累积: {acc_n_slots} 个槽位，{acc_n_intents} 个意图"
                f"（已融合 {n_merged} 条对话）"
            )
            if self.verbose:
                _print_schema_brief(f"{i_label} 融合后累积:", accumulated_schema)

        def _synthesize_per_turn(
            per_turn: List[Any],
        ) -> Optional[Dict[str, Any]]:
            """从逐轮提取结果构建局部计数器，调用 LLM 合成单条对话 schema。"""
            local_slot_counter: Counter = Counter()
            local_intent_counter: Counter = Counter()
            local_fact_counter: Counter = Counter()
            local_slot_samples: Dict[str, List[str]] = {}
            local_intent_samples: Dict[str, List[str]] = {}
            local_fact_samples: Dict[str, List[str]] = {}
            for _, _, _, items in per_turn:
                for item in items:
                    if item.extraction_class == "slot_value" and item.label:
                        local_slot_counter[item.label] += 1
                        vals = local_slot_samples.setdefault(item.label, [])
                        if item.value and len(vals) < 5 and item.value not in vals:
                            vals.append(item.value)
                    elif item.extraction_class == "intent" and item.label:
                        local_intent_counter[item.label] += 1
                        descs = local_intent_samples.setdefault(item.label, [])
                        if item.value and len(descs) < 3 and item.value not in descs:
                            descs.append(item.value)
                    elif item.extraction_class == "fact" and item.label:
                        local_fact_counter[item.label] += 1
                        descs = local_fact_samples.setdefault(item.label, [])
                        if item.value and len(descs) < 3 and item.value not in descs:
                            descs.append(item.value)
            if not (local_slot_counter or local_intent_counter):
                return None
            return synthesizer.synthesize(
                scene_name=self.scene_name,
                scene_description=self.scene_description,
                slot_counter=local_slot_counter,
                intent_counter=local_intent_counter,
                slot_sample_values=local_slot_samples,
                intent_sample_descs=local_intent_samples,
                n_dialogues=1,
                fact_counter=local_fact_counter,
                fact_sample_descs=local_fact_samples,
            )

        if self.workers == 1:
            # ── 串行路径：每条对话提取后立即合并、融合 ──
            for i, dlg in enumerate(normalized):
                dialogue_id = dlg.get("session_id", f"dlg_{i}")
                logger.info(
                    f"[KnowledgeBaseBuilder] 处理对话 {i + 1}/{n_total} ({dialogue_id})"
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
                _accumulate_items(per_turn)

                # 统计局部计数（用于日志）：使用唯一 label 数量，避免重复计次带来的误导
                n_s = len(set(
                    item.label for _, _, _, items in per_turn for item in items
                    if item.extraction_class == "slot_value" and item.label
                ))
                n_i = len(set(
                    item.label for _, _, _, items in per_turn for item in items
                    if item.extraction_class == "intent" and item.label
                ))
                n_f = len(set(
                    item.label for _, _, _, items in per_turn for item in items
                    if item.extraction_class == "fact" and item.label
                ))
                logger.info(
                    f"[KnowledgeBaseBuilder] 对话 {i + 1}/{n_total} ({dialogue_id}) "
                    f"提取结果 — 槽位 {n_s} 个，意图 {n_i} 个，事实 {n_f} 个"
                )

                # 立即合成并融合
                try:
                    schema_part = _synthesize_per_turn(per_turn)
                    if schema_part is not None:
                        _merge_incremental(f"{i + 1}/{n_total}", schema_part)
                except Exception as exc:
                    logger.warning(
                        f"[KnowledgeBaseBuilder] 对话 {dialogue_id} schema 合成失败，跳过: {exc}"
                    )

        else:
            # ── 并行路径（workers > 1）──
            # 多线程并行提取各对话；每条提取完成后，立即交给专用的合并线程串行执行
            # 合成（LLM 调用）和融合，确保提取和合成互不阻塞。
            def _extract(
                args: Tuple[int, Dict[str, Any]]
            ) -> Tuple[int, Optional[List[Any]]]:
                idx, dlg = args
                dialogue_id = dlg.get("session_id", f"dlg_{idx}")
                logger.info(
                    f"[KnowledgeBaseBuilder] 处理对话 {idx + 1}/{n_total} ({dialogue_id})"
                )
                try:
                    per_turn = discoverer.extract_per_turn(dlg)
                    n_slots = len(set(
                        item.label for _, _, _, items in per_turn
                        for item in items
                        if item.extraction_class == "slot_value" and item.label
                    ))
                    n_intents = len(set(
                        item.label for _, _, _, items in per_turn
                        for item in items
                        if item.extraction_class == "intent" and item.label
                    ))
                    n_facts = len(set(
                        item.label for _, _, _, items in per_turn
                        for item in items
                        if item.extraction_class == "fact" and item.label
                    ))
                    logger.info(
                        f"[KnowledgeBaseBuilder] 对话 {idx + 1}/{n_total} ({dialogue_id}) "
                        f"提取完成 — 槽位 {n_slots} 个，意图 {n_intents} 个，事实 {n_facts} 个"
                    )
                    return idx, per_turn
                except Exception as exc:
                    logger.warning(
                        f"[KnowledgeBaseBuilder] 对话 {dialogue_id} 提取失败，跳过: {exc}"
                    )
                    return idx, None

            per_dialogue_turns_dict: Dict[int, List[Any]] = {}
            n_completed: int = 0

            # 专用合并线程：接收提取结果，串行执行合成（LLM 调用）和 schema 融合。
            # 使用 None 作为哨兵值通知线程退出。
            merge_task_queue: queue.Queue = queue.Queue()

            def _merge_worker() -> None:
                """合并线程主循环：逐条处理提取结果，调用 LLM 合成并融合。"""
                while True:
                    task = merge_task_queue.get()
                    try:
                        if task is None:
                            return
                        seq_label, per_turn_data, dlg_id = task
                        try:
                            schema_part = _synthesize_per_turn(per_turn_data)
                            if schema_part is not None:
                                _merge_incremental(seq_label, schema_part)
                        except Exception as exc:
                            logger.warning(
                                f"[KnowledgeBaseBuilder] 对话 {dlg_id} schema 合成失败，跳过: {exc}"
                            )
                    finally:
                        merge_task_queue.task_done()

            merge_thread = threading.Thread(target=_merge_worker, daemon=True)
            merge_thread.start()

            try:
                with ThreadPoolExecutor(max_workers=self.workers) as pool:
                    futures = {
                        pool.submit(_extract, (idx, dlg)): idx
                        for idx, dlg in enumerate(normalized)
                    }
                    # 每条提取完成后立即累积计数器，并投递到合并队列
                    for future in as_completed(futures):
                        idx, per_turn = future.result()
                        n_completed += 1
                        per_dialogue_turns_dict[idx] = per_turn if per_turn is not None else []

                        if per_turn is None:
                            continue

                        _accumulate_items(per_turn)

                        dialogue_id_p = normalized[idx].get("session_id", f"dlg_{idx}")
                        merge_task_queue.put(
                            (f"{n_completed}/{n_total} (dlg {dialogue_id_p})", per_turn, dialogue_id_p)
                        )
            finally:
                # 发送哨兵值，等待合并线程处理完所有剩余任务后退出
                merge_task_queue.put(None)
                merge_thread.join()

            # 按原始顺序重建 per_dialogue_turns
            per_dialogue_turns = [
                per_dialogue_turns_dict.get(i, [])
                for i in range(n_total)
            ]

        # ── 更新统计属性（供调用方展示）──
        self.last_slot_counter = global_slot_counter
        self.last_intent_counter = global_intent_counter
        self.last_fact_counter = global_fact_counter
        self.last_discovery_turns = per_dialogue_turns

        logger.info(
            f"[KnowledgeBaseBuilder] 发现阶段完成 — "
            f"槽位类型 {len(global_slot_counter)} 个，意图类型 {len(global_intent_counter)} 个，"
            f"事实类型 {len(global_fact_counter)} 个"
        )

        # ── Step 2: 精炼（消除跨对话产生的相似/重复槽位和意图）──
        if accumulated_schema is None:
            schema_dict = _fill_schema_defaults(
                {"service_name": re.sub(r"\s+", "_", self.scene_name)},
                scene_name=self.scene_name,
            )
        elif n_merged >= 2:
            pre_slots = len(accumulated_schema.get("slots", []))
            pre_intents = len(accumulated_schema.get("intents", []))
            print(f"  精炼前: {pre_slots} 个槽位，{pre_intents} 个意图")
            schema_dict = synthesizer.refine(
                schema_dict=accumulated_schema,
                scene_name=self.scene_name,
                scene_description=self.scene_description,
                n_dialogues=len(normalized),
            )
            post_slots = len(schema_dict.get("slots", []))
            post_intents = len(schema_dict.get("intents", []))
            print(f"  精炼后: {post_slots} 个槽位，{post_intents} 个意图")
            if self.verbose:
                _print_schema_brief("融合/整理后结果（精炼去重后）:", schema_dict)
        else:
            schema_dict = accumulated_schema

        # 深度精炼：补全 possible_values、required_slots / optional_slots / result_slots
        if schema_dict and (global_slot_samples or global_intent_samples):
            pre_polish_slots = len(schema_dict.get("slots", []))
            pre_polish_intents = len(schema_dict.get("intents", []))
            print(f"  深度精炼前: {pre_polish_slots} 个槽位，{pre_polish_intents} 个意图")
            schema_dict = synthesizer.polish(
                schema_dict=schema_dict,
                scene_name=self.scene_name,
                scene_description=self.scene_description,
                slot_sample_values=global_slot_samples,
                intent_sample_descs=global_intent_samples,
                n_dialogues=len(normalized),
                dialogue_snippets=_format_dialogue_snippets(normalized),
            )
            post_polish_slots = len(schema_dict.get("slots", []))
            post_polish_intents = len(schema_dict.get("intents", []))
            print(f"  深度精炼后: {post_polish_slots} 个槽位，{post_polish_intents} 个意图")
            if self.verbose:
                _print_schema_brief("深度精炼后最终结果:", schema_dict)

        logger.info(
            f"[KnowledgeBaseBuilder] ✓ schema 合并完成 — "
            f"{len(schema_dict.get('slots', []))} 个槽位，"
            f"{len(schema_dict.get('intents', []))} 个意图"
        )

        # ── Step 3: 转换为 SGD 对话格式 ──
        service_name = schema_dict.get("service_name", self.scene_name)
        sgd_dialogues = []
        for dlg_idx, (dlg, per_turn) in enumerate(zip(normalized, per_dialogue_turns)):
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

        # 写入 discovery_raw.json（以知识为主体的提取结果，含 langextract 溯源信息）
        # 格式：按 extraction_class（intent/slot_value/fact）和 label 聚合，每条知识附带
        # 来源对话、轮次、说话人、话语及 provenance 溯源字符串。
        if self.last_discovery_turns:
            # 按 (extraction_class, label) 聚合所有出现记录
            knowledge_index: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
            for sgd_dlg, per_turn in zip(sgd_dialogues, self.last_discovery_turns):
                dialogue_id = sgd_dlg.get("dialogue_id", "")
                for turn_idx, speaker, utterance, items in per_turn:
                    for item in items:
                        if not item.label:
                            continue
                        key = (item.extraction_class, item.label)
                        knowledge_index[key].append(
                            {
                                "value": item.value,
                                "provenance": item.provenance,
                                "dialogue_id": dialogue_id,
                                "turn_idx": turn_idx,
                                "speaker": speaker,
                                "utterance": utterance,
                            }
                        )

            # 按 extraction_class 排序输出，类内按出现次数降序
            sorted_keys = sorted(
                knowledge_index.keys(),
                key=lambda k: (_DISCOVERY_CLASS_ORDER.get(k[0], 9), -len(knowledge_index[k])),
            )
            raw_records = [
                {
                    "extraction_class": ec,
                    "label": label,
                    "total_occurrences": len(knowledge_index[(ec, label)]),
                    "occurrences": knowledge_index[(ec, label)],
                }
                for ec, label in sorted_keys
            ]

            raw_path = output_dir / "discovery_raw.json"
            raw_path.write_text(
                json.dumps(raw_records, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info(
                f"[KnowledgeBaseBuilder] discovery_raw.json 已写入: {raw_path} "
                f"（{len(raw_records)} 条知识条目）"
            )

        # 写入 conversion_summary.json
        final_schema_slots = [s["name"] for s in schema_dict.get("slots", [])]
        final_schema_intents = [i["name"] for i in schema_dict.get("intents", [])]
        summary = {
            "output_dir": str(output_dir),
            "dialogues": len(sgd_dialogues),
            "turns": total_turns,
            "failed": 0,
            "dialogue_files": len(dialogue_files),
            "services": [service_name],
            "converted_at": datetime.datetime.now().isoformat(timespec="seconds"),
            # 最终 schema 中的槽位和意图数量（经过精炼/深度精炼后的结果，与 schema.json 一致）
            "schema_slot_count": len(final_schema_slots),
            "schema_intent_count": len(final_schema_intents),
            # 发现阶段原始提取的不同标签数量（提取-合并前的 raw 数据，通常多于最终 schema 数量）
            "raw_discovery_slot_count": len(self.last_slot_counter),
            "raw_discovery_intent_count": len(self.last_intent_counter),
            "raw_discovery_fact_count": len(self.last_fact_counter),
            "schema_coverage": {
                "schema_slots": final_schema_slots,
                "schema_intents": final_schema_intents,
                "extracted_slots": list(self.last_slot_counter.keys()),
                "extracted_intents": list(self.last_intent_counter.keys()),
                "extracted_facts": list(self.last_fact_counter.keys()),
            },
        }
        summary_path = output_dir / "conversion_summary.json"
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(
            f"[KnowledgeBaseBuilder] 数据集保存完成 → {output_dir} "
            f"（schema: {len(final_schema_slots)} 个槽位，{len(final_schema_intents)} 个意图；"
            f"{len(sgd_dialogues)} 条对话，{total_turns} 轮）"
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

    def _build_schema_from_dialogues(
        self,
        normalized_dialogues: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], Counter, Counter]:
        """
        逐条对话执行发现 + 合成，最终合并所有对话的 schema。

        每条对话独立处理（不跨对话累积槽位），避免因汇总数据过多导致
        LLM 输出被截断。各对话的槽位/意图计数仅在该对话范围内有效，
        合成后通过名称去重合并为统一 schema。

        返回
        ----
        (schema_dict, global_slot_counter, global_intent_counter)

        - schema_dict: 合并后的 SGD schema
        - global_slot_counter: 全局槽位统计（供展示/调试）
        - global_intent_counter: 全局意图统计（供展示/调试）
        """
        discoverer = GenericDialogueDiscoverer(
            llm_client=self._get_llm(),
            scene_name=self.scene_name,
            context_window=self.context_window,
        )
        synthesizer = SchemaSynthesizer(llm_client=self._get_llm())

        # 逐条对话增量融合（替代原先收集 schema_parts 后一次性批量合并的方式）
        accumulated_schema: Optional[Dict[str, Any]] = None  # 历史累积 schema
        n_merged: int = 0  # 已融合进 accumulated_schema 的对话数
        global_slot_counter: Counter = Counter()
        global_intent_counter: Counter = Counter()
        global_slot_samples: Dict[str, List[str]] = {}
        global_intent_samples: Dict[str, List[str]] = {}

        for i, dlg in enumerate(normalized_dialogues):
            dialogue_id = dlg.get("session_id", f"dlg_{i}")
            logger.info(
                f"[KnowledgeBaseBuilder] 发现对话 {i + 1}/{len(normalized_dialogues)} "
                f"({dialogue_id})"
            )

            try:
                items = discoverer.extract(dlg)
            except Exception as exc:
                logger.warning(
                    f"[KnowledgeBaseBuilder] 对话 {dialogue_id} 提取失败，跳过: {exc}"
                )
                continue

            # 构建本对话的局部计数器（不与其他对话混合）
            local_slot_counter: Counter = Counter()
            local_intent_counter: Counter = Counter()
            local_slot_samples: Dict[str, List[str]] = {}
            local_intent_samples: Dict[str, List[str]] = {}

            for item in items:
                if item.extraction_class == "slot_value" and item.label:
                    local_slot_counter[item.label] += 1
                    samples = local_slot_samples.setdefault(item.label, [])
                    if item.value and len(samples) < 5 and item.value not in samples:
                        samples.append(item.value)
                elif item.extraction_class == "intent" and item.label:
                    local_intent_counter[item.label] += 1
                    descs = local_intent_samples.setdefault(item.label, [])
                    if item.value and len(descs) < 3 and item.value not in descs:
                        descs.append(item.value)

            global_slot_counter.update(local_slot_counter)
            global_intent_counter.update(local_intent_counter)
            # 跨对话累积槽位/意图样本值，供后续深度精炼使用
            for label, vals in local_slot_samples.items():
                existing = global_slot_samples.setdefault(label, [])
                for v in vals:
                    if v not in existing and len(existing) < 8:
                        existing.append(v)
            for label, descs in local_intent_samples.items():
                existing = global_intent_samples.setdefault(label, [])
                for d in descs:
                    if d not in existing and len(existing) < 5:
                        existing.append(d)

            # 提取结果摘要（每通对话均输出，供监控进度使用）
            logger.info(
                f"[KnowledgeBaseBuilder] 对话 {i + 1}/{len(normalized_dialogues)} ({dialogue_id}) "
                f"提取结果 — 槽位 {len(local_slot_counter)} 个，"
                f"意图 {len(local_intent_counter)} 个"
            )

            if local_slot_counter or local_intent_counter:
                try:
                    schema_part = synthesizer.synthesize(
                        scene_name=self.scene_name,
                        scene_description=self.scene_description,
                        slot_counter=local_slot_counter,
                        intent_counter=local_intent_counter,
                        slot_sample_values=local_slot_samples,
                        intent_sample_descs=local_intent_samples,
                        n_dialogues=1,
                    )
                    # 增量融合：将本次合成结果并入历史累积 schema
                    if accumulated_schema is None:
                        accumulated_schema = schema_part
                        if self.verbose:
                            _print_schema_brief(
                                f"对话 {i + 1}/{len(normalized_dialogues)} ({dialogue_id}) 合并结果:",
                                schema_part,
                            )
                    else:
                        if self.verbose:
                            _print_schema_brief(
                                f"对话 {i + 1}/{len(normalized_dialogues)} ({dialogue_id}) 合并结果:",
                                schema_part,
                            )
                        prev_n_slots = len(accumulated_schema.get("slots", []))
                        prev_n_intents = len(accumulated_schema.get("intents", []))
                        new_merged = _merge_service_list([accumulated_schema, schema_part])
                        if new_merged is not None:
                            new_merged = _fill_schema_defaults(new_merged, scene_name=self.scene_name)
                            # 安全保障：融合只能增长不能缩减
                            if (len(new_merged.get("slots", [])) < prev_n_slots or
                                    len(new_merged.get("intents", [])) < prev_n_intents):
                                logger.warning(
                                    f"[KnowledgeBaseBuilder] 对话 {dialogue_id} 融合后条目异常减少，"
                                    f"执行恢复合并"
                                )
                                restored = _merge_service_list([new_merged, accumulated_schema])
                                if restored is not None:
                                    new_merged = _fill_schema_defaults(
                                        restored, scene_name=self.scene_name
                                    )
                            accumulated_schema = new_merged
                    n_merged += 1
                    acc_n_slots = len(accumulated_schema.get("slots", []))
                    acc_n_intents = len(accumulated_schema.get("intents", []))
                    logger.info(
                        f"[KnowledgeBaseBuilder] 对话 {i + 1}/{len(normalized_dialogues)} ({dialogue_id}) "
                        f"融合后累积 — 槽位 {acc_n_slots} 个，意图 {acc_n_intents} 个"
                        f"（已融合 {n_merged} 条对话）"
                    )
                    print(
                        f"  [{i + 1}/{len(normalized_dialogues)}] 合并累积: "
                        f"{acc_n_slots} 个槽位，{acc_n_intents} 个意图"
                        f"（已融合 {n_merged} 条对话）"
                    )
                    if self.verbose:
                        _print_schema_brief(
                            f"对话 {i + 1}/{len(normalized_dialogues)} ({dialogue_id}) 融合后累积:",
                            accumulated_schema,
                        )
                except Exception as exc:
                    logger.warning(
                        f"[KnowledgeBaseBuilder] 对话 {dialogue_id} schema 合成失败，跳过: {exc}"
                    )

        logger.info(
            f"[KnowledgeBaseBuilder] 发现阶段完成 — "
            f"槽位类型 {len(global_slot_counter)} 个，意图类型 {len(global_intent_counter)} 个"
        )

        if accumulated_schema is None:
            schema_dict: Dict[str, Any] = _fill_schema_defaults(
                {"service_name": re.sub(r"\s+", "_", self.scene_name)},
                scene_name=self.scene_name,
            )
        elif n_merged >= 2:
            # 精炼：消除跨对话产生的相似/重复槽位和意图
            pre_slots = len(accumulated_schema.get("slots", []))
            pre_intents = len(accumulated_schema.get("intents", []))
            print(f"  精炼前: {pre_slots} 个槽位，{pre_intents} 个意图")
            schema_dict = synthesizer.refine(
                schema_dict=accumulated_schema,
                scene_name=self.scene_name,
                scene_description=self.scene_description,
                n_dialogues=len(normalized_dialogues),
            )
            post_slots = len(schema_dict.get("slots", []))
            post_intents = len(schema_dict.get("intents", []))
            print(f"  精炼后: {post_slots} 个槽位，{post_intents} 个意图")
            if self.verbose:
                _print_schema_brief("整理后最终结果（精炼去重后）:", schema_dict)
        else:
            schema_dict = accumulated_schema

        # 深度精炼：补全 possible_values、required_slots / optional_slots / result_slots
        if schema_dict and (global_slot_samples or global_intent_samples):
            pre_polish_slots = len(schema_dict.get("slots", []))
            pre_polish_intents = len(schema_dict.get("intents", []))
            print(f"  深度精炼前: {pre_polish_slots} 个槽位，{pre_polish_intents} 个意图")
            schema_dict = synthesizer.polish(
                schema_dict=schema_dict,
                scene_name=self.scene_name,
                scene_description=self.scene_description,
                slot_sample_values=global_slot_samples,
                intent_sample_descs=global_intent_samples,
                n_dialogues=len(normalized_dialogues),
                dialogue_snippets=_format_dialogue_snippets(normalized_dialogues),
            )
            post_polish_slots = len(schema_dict.get("slots", []))
            post_polish_intents = len(schema_dict.get("intents", []))
            print(f"  深度精炼后: {post_polish_slots} 个槽位，{post_polish_intents} 个意图")
            if self.verbose:
                _print_schema_brief("深度精炼后最终结果:", schema_dict)

        logger.info(
            f"[KnowledgeBaseBuilder] ✓ schema 完成 — "
            f"{len(schema_dict.get('slots', []))} 个槽位，"
            f"{len(schema_dict.get('intents', []))} 个意图"
        )
        return schema_dict, global_slot_counter, global_intent_counter

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
