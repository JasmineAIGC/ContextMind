"""
Benchmark 数据集适配器

将各数据集格式转换为统一的对话实例结构，供评测脚本使用。

添加新数据集时：继承 BaseDatasetAdapter，并在此 __init__.py 中注册导出。
"""

from .base import BaseDatasetAdapter
from .transfertod.adapter import TransferTODAdapter
from .risawoz.adapter import RiSAWOZAdapter
from .anyihua.adapter import AnyihuaSGDAdapter, AnyihuaDialogue, AnyihuaTurn

__all__ = [
    "BaseDatasetAdapter",
    "TransferTODAdapter",
    "RiSAWOZAdapter",
    "AnyihuaSGDAdapter",
    "AnyihuaDialogue",
    "AnyihuaTurn",
]
