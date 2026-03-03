"""
核心数据模型模块 (兼容层)

对于新代码，请直接从 types、data_models、configs 或 utils.logger 导入。
"""

from .types import (
    KnowledgeType,
    MemoryType,
    MessageRole,
    ContextSource,
)

from .data_models import (
    EmbeddingInfo,
    ScoreInfo,
    VersionRecord,
    Message,
    ContextItem,
    ContextResult,
    ProcessedContext,
    MemoryNote,
    Chunk,
    ContextState,
    Knowledge,
)

from .configs import (
    RetrievalConfig,
    ExtractionConfig,
    CompressionConfig,
    SummarizationConfig,
    MemorySystemConfig,
    DEFAULT_MEMORY_CONFIG,
)

from contextmind.infra.logger import (
    LogLevel,
    EvolveLogger,
    get_logger,
    setup_logging,
    set_global_log_level,
    get_global_log_level,
    INFO,
    DEBUG,
)

__all__ = [
    "KnowledgeType",
    "MemoryType",
    "MessageRole",
    "ContextSource",
    "EmbeddingInfo",
    "ScoreInfo",
    "VersionRecord",
    "Message",
    "ContextItem",
    "ContextResult",
    "ProcessedContext",
    "MemoryNote",
    "Chunk",
    "ContextState",
    "Knowledge",
    "RetrievalConfig",
    "ExtractionConfig",
    "CompressionConfig",
    "SummarizationConfig",
    "MemorySystemConfig",
    "DEFAULT_MEMORY_CONFIG",
    "LogLevel",
    "EvolveLogger",
    "get_logger",
    "setup_logging",
    "set_global_log_level",
    "get_global_log_level",
    "INFO",
    "DEBUG",
]
