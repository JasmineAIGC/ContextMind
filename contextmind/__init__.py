"""
ContextMind - 专业的上下文优化框架 v5.0

清晰的模块化架构，每个模块职责单一，易于扩展：

核心模块：
- InputPreprocessor: 输入预处理
- ContextRetriever: 统一检索（RAG）
- MemoryBank: 长期记忆管理
- ContextCompressor: 上下文压缩
- ContextReorderer: 上下文重排序
- KnowledgeExtractor: 知识提取

架构设计 (v5.0):
- 应用层：使用引擎的应用
- 适配器层：对话系统集成接口
- 引擎层：ContextEngine 统一接口
- 模块层：InputPreprocessor, ContextRetriever, MemoryBank, ContextCompressor, ContextReorderer, KnowledgeExtractor
- 策略层：可插拔的策略实现
- 基础层：TokenizerService, VectorClient, CacheManager

v5.0 核心改进：
- 模块化重构：清晰的职责划分，易于扩展
- 策略可插拔：支持持续集成新算法
- 零冗余设计：功能不重复，代码简洁
- SOLID 原则：单一职责，依赖倒置
- 全面升级：demos和文档完全同步
- CodeQL 0 告警：高质量代码
"""

# 核心引擎
from .engine import ContextEngine

# 核心模块 (v4.0 模块化)
from .modules import (
    InputPreprocessor,
    ContextRetriever,
    MemoryBank,
    ContextCompressor,
    ContextReorderer,
    KnowledgeExtractor,
)

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
    # v3.2 新增
    Chunk,
    ContextState,
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
    ContextTextBuilder,  # 统一文本构建工具
)

# 基础层 (v3.2 新增)
from .foundation import (
    TokenizerService,
    TokenizerType,
    VectorClient,
    VectorSearchResult,
    CacheManager,
    CacheEntry,
)

# 控制层 (v3.2 新增)
from .control import (
    FlowController,
    CircuitBreaker,
    CircuitState,
)

__all__ = [
    # 核心引擎
    "ContextEngine",
    
    # 核心模块 (v4.0)
    "InputPreprocessor",
    "ContextRetriever",
    "MemoryBank",
    "ContextCompressor",
    "ContextReorderer",
    "KnowledgeExtractor",
    
    # 数据模型
    "Message",
    "MessageRole",
    "ContextItem",
    "ContextSource",
    "ContextResult",
    "ProcessedContext",
    "Knowledge",
    "KnowledgeType",
    "Chunk",  # v3.2
    "ContextState",  # v3.2
    
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
    "ContextTextBuilder",  # 统一文本构建工具
    
    # 基础层 (v3.2)
    "TokenizerService",
    "TokenizerType",
    "VectorClient",
    "VectorSearchResult",
    "CacheManager",
    "CacheEntry",
    
    # 控制层 (v3.2)
    "FlowController",
    "CircuitBreaker",
    "CircuitState",
]

__version__ = "5.0.0"
