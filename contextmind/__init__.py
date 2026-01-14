"""
ContextMind - 专业的上下文优化框架 v3.1

支持上下文工程的所有核心能力：
- 输入预处理
- 上下文收集（短期/长期/外部）
- 上下文整合
- 上下文优化（压缩/重排）
- 知识提取

架构设计：
- 应用层：使用引擎的应用
- 引擎层：ContextEngine 统一接口
- 流水线层：InputProcessor, ContextCollector, ContextIntegrator, ContextOptimizer, KnowledgeExtractor
- 策略层：可插拔的策略实现
- 适配器层：对话系统集成接口
- 工具层：配置、监控、可视化、事件系统
"""

# 核心引擎
from .engine import ContextEngine

# 数据模型
from .data_models import (
    Message,
    MessageRole,
    ContextItem,
    ContextSource,
    ContextResult,
    ProcessedContext,
    Knowledge,
    KnowledgeType,
)

# 客户端
from .client import Client, ClientConfig

# 日志
from .logger import get_logger, setup_logging, INFO, DEBUG

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

# 适配器 (新增)
from .adapters import (
    BaseAdapter,
    DialogContext,
    DialogMessage,
    OpenAIAdapter,
    LangChainAdapter,
    CustomAdapter,
)

# 工具 (新增)
from .utils import (
    ConfigManager,
    validate_config,
    PerformanceMonitor,
    ContextMetrics,
    ContextVisualizer,
    EventBus,
    Event,
)

__all__ = [
    # 核心引擎
    "ContextEngine",
    
    # 数据模型
    "Message",
    "MessageRole",
    "ContextItem",
    "ContextSource",
    "ContextResult",
    "ProcessedContext",
    "Knowledge",
    "KnowledgeType",
    
    # 客户端
    "Client",
    "ClientConfig",
    
    # 日志
    "get_logger",
    "setup_logging",
    "INFO",
    "DEBUG",
    
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
    
    # 工具
    "ConfigManager",
    "validate_config",
    "PerformanceMonitor",
    "ContextMetrics",
    "ContextVisualizer",
    "EventBus",
    "Event",
]

__version__ = "3.1.0"
