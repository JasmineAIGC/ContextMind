"""
ContextMind Core Module

Core data models, types, and configurations.
"""

from .models import (
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

from .types import (
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
    # Knowledge types
    "KnowledgeType",
    "MemoryType",
    "EmbeddingInfo",
    "ScoreInfo",
    "VersionRecord",
    "Knowledge",
]
