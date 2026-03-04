"""
Benchmark 数据集适配器基类

所有数据集适配器（TransferTODAdapter、RiSAWOZAdapter）均继承自
BaseDatasetAdapter，保证评测脚本可以统一方式驱动任意数据集。

接口契约：
- load_dialogue(dialogue_id)          : 按 ID 加载单条对话实例
- list_dialogue_ids(split, **kwargs)  : 列出指定 split 的所有对话 ID
- get_domain(dialogue_id)             : 返回对话所属领域名称
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List


class BaseDatasetAdapter(ABC):
    """
    数据集适配器抽象基类。

    所有适配器都必须实现以下三个方法，以保证评测 runner 可以对其进行统一遍历。
    """

    @abstractmethod
    def load_dialogue(self, dialogue_id: str) -> Any:
        """
        按 ID 加载单条对话实例。

        Args:
            dialogue_id: 数据集内唯一对话标识符。

        Returns:
            适配器专属的对话实例对象（如 ``DialogueInstance``）。
        """
        ...

    @abstractmethod
    def list_dialogue_ids(self, split: str = "test", **kwargs: Any) -> List[str]:
        """
        列出指定数据集划分中的所有对话 ID。

        Args:
            split: 数据集划分，如 ``"train"``、``"val"``、``"test"``。
            **kwargs: 适配器特定的过滤参数（如 ``domain``、``data_type``）。

        Returns:
            对话 ID 字符串列表。
        """
        ...

    @abstractmethod
    def get_domain(self, dialogue_id: str) -> str:
        """
        返回指定对话所属的领域名称。

        Args:
            dialogue_id: 对话 ID。

        Returns:
            领域名称字符串（如 ``"酒店"``、``"餐厅"``）。
        """
        ...


__all__ = ["BaseDatasetAdapter"]
