"""
Benchmark 算法评测器基类

所有算法评测器（DSTEvaluator、FnCTODEvaluator、PyTODEvaluator、EvolveEvaluator）
均继承自 BaseEvaluator，保证统一的接口契约。

接口契约：
- reset()            : 清空所有已收集的预测记录
- calculate_metrics(): 根据当前记录计算并返回指标对象
- metrics_to_dict()  : 将指标序列化为嵌套字典（适合 JSON 输出）
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


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


__all__ = ["BaseMetrics", "BaseEvaluator"]
