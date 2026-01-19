"""
ContextMind核心模块 v4.0

清晰的模块化架构，每个模块职责单一：
- InputPreprocessor: 输入预处理
- ContextRetriever: 统一检索（RAG）
- MemoryBank: 长期记忆管理
- ContextCompressor: 上下文压缩
- ContextReorderer: 上下文重排序
- KnowledgeExtractor: 知识提取
"""

from .preprocessor import InputPreprocessor
from .retriever import ContextRetriever
from .memory_bank import MemoryBank
from .compressor import ContextCompressor
from .reorderer import ContextReorderer
from .extractor import KnowledgeExtractor

__all__ = [
    "InputPreprocessor",
    "ContextRetriever",
    "MemoryBank",
    "ContextCompressor",
    "ContextReorderer",
    "KnowledgeExtractor",
]
