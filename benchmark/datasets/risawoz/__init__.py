"""
RiSAWOZ 数据集适配器包

将 RiSAWOZ 格式转换为标准化对话实例，支持 source-data、task2-DST 等多种子格式。
"""

from .adapter import RiSAWOZAdapter, RISAWOZ_FILE_MAPPINGS
from .label_parser import RiSAWOZLabel, RiSAWOZLabelParser
from .sgd_converter import RiSAWOZToSGDConverter

__all__ = [
    # 主适配器
    "RiSAWOZAdapter",
    "RISAWOZ_FILE_MAPPINGS",
    # 标签解析
    "RiSAWOZLabel",
    "RiSAWOZLabelParser",
    # 格式转换
    "RiSAWOZToSGDConverter",
]
