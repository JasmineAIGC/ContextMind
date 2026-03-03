"""工具模块的基础数据模型。"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class EmbeddingInfo:
    """嵌入向量信息，包含模型名称、向量及自动计算的维度。"""

    model: str
    vector: List[float]
    # Derived from vector length in __post_init__; not set by the caller.
    dimension: int = field(init=False)

    def __post_init__(self):
        self.dimension = len(self.vector) if self.vector else 0
