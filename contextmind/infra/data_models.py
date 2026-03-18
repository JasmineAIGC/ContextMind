"""工具模块的基础数据模型。"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class EmbeddingInfo:
    """嵌入向量信息，包含模型名称、向量及自动计算的维度。"""

    model: str
    vector: List[float]
    # 由 __post_init__ 根据向量长度自动推导，调用方无需传入。
    dimension: int = field(init=False)

    def __post_init__(self):
        self.dimension = len(self.vector) if self.vector else 0
