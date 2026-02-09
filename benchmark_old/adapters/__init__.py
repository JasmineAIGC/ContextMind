"""
Benchmark 适配器模块

提供算法-数据集之间的适配层
"""

from .base_adapter import DatasetAdapter
from .dst_transfertod import DSTTransferTODAdapter
from .fnctod_transfertod import FnCTODTransferTODAdapter

# RiSAWOZ适配器（待实现）
# from .dst_risawoz import DSTRiSAWOZAdapter
# from .fnctod_risawoz import FnCTODRiSAWOZAdapter

__all__ = [
    'DatasetAdapter',
    'DSTTransferTODAdapter',
    'FnCTODTransferTODAdapter',
]
