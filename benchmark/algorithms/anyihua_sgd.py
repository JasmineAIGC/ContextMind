"""
安逸花外呼 SGD 知识库提取质量评测模块（任务三：3.2 自动化评测）

评测 3 步 SGD 管道产出的知识质量，核心指标：

  1. 溯源完整率（Provenance Completeness）
     - 每个提取项（意图/槽位）是否有 char_interval（原文定位）
     - 对应 langextract 的 WordAligner 对齐结果

  2. 精确对齐率（Exact Alignment Rate）
     - 对齐状态为 match_exact 的占比（最高质量溯源）

  3. 槽位提取率（Slot Extraction Rate）
     - 每条对话平均提取到的槽位值数量

  4. 意图检测率（Intent Detection Rate）
     - 用户轮次中成功识别到具体意图（非 general_inquiry）的占比

  5. Schema 覆盖率（Schema Coverage）
     - 提取到的槽位名 / 意图名覆盖预定义 Schema 的比例

与 benchmark/algorithms/ 中其他评测器保持结构一致，
继承 BaseEvaluator / BaseMetrics。

典型使用::

    from benchmark.algorithms.anyihua_sgd import AnYiHuaSGDEvaluator

    evaluator = AnYiHuaSGDEvaluator(schema=schema)
    for dialogue in sgd_dialogues:
        evaluator.add_dialogue(dialogue)

    metrics = evaluator.calculate_metrics()
    print(metrics.to_dict())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from benchmark.algorithms.base import BaseEvaluator, BaseMetrics


# ---------------------------------------------------------------------------
# 指标数据类
# ---------------------------------------------------------------------------


@dataclass
class AnYiHuaSGDMetrics(BaseMetrics):
    """
    安逸花 SGD 知识库提取质量指标。

    溯源相关指标（provenance）直接对应 langextract WordAligner 的对齐结果：
      - provenance_completeness: 具有 char_interval 的提取项占比（任意对齐状态）
      - exact_alignment_rate:    对齐状态为 match_exact 的提取项占比

    schema_coverage 衡量提取结果对预定义 schema 的覆盖，
    用于评估管道是否能发现大多数已知意图和槽位。
    """

    # 溯源质量
    provenance_completeness: float = 0.0   # 有 char_interval 的提取项 %
    exact_alignment_rate: float = 0.0      # match_exact 提取项 %

    # 提取丰富度
    slot_extraction_rate: float = 0.0      # 每条对话平均提取到的槽位值数
    intent_detection_rate: float = 0.0     # 用户轮次中具体意图占比

    # Schema 覆盖
    schema_slot_coverage: float = 0.0      # 提取到的槽位名 / schema 总槽位名
    schema_intent_coverage: float = 0.0    # 提取到的意图名 / schema 总意图名

    # 统计信息
    total_dialogues: int = 0
    total_extractions: int = 0
    extractions_with_provenance: int = 0
    extractions_exact: int = 0
    total_slot_extractions: int = 0
    total_user_turns: int = 0
    user_turns_with_specific_intent: int = 0

    seen_slot_names: List[str] = field(default_factory=list)
    seen_intent_names: List[str] = field(default_factory=list)
    schema_slot_names: List[str] = field(default_factory=list)
    schema_intent_names: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provenance": {
                "provenance_completeness": round(self.provenance_completeness, 4),
                "exact_alignment_rate": round(self.exact_alignment_rate, 4),
            },
            "extraction": {
                "slot_extraction_rate": round(self.slot_extraction_rate, 4),
                "intent_detection_rate": round(self.intent_detection_rate, 4),
            },
            "schema_coverage": {
                "slot_coverage": round(self.schema_slot_coverage, 4),
                "intent_coverage": round(self.schema_intent_coverage, 4),
                "seen_slot_names": sorted(self.seen_slot_names),
                "seen_intent_names": sorted(self.seen_intent_names),
            },
            "statistics": {
                "total_dialogues": self.total_dialogues,
                "total_extractions": self.total_extractions,
                "extractions_with_provenance": self.extractions_with_provenance,
                "extractions_exact": self.extractions_exact,
                "total_slot_extractions": self.total_slot_extractions,
                "total_user_turns": self.total_user_turns,
                "user_turns_with_specific_intent": self.user_turns_with_specific_intent,
            },
        }


# ---------------------------------------------------------------------------
# 评测器
# ---------------------------------------------------------------------------


class AnYiHuaSGDEvaluator(BaseEvaluator):
    """
    安逸花外呼 SGD 知识库提取质量评测器。

    接收 ``build_sgd_dialogue_step3`` 产出的 SGD 对话字典，
    分析 ``metadata.langextract_example`` 中的提取结果，
    计算溯源完整率、对齐精度、提取丰富度和 Schema 覆盖率。

    参数:
        schema_slot_names:   预定义 Schema 的槽位名列表（用于计算 schema_coverage）
        schema_intent_names: 预定义 Schema 的意图名列表
    """

    def __init__(
        self,
        schema_slot_names: Optional[List[str]] = None,
        schema_intent_names: Optional[List[str]] = None,
    ) -> None:
        self._schema_slot_names: List[str] = schema_slot_names or []
        self._schema_intent_names: List[str] = schema_intent_names or []
        self._records: List[Dict[str, Any]] = []

    def add_dialogue(self, sgd_dialogue: Dict[str, Any]) -> None:
        """
        记录单条 SGD 对话的提取结果。

        参数:
            sgd_dialogue: ``build_sgd_dialogue_step3`` 返回的 SGD 对话字典，
                          必须含 ``metadata.langextract_example``。
        """
        metadata = sgd_dialogue.get("metadata", {})
        lx_example = metadata.get("langextract_example", {})
        extractions: List[Dict[str, Any]] = lx_example.get("extractions", [])
        turns: List[Dict[str, Any]] = sgd_dialogue.get("turns", [])

        # 统计溯源信息
        n_with_provenance = sum(
            1 for e in extractions if e.get("char_interval") is not None
        )
        n_exact = sum(
            1 for e in extractions
            if e.get("alignment_status") == "match_exact"
        )

        # 统计槽位提取
        slot_extractions = [e for e in extractions if e.get("extraction_class") == "slot_value"]
        seen_slots: Set[str] = {
            e["attributes"]["slot_name"]
            for e in slot_extractions
            if e.get("attributes") and e["attributes"].get("slot_name")
        }

        # 统计用户意图
        intent_extractions = [e for e in extractions if e.get("extraction_class") == "intent"]
        seen_intents: Set[str] = {
            e["attributes"]["intent_name"]
            for e in intent_extractions
            if e.get("attributes") and e["attributes"].get("intent_name")
        }

        # 统计用户轮次及具体意图覆盖
        user_turns = [t for t in turns if t.get("speaker") == "USER"]
        n_user_turns = len(user_turns)
        n_specific_intent = sum(
            1 for t in user_turns
            if t.get("frames")
            and t["frames"][0].get("state", {}).get("active_intent", "general_inquiry")
            not in ("general_inquiry", "NONE", None)
        )

        self._records.append({
            "n_extractions": len(extractions),
            "n_with_provenance": n_with_provenance,
            "n_exact": n_exact,
            "n_slot_extractions": len(slot_extractions),
            "n_user_turns": n_user_turns,
            "n_specific_intent": n_specific_intent,
            "seen_slots": seen_slots,
            "seen_intents": seen_intents,
        })

    def calculate_metrics(self) -> AnYiHuaSGDMetrics:
        """计算并返回聚合质量指标。"""
        if not self._records:
            return AnYiHuaSGDMetrics(
                schema_slot_names=list(self._schema_slot_names),
                schema_intent_names=list(self._schema_intent_names),
            )

        total_dialogues = len(self._records)
        total_extractions = sum(r["n_extractions"] for r in self._records)
        total_provenance = sum(r["n_with_provenance"] for r in self._records)
        total_exact = sum(r["n_exact"] for r in self._records)
        total_slots = sum(r["n_slot_extractions"] for r in self._records)
        total_user_turns = sum(r["n_user_turns"] for r in self._records)
        total_specific = sum(r["n_specific_intent"] for r in self._records)

        # 聚合所有见过的槽位和意图
        all_seen_slots: Set[str] = set()
        all_seen_intents: Set[str] = set()
        for r in self._records:
            all_seen_slots.update(r["seen_slots"])
            all_seen_intents.update(r["seen_intents"])

        # Schema 覆盖率
        schema_slot_names = list(self._schema_slot_names)
        schema_intent_names = list(self._schema_intent_names)
        slot_coverage = (
            len(all_seen_slots & set(schema_slot_names)) / len(schema_slot_names)
            if schema_slot_names
            else 0.0
        )
        intent_coverage = (
            len(all_seen_intents & set(schema_intent_names)) / len(schema_intent_names)
            if schema_intent_names
            else 0.0
        )

        return AnYiHuaSGDMetrics(
            provenance_completeness=(
                total_provenance / total_extractions if total_extractions else 0.0
            ),
            exact_alignment_rate=(
                total_exact / total_extractions if total_extractions else 0.0
            ),
            slot_extraction_rate=(
                total_slots / total_dialogues if total_dialogues else 0.0
            ),
            intent_detection_rate=(
                total_specific / total_user_turns if total_user_turns else 0.0
            ),
            schema_slot_coverage=slot_coverage,
            schema_intent_coverage=intent_coverage,
            total_dialogues=total_dialogues,
            total_extractions=total_extractions,
            extractions_with_provenance=total_provenance,
            extractions_exact=total_exact,
            total_slot_extractions=total_slots,
            total_user_turns=total_user_turns,
            user_turns_with_specific_intent=total_specific,
            seen_slot_names=sorted(all_seen_slots),
            seen_intent_names=sorted(all_seen_intents),
            schema_slot_names=schema_slot_names,
            schema_intent_names=schema_intent_names,
        )

    def reset(self) -> None:
        """清空已记录的评测数据。"""
        self._records = []
