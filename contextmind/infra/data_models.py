"""
Utils Data Models - 工具模块的数据模型

这些数据模型是工具模块自包含的，不依赖其他模块。
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class EmbeddingInfo:
    """嵌入向量信息
    
    Attributes:
        model: 使用的模型名称
        vector: 嵌入向量
        dimension: 向量维度
    """
    model: str
    vector: List[float]
    dimension: int = field(init=False)
    
    def __post_init__(self):
        """自动计算维度"""
        self.dimension = len(self.vector) if self.vector else 0
