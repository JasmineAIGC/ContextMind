"""
ContextMind v7.0 数据模型

Context Engineering 框架的最小化数据类定义

此文件保持向后兼容性，所有类型现在从 core 模块导入
"""

# Re-export all types from core for backward compatibility
from .core.models import (
    MessageRole,
    Message,
    ContextSource,
    ContextItem,
    ContextResult,
    ProcessedContext,
    MemoryNote,
    Chunk,
    ContextState,
    RetrievalConfig,
    ExtractionConfig,
    CompressionConfig,
    SummarizationConfig,
    MemorySystemConfig,
    DEFAULT_MEMORY_CONFIG,
    LogLevel,
    ContextMindLogger,
    set_global_log_level,
    get_global_log_level,
    get_logger,
    setup_logging,
    INFO,
    DEBUG,
)

from .core.types import (
    KnowledgeType,
    MemoryType,
    EmbeddingInfo,
    ScoreInfo,
    VersionRecord,
    Knowledge,
)

__all__ = [
    # Message types
    "MessageRole",
    "Message",
    # Knowledge types
    "KnowledgeType",
    "MemoryType",
    "EmbeddingInfo",
    "ScoreInfo",
    "VersionRecord",
    "Knowledge",
    # Context types
    "ContextSource",
    "ContextItem",
    "ContextResult",
    "ProcessedContext",
    # Memory types
    "MemoryNote",
    # Processing types
    "Chunk",
    "ContextState",
    # Config types
    "RetrievalConfig",
    "ExtractionConfig",
    "CompressionConfig",
    "SummarizationConfig",
    "MemorySystemConfig",
    "DEFAULT_MEMORY_CONFIG",
    # Logging
    "LogLevel",
    "ContextMindLogger",
    "set_global_log_level",
    "get_global_log_level",
    "get_logger",
    "setup_logging",
    "INFO",
    "DEBUG",
]
