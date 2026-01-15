"""
Foundation Layer - 基础支撑层

提供上下文工程所需的核心计算基础设施：
- TokenizerService: 统一的Token计数服务
- VectorClient: 向量数据库客户端
- CacheManager: 缓存管理器

这一层是整个框架的"地基"，确保计算的准确性和效率。
"""

from .tokenizer import TokenizerService, TokenizerType
from .vector_client import VectorClient, VectorSearchResult
from .cache import CacheManager, CacheEntry

__all__ = [
    # Tokenizer
    "TokenizerService",
    "TokenizerType",
    
    # Vector
    "VectorClient",
    "VectorSearchResult",
    
    # Cache
    "CacheManager",
    "CacheEntry",
]
