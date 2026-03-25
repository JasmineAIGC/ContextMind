"""
Evolve - 上下文优化框架

通用化的上下文工程框架，支持任意对话场景。

日志工具请直接从 ``contextmind.infra.logger`` 导入：

.. code-block:: python

    from contextmind.infra.logger import get_logger, setup_logging, LogLevel
"""

from .core import (
    EvolveEngine,
    PluginRegistry,
    Message,
    MessageRole,
    ContextItem,
    ContextSource,
    ContextResult,
    ProcessedContext,
    Knowledge,
    KnowledgeType,
    Chunk,
    ContextState,
    EmbeddingInfo,
    ExtractionConfig,
    RetrievalConfig,
    SummarizationConfig,
    CompressionConfig,
    MemorySystemConfig,
    DEFAULT_MEMORY_CONFIG,
    ExtractionStrategy,
    RetrievalStrategy,
    IntegrationStrategy,
    OptimizationStrategy,
    CompressionStrategy,
    RerankingStrategy,
)

from .pipeline import (
    Preprocessor,
    ContextRetriever,
    ContextCompressor,
    ContextReorderer,
    ResponseHandler,
    BaseSummarizer,
    LLMBasedSummarizer,
    ConversationSummarizer,
)

from .memory import (
    MemoryBank,
    SessionManager,
    LLMBasedExtractor,
    SemanticSearchRetriever,
    SimpleUpdater,
    BaseExtractor,
    BaseRetriever,
    BaseUpdater,
    MemoryFitness,
    FitnessCalculator,
)

from .evolution import (
    EvolutionaryMemoryUpdater,
    ObservationCollector,
    FeedbackCollector,
    ImplicitFeedbackAnalyzer,
)

registry = PluginRegistry()
InputPreprocessor = Preprocessor

from .factory import create_app_for_scenario
from .app import EvolveApplication


__all__ = [
    # 插件系统
    "registry",
    "PluginRegistry",

    # 核心引擎
    "EvolveEngine",

    # 应用层
    "EvolveApplication",

    # 工厂方法
    "create_app_for_scenario",

    # 数据模型
    "Message",
    "MessageRole",
    "ContextItem",
    "ContextSource",
    "ContextResult",
    "ProcessedContext",
    "Knowledge",
    "KnowledgeType",
    "Chunk",
    "ContextState",
    "EmbeddingInfo",

    # 配置
    "ExtractionConfig",
    "RetrievalConfig",
    "SummarizationConfig",
    "CompressionConfig",
    "MemorySystemConfig",
    "DEFAULT_MEMORY_CONFIG",

    # 流水线
    "InputPreprocessor",
    "Preprocessor",
    "ContextRetriever",
    "ContextCompressor",
    "ContextReorderer",
    "ResponseHandler",

    # 支持组件
    "BaseSummarizer",
    "LLMBasedSummarizer",
    "ConversationSummarizer",

    # 记忆库
    "MemoryBank",
    "SessionManager",
    "LLMBasedExtractor",
    "SemanticSearchRetriever",
    "SimpleUpdater",
    "MemoryFitness",
    "FitnessCalculator",

    # 进化模块
    "EvolutionaryMemoryUpdater",
    "ObservationCollector",
    "FeedbackCollector",
    "ImplicitFeedbackAnalyzer",

    # 策略基类
    "BaseExtractor",
    "BaseRetriever",
    "BaseUpdater",
    "ExtractionStrategy",
    "RetrievalStrategy",
    "IntegrationStrategy",
    "OptimizationStrategy",
    "CompressionStrategy",
    "RerankingStrategy",
]

__version__ = "0.3.0"
