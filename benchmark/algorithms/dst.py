"""
DST (Dialogue State Tracking) 算法评测模块

槽位级别指标计算逻辑与 FnCTOD 评测模块共用，统一由 SlotBasedEvaluator 提供。
"""

from .base import SlotMetrics, SlotBasedEvaluator



class DSTEvaluator(SlotBasedEvaluator):
    """DST 评测器（继承 SlotBasedEvaluator，复用槽位级别指标计算逻辑）。"""
