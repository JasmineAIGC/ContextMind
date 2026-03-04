"""
Benchmark 算法评测模块

提供四种算法评测器，每种评测器均遵循相同结构：
- Metrics 数据类（继承 BaseMetrics）：存储聚合指标
- Evaluator 类（继承 BaseEvaluator）：通过 add_* / calculate_metrics / reset 接口收集并计算指标

添加新评测器时：继承 BaseEvaluator + BaseMetrics，并在此 __init__.py 中注册导出。
"""

from .base import BaseMetrics, BaseEvaluator
from .dst import DSTMetrics, DSTEvaluator
from .fnctod import FnCTODMetrics, FnCTODEvaluator
from .pytod import PyTODMetrics, PyTODEvaluator
from .evolve import EvolveMetrics, EvolveEvaluator

__all__ = [
    # 基类
    "BaseMetrics",
    "BaseEvaluator",
    # DST — 对话状态追踪
    "DSTMetrics",
    "DSTEvaluator",
    # FnCTOD — 函数调用型 TOD
    "FnCTODMetrics",
    "FnCTODEvaluator",
    # PyTOD — 程序执行型 TOD
    "PyTODMetrics",
    "PyTODEvaluator",
    # Evolve — 进化式上下文优化
    "EvolveMetrics",
    "EvolveEvaluator",
]
