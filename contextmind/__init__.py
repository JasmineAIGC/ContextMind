"""
ContextMind - 专业的上下文优化框架 v6.0
ContextMind - Professional Context Optimization Framework v6.0

完全通用化的上下文工程框架，支持任意对话场景
Fully generalized context engineering framework supporting any dialogue scenario

核心模块 Core Modules：
- InputPreprocessor: 输入预处理 / Input preprocessing
- ContextRetriever: 统一检索（RAG） / Unified retrieval (RAG)
- MemoryBank: 长期记忆管理 / Long-term memory management
- ContextCompressor: 上下文压缩 / Context compression
- ContextReorderer: 上下文重排序 / Context reordering
- KnowledgeExtractor: 知识提取 / Knowledge extraction
- PostProcessor: 输出后处理 / Output post-processing  
- ConversationSummarizer: 对话摘要 / Conversation summarization
- KVCacheManager: KV缓存管理 / KV cache management

NEW in v6.0 - Plugin System:
Context{
    from contextmind import registry
    
    # List available plugins
    print(registry.list_extractors())  # ['rule_based', 'llm_entity', 'importance']
    print(registry.list_retrievers())  # ['semantic', 'hybrid', 'locator']
    
    # Get plugins
    extractor = registry.get_extractor('rule_based')
    retriever = registry.get_retriever('hybrid')
}

架构设计 (v6.0 - Modular Plugin Architecture):
┌─────────────────────────────────────────┐
│  应用层 (Application Layer)              │  ← examples/applications/
│  - 基于框架构建的具体应用                 │
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│  引擎层 (Engine Layer)                   │  ← ContextEngine
│  - 统一的高层API接口                      │
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│  流水线层 (Pipeline Layer)               │  ← pipeline/
│  - 数据流程编排和处理                     │
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│  策略层 (Strategy/Plugin Layer)          │  ← strategies/memory/
│  - 可插拔的算法实现 (Plugin System)       │  ← registry
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│  基础层 (Foundation)                     │
│  - 核心数据模型 (core/)                   │
│  - 工具函数 (utils/)                      │
│  - 适配器 (adapters/)                     │
└─────────────────────────────────────────┘

v6.0 核心改进：
- ✨ Plugin System: 统一的插件注册和发现机制
- ✨ Modular Architecture: 所有算法都可通过插件替换
- ✨ Easy Integration: 简化的API和插件registry
- ✨ Enhanced Observability: 改进的日志系统
- ✨ Code Cleanup: 移除冗余代码，提升可维护性
"""

# Plugin Registry (NEW in v6.0)
from .registry import registry, PluginRegistry

# Easy Integration API (NEW in v6.0)
from .config_api import ContextMind

# 核心引擎
from .engine import ContextEngine

# 核心层
from .models import (
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
from .models import (
    # 日志
    get_logger,
    setup_logging,
    INFO,
    DEBUG,
)

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
)

__all__ = [
    # Easy Integration API (NEW in v6.0)
    "ContextMind",
    
    # Plugin System (NEW in v6.0)
    "registry",
    "PluginRegistry",
    
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

__version__ = "6.0.0"  # 当前版本 Current version - Plugin System Added
