"""
ContextMind - 专业的上下文优化框架 v7.2
ContextMind - Professional Context Optimization Framework v7.2

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

NEW in v7.2 - Architecture Refinement:
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

v7.2 核心改进：
- ✨ Clean Architecture: 移除所有旧代码和冗余文件
- ✨ Flat Structure: 扁平化目录结构，无冗余嵌套
- ✨ Plugin System: 统一的插件注册和发现机制
- ✨ Modular: 所有算法都可通过插件替换
- ✨ Universal: 适用任何LLM，推理在外部完成
- ✨ Enhanced Observability: 改进的日志系统
- ✨ Simplified API: 清晰的模块边界和导出接口
"""

# Plugin Registry (NEW in v7.0)
from .registry import registry, PluginRegistry

# Easy Integration API (NEW in v7.0)
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
    ContextCompressor,
    ContextReorderer,
    PostProcessor,
)
from .memory import (
    MemoryBank,
    SessionManager,
    KVCacheManager,
)
from .summarizer import (
    ConversationSummarizer,
)

# 策略 (Plugin System)
from .strategies import (
    # 基类
    BaseStrategy,
)

# 工具
from .models import (
    # 日志系统 (NEW in v7.0 - Unified Logging)
    ContextMindLogger,
    LogLevel,
    get_logger,
    setup_logging,
    set_global_log_level,
    get_global_log_level,
    INFO,
    DEBUG,
)

__all__ = [
    # Easy Integration API (NEW in v7.0)
    "ContextMind",
    
    # Plugin System (NEW in v7.0)
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
    
    # 核心层 - 日志系统 (NEW in v7.0)
    "ContextMindLogger",
    "LogLevel",
    "get_logger",
    "setup_logging",
    "set_global_log_level",
    "get_global_log_level",
    "INFO",
    "DEBUG",
    
    # 流水线层
    "InputPreprocessor",
    "MemoryBank",
    "ContextCompressor",
    "ContextReorderer",
    "SessionManager",
    "ConversationSummarizer",
    "PostProcessor",
    "KVCacheManager",
    
    # 策略基类
    "BaseStrategy",
]

__version__ = "7.2.0"  # 当前版本 Current version - Architecture Refinement
