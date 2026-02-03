"""核心框架组件"""

# 不导入 EvolutionEngine，避免循环依赖
# from ..engine import EvolutionEngine
from .registry import PluginRegistry, registry
from .framework_config import Evolution as EvolutionFrameworkConfig

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

from utils.logger import (
    EvolutionLogger,
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
    "EvolutionEngine",
    "PluginRegistry",
    "registry",
    "EvolutionConfig",
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
    "EvolutionLogger",
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

