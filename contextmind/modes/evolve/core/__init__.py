"""核心框架组件"""

from ..engine import EvolveEngine
from .registry import PluginRegistry, registry

# 从模块化子包导入
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

from contextmind.infra.logger import (
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
    # 类型枚举
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
    # 配置数据类
    "ExtractionConfig",
    "RetrievalConfig",
    "SummarizationConfig",
    "CompressionConfig",
    "MemorySystemConfig",
    "DEFAULT_MEMORY_CONFIG",
    # 日志工具
    "EvolveLogger",
    "LogLevel",
    "get_logger",
    "setup_logging",
    "set_global_log_level",
    "get_global_log_level",
    "INFO",
    "DEBUG",
    # 策略基类
    "ExtractionStrategy",
    "RetrievalStrategy",
    "IntegrationStrategy",
    "OptimizationStrategy",
    "CompressionStrategy",
    "RerankingStrategy",
]

