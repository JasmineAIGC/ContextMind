"""核心框架组件

日志工具（get_logger、setup_logging 等）应直接从 ``contextmind.infra.logger`` 导入，
不通过此模块重新导出。
"""

from .engine import EvolveEngine
from .registry import PluginRegistry, registry

from .config import (
    KnowledgeType,
    MemoryType,
    MessageRole,
    ContextSource,
    ExtractionConfig,
    RetrievalConfig,
    SummarizationConfig,
    CompressionConfig,
    MemorySystemConfig,
    DEFAULT_MEMORY_CONFIG,
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
    # 策略基类
    "ExtractionStrategy",
    "RetrievalStrategy",
    "IntegrationStrategy",
    "OptimizationStrategy",
    "CompressionStrategy",
    "RerankingStrategy",
]
