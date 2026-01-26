"""
ContextMind - 专业的上下文优化框架 v7.3
ContextMind - Professional Context Optimization Framework v7.3

完全通用化的上下文工程框架，支持任意对话场景
Fully generalized context engineering framework supporting any dialogue scenario

核心模块 Core Modules：
- InputPreprocessor: 输入预处理 / Input preprocessing
- MemoryBank: 长期记忆管理 / Long-term memory management
- ContextCompressor: 上下文压缩 / Context compression
- ContextReorderer: 上下文重排序 / Context reordering
- PostProcessor: 输出后处理 / Output post-processing  
- ConversationSummarizer: 对话摘要 / Conversation summarization
- KVCacheManager: KV缓存管理 / KV cache management

NEW in v7.3 - Modular Structure & Code Quality:
{
    from contextmind import ContextMind, registry
    
    # Easy integration API
    cm = ContextMind()
    context = await cm.prepare_context(user_input, session_id)
    
    # Plugin registry
    print(registry.list_extractors())  # ['rule_based', 'llm_entity', 'importance']
    print(registry.list_retrievers())  # ['semantic', 'hybrid', 'locator']
}

架构设计 (v7.0 - Pure Context Engineering):
┌─────────────────────────────────────────┐
│  应用层 (Application Layer)              │  ← demos/
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
│  策略层 (Strategy/Plugin Layer)          │  ← strategies/
│  - 可插拔的算法实现 (Plugin System)       │  ← registry
└─────────────────────────────────────────┘

v7.3 核心改进：
- ✨ Modular Structure: Split models.py into types, data_models, configs, logger
- ✨ Engine Reorganization: Moved engine.py to top level for better access
- ✨ Code Quality: Improved organization and maintainability
- ✨ Logger Utilities: Dedicated logger module in utils/
- ✨ Clean Imports: Better import organization with backward compatibility
- ✨ Enhanced Observability: Improved logging structure
"""

# Core Framework Components
from .core import (
    ContextMindEngine,
    PluginRegistry,
    ContextMindConfig,
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
    # Logging
    ContextMindLogger,
    LogLevel,
    get_logger,
    setup_logging,
    set_global_log_level,
    get_global_log_level,
    INFO,
    DEBUG,
)

# Pipeline Components (6-Step Processing)
from .pipeline import (
    Preprocessor,
    ContextRetriever,
    ContextCompressor,
    ContextReorderer,
    KVCacheManager,
    PostProcessor,
    BaseSummarizer,
    LLMBasedSummarizer,
    RuleBasedSummarizer,
)

# Memory Bank Module
from .memory import (
    MemoryBank,
    SessionManager,
    LLMBasedExtractor,
    SemanticSearchRetriever,
    SimpleUpdater,
    BaseExtractor,
    BaseRetriever,
    BaseUpdater,
)

# Backward compatibility aliases
registry = PluginRegistry()
ContextMind = ContextMindConfig
ContextEngine = ContextMindEngine
InputPreprocessor = Preprocessor
ConversationSummarizer = LLMBasedSummarizer

__all__ = [
    # Easy Integration API
    "ContextMind",
    "ContextMindConfig",
    
    # Plugin System
    "registry",
    "PluginRegistry",
    
    # Core Engine
    "ContextEngine",
    "ContextMindEngine",
    
    # Data Models
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
    
    # Configurations
    "ExtractionConfig",
    "RetrievalConfig",
    "SummarizationConfig",
    "CompressionConfig",
    "MemorySystemConfig",
    "DEFAULT_MEMORY_CONFIG",
    
    # Logging System
    "ContextMindLogger",
    "LogLevel",
    "get_logger",
    "setup_logging",
    "set_global_log_level",
    "get_global_log_level",
    "INFO",
    "DEBUG",
    
    # Pipeline (6 Steps)
    "InputPreprocessor",      # Backward compatibility
    "Preprocessor",           # Step 1
    "ContextRetriever",       # Step 2
    "ContextCompressor",      # Step 3
    "ContextReorderer",       # Step 4
    "KVCacheManager",         # Step 5
    "PostProcessor",          # Step 6
    
    # Supporting Components
    "BaseSummarizer",
    "LLMBasedSummarizer",
    "RuleBasedSummarizer",
    "ConversationSummarizer",  # Backward compatibility
    
    # Memory Bank
    "MemoryBank",
    "SessionManager",
    "LLMBasedExtractor",
    "SemanticSearchRetriever",
    "SimpleUpdater",
    
    # Strategy Base Classes
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

__version__ = "7.3.0"  # 当前版本 Current version - Modular Structure & Code Quality
