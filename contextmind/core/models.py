"""
Core Data Models Module (v7.3 Compatibility Layer)

Backward compatibility module - imports from split modules.
For new code, import directly from types, data_models, configs, or utils.logger

This module maintains backward compatibility by re-exporting all components
from the new modular structure introduced in v7.3.
"""

# Import from new modular structure
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

from ..utils.logger import (
    LogLevel,
    ContextMindLogger,
    get_logger,
    setup_logging,
    set_global_log_level,
    get_global_log_level,
    INFO,
    DEBUG,
)

# Re-export all for backward compatibility
__all__ = [
    # Types
    "KnowledgeType",
    "MemoryType",
    "MessageRole",
    "ContextSource",
    # Data Models
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
    # Configs
    "RetrievalConfig",
    "ExtractionConfig",
    "CompressionConfig",
    "SummarizationConfig",
    "MemorySystemConfig",
    "DEFAULT_MEMORY_CONFIG",
    # Logger
    "LogLevel",
    "ContextMindLogger",
    "get_logger",
    "setup_logging",
    "set_global_log_level",
    "get_global_log_level",
    "INFO",
    "DEBUG",
]
