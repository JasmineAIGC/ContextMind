"""核心框架组件"""

from ..engine import ContextEngine as ContextMindEngine
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

from ..utils.logger import (
    ContextMindLogger,
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

from .prompt_template import (
    PromptTemplate,
    TemplateSlot,
    DEFAULT_CHAT_TEMPLATE,
)

__all__ = [
    "ContextMindEngine",
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
    "ContextMindLogger",
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
    # Prompt Template
    "PromptTemplate",
    "TemplateSlot",
    "DEFAULT_CHAT_TEMPLATE",
]

