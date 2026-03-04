"""
FnCTOD (Function-based TOD) 算法评测模块

槽位级别指标计算逻辑与 DST 评测模块完全一致，统一由 SlotBasedEvaluator 提供。
"""

from .base import SlotMetrics, SlotBasedEvaluator

# 向后兼容别名（行为与 SlotMetrics 完全相同）
FnCTODMetrics = SlotMetrics


class FnCTODEvaluator(SlotBasedEvaluator):
    """FnCTOD 评测器（继承 SlotBasedEvaluator，复用槽位级别指标计算逻辑）。"""
