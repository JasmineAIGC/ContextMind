"""
ContextMind - 专业的上下文优化框架 v7.3

完全通用化的上下文工程框架，支持任意对话场景

核心模块：
- InputPreprocessor: 输入预处理
- MemoryBank: 长期记忆管理
- ContextCompressor: 上下文压缩
- ContextReorderer: 上下文重排序
- PostProcessor: 输出后处理
- ConversationSummarizer: 对话摘要
- KVCacheManager: KV缓存管理

v7.3 新增功能 - 模块化结构与代码质量：
{
    from contextmind import ContextMind, registry
    
    # 简易集成API
    cm = ContextMind()
    context = await cm.prepare_context(user_input, session_id)
    
    # 插件注册中心
    print(registry.list_extractors())  # ['rule_based', 'llm_entity', 'importance']
    print(registry.list_retrievers())  # ['semantic', 'hybrid', 'locator']
}

架构设计 (v7.0 - 纯上下文工程):
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
- ✨ 模块化结构：将 models.py 拆分为 types、data_models、configs、logger
- ✨ 引擎重组：将 engine.py 移至顶层以便更好访问
- ✨ 代码质量：改进组织结构和可维护性
- ✨ 日志工具：在 utils/ 中提供专用日志模块
- ✨ 清晰导入：改进导入组织结构并保持向后兼容性
- ✨ 增强可观测性：改进日志结构
"""

# 核心框架组件
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
    # 日志
    ContextMindLogger,
    LogLevel,
    get_logger,
    setup_logging,
    set_global_log_level,
    get_global_log_level,
    INFO,
    DEBUG,
)

# 流水线组件 (5步处理流程 - v7.3)
from .pipeline import (
    Preprocessor,
    ContextRetriever,
    ContextCompressor,
    ContextReorderer,
    ResponseHandler,
    BaseSummarizer,
    LLMBasedSummarizer,
)

# 记忆库模块
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

# 向后兼容性别名
registry = PluginRegistry()
ContextMind = ContextMindConfig
ContextEngine = ContextMindEngine
InputPreprocessor = Preprocessor
ConversationSummarizer = LLMBasedSummarizer

__all__ = [
    # 简易集成API
    "ContextMind",
    "ContextMindConfig",
    
    # 插件系统
    "registry",
    "PluginRegistry",
    
    # 核心引擎
    "ContextEngine",
    "ContextMindEngine",
    
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
    
    # 日志系统
    "ContextMindLogger",
    "LogLevel",
    "get_logger",
    "setup_logging",
    "set_global_log_level",
    "get_global_log_level",
    "INFO",
    "DEBUG",
    
    # 流水线 (5步处理流程 - v7.3)
    "InputPreprocessor",      # 向后兼容性
    "Preprocessor",           # 步骤 1
    "ContextRetriever",       # 步骤 2
    "ContextCompressor",      # 步骤 3
    "ContextReorderer",       # 步骤 4
    "ResponseHandler",        # 步骤 5 (v7.3)
    
    # 支持组件
    "BaseSummarizer",
    "LLMBasedSummarizer",
    "ConversationSummarizer",  # 向后兼容性
    
    # 记忆库
    "MemoryBank",
    "SessionManager",
    "LLMBasedExtractor",
    "SemanticSearchRetriever",
    "SimpleUpdater",
    
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

__version__ = "7.3.0"  # 当前版本 - 模块化结构与代码质量
