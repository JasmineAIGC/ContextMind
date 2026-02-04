"""核心框架组件"""

from ..engine import EvolveEngine
from .registry import PluginRegistry, registry
from .framework_config import ContextMind as ContextMindConfig

# Import from new modular structure
from .types import (
    KnowledgeType,
    MemoryType,
    MessageRole,
    ContextSource,
)

from .data_models import (
    Message,
    ContextItem,
    ContextResult,
    ProcessedContext,
    Knowledge,
    Chunk,
    ContextState,
    EmbeddingInfo,
    ScoreInfo,
    VersionRecord,
    MemoryNote,
)

from .configs import (
    ExtractionConfig,
    RetrievalConfig,
    SummarizationConfig,
    CompressionConfig,
    MemorySystemConfig,
    DEFAULT_MEMORY_CONFIG,
)

from lib.utils.logger import (
    EvolveLogger,
    LogLevel,
    get_logger,
    setup_logging,
    set_global_log_level,
    get_global_log_level,
    INFO,
    DEBUG,
)

from .strategies import (
    ExtractionStrategy,
    RetrievalStrategy,
    IntegrationStrategy,
    OptimizationStrategy,
    CompressionStrategy,
    RerankingStrategy,
)

__all__ = [
    "EvolveEngine",
    "PluginRegistry",
    "registry",
    "ContextMindConfig",
    # Types
    "KnowledgeType",
    "MemoryType",
    "MessageRole",
    "ContextSource",
    # 数据模型
    "Message",
    "ContextItem",
    "ContextResult",
    "ProcessedContext",
    "Knowledge",
    "Chunk",
    "ContextState",
    "EmbeddingInfo",
    "ScoreInfo",
    "VersionRecord",
    "MemoryNote",
    # Configs
    "ExtractionConfig",
    "RetrievalConfig",
    "SummarizationConfig",
    "CompressionConfig",
    "MemorySystemConfig",
    "DEFAULT_MEMORY_CONFIG",
    # Logger
    "EvolveLogger",
    "LogLevel",
    "get_logger",
    "setup_logging",
    "set_global_log_level",
    "get_global_log_level",
    "INFO",
    "DEBUG",
    # Strategies
    "ExtractionStrategy",
    "RetrievalStrategy",
    "IntegrationStrategy",
    "OptimizationStrategy",
    "CompressionStrategy",
    "RerankingStrategy",
]

