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
    from contextmind.modes.evolve import EvolveEngine, registry
    
    # 核心引擎
    engine = EvolveEngine(llm_client=llm_client)
    
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

# 别名 - 统一命名风格
registry = PluginRegistry()
InputPreprocessor = Preprocessor
ConversationSummarizer = LLMBasedSummarizer
ResponseParser = ResponseHandler  # 统一Parser命名（虽然功能不同，但概念相似）
EvolveTracker = EvolveEngine  # 统一Tracker命名


def create_app_for_scenario(scenario_name: str, llm_client, scenario_config, app_name_prefix: str = "demo"):
    """
    为指定场景创建应用实例的工厂方法（通用化版本）
    
    这是Evolve模式的推荐初始化方式，与DST/FnCTOD的from_scenario()保持一致。
    现在使用场景注册表，支持动态添加新场景，无需修改代码。
    
    Args:
        scenario_name: 场景名称（支持中英文别名）
        llm_client: LLM客户端实例
        scenario_config: 场景配置对象
        app_name_prefix: 应用名称前缀（默认 "demo"）
        
    Returns:
        对应场景的Application实例
        
    Raises:
        ValueError: 如果场景未注册
        
    Example:
        # 使用内置场景
        from contextmind.modes.evolve import create_app_for_scenario
        app = create_app_for_scenario("chat", llm_client, config)
        
        # 注册并使用自定义场景
        from contextmind.config.registry import scenario_registry
        scenario_registry.register(
            name="custom",
            app_class=CustomApplication,
            aliases=["自定义"]
        )
        app = create_app_for_scenario("custom", llm_client, config)
    """
    from contextmind.config.registry import scenario_registry
    
    # 创建引擎
    engine = EvolveEngine(
        app_name=f"{app_name_prefix}_{scenario_name}",
        user_id=f"{app_name_prefix}_user",
        llm_client=llm_client
    )
    
    # 从注册表获取应用类
    app_class = scenario_registry.get_app_class(scenario_name)
    
    if app_class is None:
        # 提供友好的错误信息
        available_scenarios = scenario_registry.list_scenarios()
        raise ValueError(
            f"场景 '{scenario_name}' 未注册。\n"
            f"可用场景: {', '.join(available_scenarios)}\n"
            f"提示: 使用 scenario_registry.register() 注册新场景"
        )
    
    # 创建应用实例
    system_prompt = scenario_config.system_prompt
    return app_class(evolve_engine=engine, system_prompt=system_prompt, llm_client=llm_client)


__all__ = [
    # 插件系统
    "registry",
    "PluginRegistry",
    
    # 核心引擎
    "EvolveEngine",
    "EvolveTracker",  # 统一别名
    
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
    "ResponseParser",         # 统一别名
    
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
