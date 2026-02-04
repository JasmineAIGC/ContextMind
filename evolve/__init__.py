"""
Evolve - 专业的上下文优化框架 v0.2.1

完全通用化的上下文工程框架，支持任意对话场景

核心模块：
- InputPreprocessor: 输入预处理
- MemoryBank: 长期记忆管理
- ContextCompressor: 上下文压缩
- ContextReorderer: 上下文重排序
- PostProcessor: 输出后处理
- ConversationSummarizer: 对话摘要
- KVCacheManager: KV缓存管理

v0.2.1 新增功能 - Utils模块独立化与增强DST：
{
    from evolve import ContextMind, registry
    
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
│  引擎层 (Engine Layer)                   │  ← EvolveEngine
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

v0.2.1 核心改进：
- ✨ Utils独立化：将utils模块移至根目录，完全不依赖contextmind/baseline
- ✨ 增强DST：完整的ACL 2023论文合规性实现
- ✨ 知识提取：新增知识提取能力，支持LLM驱动的信息抽取
- ✨ 代码优化：改进模块组织和导入结构

- ✨ 文档更新：完善架构和使用文档
"""

# 核心框架组件
from .core import (
    EvolveEngine,
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
    EvolveLogger,
    LogLevel,
    get_logger,
    setup_logging,
    set_global_log_level,
    get_global_log_level,
    INFO,
    DEBUG,
)

# 流水线组件 (5步处理流程 - v0.2.1)
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
    MemoryFitness,
    FitnessCalculator,
)

# 进化模块 (基于 AlphaEvolve/ThetaEvolve 思想)
from .evolution import (
    EvolutionaryMemoryUpdater,
    ObservationCollector,
    FeedbackCollector,
    ImplicitFeedbackAnalyzer,
)

# 别名
registry = PluginRegistry()
ContextMind = ContextMindConfig
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
    "EvolveEngine",
    
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
    "EvolveLogger",
    "LogLevel",
    "get_logger",
    "setup_logging",
    "set_global_log_level",
    "get_global_log_level",
    "INFO",
    "DEBUG",
    
    # 流水线 (5步处理流程 - v0.2.1)
    "InputPreprocessor",
    "Preprocessor",           # 步骤 1
    "ContextRetriever",       # 步骤 2
    "ContextCompressor",      # 步骤 3
    "ContextReorderer",       # 步骤 4
    "ResponseHandler",        # 步骤 5 (v0.2.1)
    
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

__version__ = "0.2.1"  # 当前版本 - Utils模块移至根目录，完全独立化
