"""
Benchmark — 对话系统评测框架

提供四种算法评测器、三个数据集适配器和共享评测组件的统一入口。

快速使用:
    from benchmark.evaluators import DSTEvaluator, FnCTODEvaluator, PyTODEvaluator, EvolveEvaluator
    from benchmark.datasets import TransferTODAdapter, RiSAWOZAdapter
    from benchmark.evaluators.utils import IntentEvaluator, IntentLabelLoader
"""

from .evaluators import (
    DSTMetrics, DSTEvaluator,
    FnCTODMetrics, FnCTODEvaluator,
    PyTODMetrics, PyTODEvaluator,
    EvolveMetrics, EvolveEvaluator,
)
from .datasets import TransferTODAdapter, RiSAWOZAdapter
from .evaluators.utils import IntentEvaluator, IntentLabelLoader, get_intent_label_loader

__all__ = [
    # 算法评测器
    "DSTMetrics", "DSTEvaluator",
    "FnCTODMetrics", "FnCTODEvaluator",
    "PyTODMetrics", "PyTODEvaluator",
    "EvolveMetrics", "EvolveEvaluator",
    # 数据集适配器
    "TransferTODAdapter",
    "RiSAWOZAdapter",
    # 共享组件
    "IntentEvaluator",
    "IntentLabelLoader",
    "get_intent_label_loader",
]
