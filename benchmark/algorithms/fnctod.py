"""
FnCTOD (Function-based TOD) 算法评测模块

槽位级别指标计算逻辑与 DST 评测模块完全一致，统一由 SlotBasedEvaluator 提供。
"""

from .base import SlotMetrics, SlotBasedEvaluator



class FnCTODEvaluator(SlotBasedEvaluator):
    """FnCTOD 评测器（继承 SlotBasedEvaluator，复用槽位级别指标计算逻辑）。"""
