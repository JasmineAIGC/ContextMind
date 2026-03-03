"""
Evolve - 上下文优化框架

通用化的上下文工程框架，支持任意对话场景。
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

from .pipeline import (
    Preprocessor,
    ContextRetriever,
    ContextCompressor,
    ContextReorderer,
    ResponseHandler,
    BaseSummarizer,
    LLMBasedSummarizer,
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
ConversationSummarizer = LLMBasedSummarizer
ResponseParser = ResponseHandler
EvolveTracker = EvolveEngine


def create_app_for_scenario(scenario_name: str, llm_client, scenario_config, app_name_prefix: str = "demo"):
    """
    为指定场景创建应用实例的工厂方法。

    Args:
        scenario_name: 场景名称（支持中英文别名）
        llm_client: LLM客户端实例
        scenario_config: 场景配置对象
        app_name_prefix: 应用名称前缀

    Returns:
        对应场景的Application实例

    Raises:
        ValueError: 如果场景未注册

    Example:
        app = create_app_for_scenario("chat", llm_client, config)
    """
    from contextmind.config.registry import scenario_registry
    
    engine = EvolveEngine(
        app_name=f"{app_name_prefix}_{scenario_name}",
        user_id=f"{app_name_prefix}_user",
        llm_client=llm_client
    )
    
    app_class = scenario_registry.get_app_class(scenario_name)
    
    if app_class is None:
        available_scenarios = scenario_registry.list_scenarios()
        raise ValueError(
            f"场景 '{scenario_name}' 未注册。\n"
            f"可用场景: {', '.join(available_scenarios)}\n"
            f"提示: 使用 scenario_registry.register() 注册新场景"
        )
    
    system_prompt = scenario_config.system_prompt
    return app_class(evolve_engine=engine, system_prompt=system_prompt, llm_client=llm_client)


__all__ = [
    # 插件系统
    "registry",
    "PluginRegistry",
    
    # 核心引擎
    "EvolveEngine",
    "EvolveTracker",
    
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
    
    # 流水线
    "InputPreprocessor",
    "Preprocessor",
    "ContextRetriever",
    "ContextCompressor",
    "ContextReorderer",
    "ResponseHandler",
    "ResponseParser",
    
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

__version__ = "0.2.1"
