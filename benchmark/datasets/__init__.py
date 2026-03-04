"""
Benchmark 数据集适配器

将各数据集格式转换为统一的对话实例结构，供评测脚本使用。
"""

from .transfertod.adapter import TransferTODAdapter
from .risawoz.adapter import RiSAWOZAdapter

__all__ = [
    "TransferTODAdapter",
    "RiSAWOZAdapter",
]
