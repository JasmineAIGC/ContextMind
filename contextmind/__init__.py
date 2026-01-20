"""
ContextMind - 专业的上下文优化框架 v5.1
ContextMind - Professional Context Optimization Framework v5.1

清晰的模块化架构，每个模块职责单一，易于扩展
Clear modular architecture with single responsibility and easy extensibility

核心模块 Core Modules：
- InputPreprocessor: 输入预处理 / Input preprocessing
- ContextRetriever: 统一检索（RAG） / Unified retrieval (RAG)
- MemoryBank: 长期记忆管理 / Long-term memory management
- ContextCompressor: 上下文压缩 / Context compression
- ContextReorderer: 上下文重排序
- KnowledgeExtractor: 知识提取

架构设计 (v5.1 - 5层架构):
- 应用层：使用引擎的应用
- 适配器层：对话系统集成接口
- 引擎层：ContextEngine 统一接口
- 流水线层：核心处理模块
- 策略层：可插拔的策略实现
- 核心层：数据模型、配置、日志
- 工具层：工具和实用程序

v5.1 核心改进：
- 5层架构重构：清晰的职责划分
- 合并冗余模块：减少文件数量
- 优化导入路径：更直观的模块组织
"""

# 核心引擎
from .engine import ContextEngine

# 核心层
from .core import (
    # 数据模型
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
    # 配置
    ExtractionConfig,
    RetrievalConfig,
    SummarizationConfig,
    CompressionConfig,
    MemorySystemConfig,
    DEFAULT_MEMORY_CONFIG,
)

# 流水线层
from .pipeline import (
    InputPreprocessor,
    ContextRetriever,
    MemoryBank,
    ContextCompressor,
    ContextReorderer,
    KnowledgeExtractor,
    SessionManager,
)

# 客户端
from .client import Client, ClientConfig

# 策略
from .strategies import (
    # 基类
    RetrievalStrategy,
    IntegrationStrategy,
    OptimizationStrategy,
    ExtractionStrategy,
    # 检索策略
    KeywordRetrievalStrategy,
    VectorRetrievalStrategy,
    HybridRetrievalStrategy,
    # 整合策略
    SimpleIntegrationStrategy,
    PriorityIntegrationStrategy,
    # 优化策略
    CompressionStrategy,
    RerankingStrategy,
    # 提取策略
    RuleBasedExtractionStrategy,
    LLMExtractionStrategy,
)

# 适配器
from .adapters import (
    BaseAdapter,
    DialogContext,
    DialogMessage,
    OpenAIAdapter,
    LangChainAdapter,
    CustomAdapter,
    VectorClient,
    VectorSearchResult,
    CacheManager,
    CacheEntry,
)

# 工具
from .utils import (
    TokenizerService,
    TokenizerType,
    ContextTextBuilder,
    ContextFormatter,
    format_context_result,
    format_memory_cache,
    format_prompt_analysis,
    format_complete_prompt,
    ConversationSummarizer,
    SummarizedHistory,
    PerformanceMonitor,
    ContextMetrics,
    # 日志
    get_logger,
    setup_logging,
    INFO,
    DEBUG,
)

__all__ = [
    # 核心引擎
    "ContextEngine",
    
    # 核心层 - 数据模型
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
    
    # 核心层 - 配置
    "ExtractionConfig",
    "RetrievalConfig",
    "SummarizationConfig",
    "CompressionConfig",
    "MemorySystemConfig",
    "DEFAULT_MEMORY_CONFIG",
    
    # 核心层 - 日志
    "get_logger",
    "setup_logging",
    "INFO",
    "DEBUG",
    
    # 流水线层
    "InputPreprocessor",
    "ContextRetriever",
    "MemoryBank",
    "ContextCompressor",
    "ContextReorderer",
    "KnowledgeExtractor",
    "SessionManager",
    
    # 客户端
    "Client",
    "ClientConfig",
    
    # 策略基类
    "RetrievalStrategy",
    "IntegrationStrategy",
    "OptimizationStrategy",
    "ExtractionStrategy",
    
    # 检索策略
    "KeywordRetrievalStrategy",
    "VectorRetrievalStrategy",
    "HybridRetrievalStrategy",
    
    # 整合策略
    "SimpleIntegrationStrategy",
    "PriorityIntegrationStrategy",
    
    # 优化策略
    "CompressionStrategy",
    "RerankingStrategy",
    
    # 提取策略
    "RuleBasedExtractionStrategy",
    "LLMExtractionStrategy",
    
    # 适配器
    "BaseAdapter",
    "DialogContext",
    "DialogMessage",
    "OpenAIAdapter",
    "LangChainAdapter",
    "CustomAdapter",
    "VectorClient",
    "VectorSearchResult",
    "CacheManager",
    "CacheEntry",
    
    # 工具
    "TokenizerService",
    "TokenizerType",
    "ContextTextBuilder",
    "ContextFormatter",
    "format_context_result",
    "format_memory_cache",
    "format_prompt_analysis",
    "format_complete_prompt",
    "ConversationSummarizer",
    "SummarizedHistory",
    "PerformanceMonitor",
    "ContextMetrics",
]

__version__ = "5.1.0"  # 当前版本 Current version
