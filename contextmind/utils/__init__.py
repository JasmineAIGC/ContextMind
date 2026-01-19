"""
Utils - 实用工具模块
Utils - Utility modules

提供各种辅助功能 Provides various utility functions：
- 性能监控与事件系统 Performance monitoring and event system (monitor.py)
- 上下文格式化与可视化 Context formatting and visualization (context_formatter.py)
- 文本构建工具 Text building tools (text_builder.py)
- 对话摘要工具 Conversation summarization (summarizer.py)
- Token计数服务 Token counting service (tokenizer.py)
- 向量客户端 Vector client (vector_client.py)
- 缓存管理 Cache management (cache.py)
"""

# 性能监控和事件系统（已合并events.py）
# Performance monitoring and event system (events.py merged into monitor.py)
from .monitor import PerformanceMonitor, ContextMetrics, EventBus, Event

# 上下文格式化和可视化（已合并visualizer.py）
# Context formatting and visualization (visualizer.py merged into context_formatter.py)
from .context_formatter import (
    ContextFormatter,
    ContextVisualizer,
    format_context_result,
    format_memory_cache,
    format_prompt_analysis,
    format_complete_prompt,
    # 日志前缀常量 Log prefix constants
    LOG_PREFIX_PROCESS,
    LOG_PREFIX_COMPLETE,
    LOG_PREFIX_OPTIMIZE,
    LOG_PREFIX_MEMORY,
    LOG_PREFIX_PROMPT,
)

# 文本构建和摘要 Text building and summarization
from .text_builder import ContextTextBuilder
from .summarizer import ConversationSummarizer, SummarizedHistory

# 基础服务 Foundation services
from .tokenizer import TokenizerService, TokenizerType
from .vector_client import VectorClient, VectorSearchResult
from .cache import CacheManager, CacheEntry

__all__ = [
    # 监控和事件 Monitoring and events
    "PerformanceMonitor",
    "ContextMetrics",
    "EventBus",
    "Event",
    # 格式化和可视化 Formatting and visualization
    "ContextFormatter",
    "ContextVisualizer",
    "format_context_result",
    "format_memory_cache",
    "format_prompt_analysis",
    "format_complete_prompt",
    # 日志前缀 Log prefixes
    "LOG_PREFIX_PROCESS",
    "LOG_PREFIX_COMPLETE",
    "LOG_PREFIX_OPTIMIZE",
    "LOG_PREFIX_MEMORY",
    "LOG_PREFIX_PROMPT",
    # 文本工具 Text tools
    "ContextTextBuilder",
    "ConversationSummarizer",
    "SummarizedHistory",
    # 基础服务 Foundation services
    "TokenizerService",
    "TokenizerType",
    "VectorClient",
    "VectorSearchResult",
    "CacheManager",
    "CacheEntry",
]
