"""
Benchmark 算法评测器基类

所有算法评测器（DSTEvaluator、FnCTODEvaluator、PyTODEvaluator、EvolveEvaluator）
均继承自 BaseEvaluator，保证统一的接口契约。

接口契约：
- reset()            : 清空所有已收集的预测记录
- calculate_metrics(): 根据当前记录计算并返回指标对象
- metrics_to_dict()  : 将指标序列化为嵌套字典（适合 JSON 输出）

槽位类评测器（DSTEvaluator、FnCTODEvaluator）额外继承 SlotBasedEvaluator，
共享槽位精度/召回/F1/JGA 计算逻辑，避免重复代码。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List


class BaseMetrics(ABC):
    """所有算法评测指标数据类的公共接口。"""

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """将指标序列化为嵌套字典（适合 JSON 输出）。"""
        ...


class BaseEvaluator(ABC):
    """
    算法评测器抽象基类。

    子类必须实现 ``reset`` 和 ``calculate_metrics``。
    ``metrics_to_dict`` 基于 ``calculate_metrics`` 默认实现，无需重写。
    """

    @abstractmethod
    def reset(self) -> None:
        """清空所有已收集的预测记录，回到初始状态。"""
        ...

    @abstractmethod
    def calculate_metrics(self) -> BaseMetrics:
        """
        根据当前所有预测记录计算评测指标。

        Returns:
            该评测器对应的 Metrics 对象（实现 ``to_dict``）。
        """
        ...

    def metrics_to_dict(self) -> Dict[str, Any]:
        """将 calculate_metrics() 的结果序列化为字典（便于 JSON 导出）。"""
        return self.calculate_metrics().to_dict()


# ---------------------------------------------------------------------------
# 槽位类评测基础设施（DST 和 FnCTOD 共用）
# ---------------------------------------------------------------------------

@dataclass
class SlotMetrics(BaseMetrics):
    """
    槽位级别评测指标（DST 和 FnCTOD 共用）。

    DSTMetrics / FnCTODMetrics 是本类的类型别名，保持向后兼容。
    """

    slot_accuracy: float = 0.0
    slot_precision: float = 0.0
    slot_recall: float = 0.0
    slot_f1: float = 0.0
    joint_accuracy: float = 0.0
    joint_accuracy_strict: float = 0.0
    total_slots: int = 0
    correct_slots: int = 0
    total_turns: int = 0
    correct_turns: int = 0
    domain_metrics: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slot_level": {
                "accuracy": round(self.slot_accuracy, 4),
                "precision": round(self.slot_precision, 4),
                "recall": round(self.slot_recall, 4),
                "f1": round(self.slot_f1, 4),
            },
            "dialogue_state_level": {
                "joint_accuracy": round(self.joint_accuracy, 4),
                "joint_accuracy_strict": round(self.joint_accuracy_strict, 4),
            },
            "statistics": {
                "total_slots": self.total_slots,
                "correct_slots": self.correct_slots,
                "total_turns": self.total_turns,
                "correct_turns": self.correct_turns,
            },
            "domain_breakdown": self.domain_metrics,
        }


class SlotBasedEvaluator(BaseEvaluator):
    """
    槽位类评测器共用基类（DST 和 FnCTOD 的公共父类）。

    提供：
    - ``add_prediction()`` — 记录一轮预测结果
    - ``reset()``           — 清空记录
    - ``calculate_metrics()`` — 计算槽位/JGA 指标

    子类可覆盖 ``_make_empty_metrics()`` 以返回各自的 Metrics 子类实例。
    """

    def __init__(self) -> None:
        self._predictions: List[Dict] = []
        self._ground_truths: List[Dict] = []
        self._domains: List[str] = []

    def add_prediction(
        self,
        predicted: Dict[str, str],
        ground_truth: Dict[str, str],
        domain: str = "unknown",
    ) -> None:
        """记录一轮对话的预测结果与标注。"""
        self._predictions.append(predicted)
        self._ground_truths.append(ground_truth)
        self._domains.append(domain)

    def reset(self) -> None:
        self._predictions = []
        self._ground_truths = []
        self._domains = []

    def _make_empty_metrics(self) -> SlotMetrics:
        """返回空指标对象；子类可重写以返回特定子类实例。"""
        return SlotMetrics()

    def calculate_metrics(self) -> SlotMetrics:
        if not self._predictions:
            return self._make_empty_metrics()

        total_slots = 0
        correct_slots = 0
        total_turns = len(self._predictions)
        correct_turns = 0
        domain_stats: Dict[str, Dict[str, int]] = {}

        true_positives = 0
        false_positives = 0
        false_negatives = 0

        for pred, gt, domain in zip(self._predictions, self._ground_truths, self._domains):
            if domain not in domain_stats:
                domain_stats[domain] = {"total": 0, "correct": 0, "exact_match": 0, "turns": 0}

            domain_stats[domain]["turns"] += 1
            all_slots = set(pred.keys()) | set(gt.keys())
            turn_correct = True

            for slot in all_slots:
                total_slots += 1
                domain_stats[domain]["total"] += 1

                pred_raw = pred.get(slot)
                gt_raw = gt.get(slot)
                pred_val = str(pred_raw) if pred_raw is not None else ""
                gt_val = str(gt_raw) if gt_raw is not None else ""

                has_pred = slot in pred and pred_raw is not None
                has_gt = slot in gt and gt_raw is not None

                if pred_val == gt_val:
                    correct_slots += 1
                    domain_stats[domain]["correct"] += 1
                    if has_pred and has_gt:
                        true_positives += 1
                else:
                    turn_correct = False
                    if has_pred:
                        false_positives += 1
                    if has_gt:
                        false_negatives += 1

            if turn_correct:
                correct_turns += 1
                domain_stats[domain]["exact_match"] += 1

        slot_accuracy = correct_slots / total_slots if total_slots > 0 else 0.0
        joint_accuracy = correct_turns / total_turns if total_turns > 0 else 0.0

        denom_p = true_positives + false_positives
        denom_r = true_positives + false_negatives
        precision = true_positives / denom_p if denom_p > 0 else 0.0
        recall = true_positives / denom_r if denom_r > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        domain_metrics: Dict[str, Dict[str, float]] = {}
        for domain, stats in domain_stats.items():
            domain_metrics[domain] = {
                "slot_accuracy": round(stats["correct"] / stats["total"], 4) if stats["total"] > 0 else 0.0,
                "joint_accuracy": round(stats["exact_match"] / stats["turns"], 4) if stats["turns"] > 0 else 0.0,
                "total_turns": stats["turns"],
            }

        return SlotMetrics(
            slot_accuracy=slot_accuracy,
            slot_precision=precision,
            slot_recall=recall,
            slot_f1=f1,
            joint_accuracy=joint_accuracy,
            joint_accuracy_strict=joint_accuracy,
            total_slots=total_slots,
            correct_slots=correct_slots,
            total_turns=total_turns,
            correct_turns=correct_turns,
            domain_metrics=domain_metrics,
        )


__all__ = ["BaseMetrics", "BaseEvaluator", "SlotMetrics", "SlotBasedEvaluator"]
