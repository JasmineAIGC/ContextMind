"""
Utils - 实用工具模块

提供各种辅助功能：
- 配置管理
- 性能监控
- 上下文可视化
- 事件系统
- 上下文格式化 (v3.2新增)
"""

from .config import ConfigManager, validate_config
from .monitor import PerformanceMonitor, ContextMetrics
from .visualizer import ContextVisualizer
from .events import EventBus, Event
from .context_formatter import (
    ContextFormatter,
    format_context_result,
    format_memory_cache,
    format_prompt_analysis,
    format_complete_prompt,
    # 日志前缀常量
    LOG_PREFIX_PROCESS,
    LOG_PREFIX_COMPLETE,
    LOG_PREFIX_OPTIMIZE,
    LOG_PREFIX_MEMORY,
    LOG_PREFIX_PROMPT,
)

__all__ = [
    "ConfigManager",
    "validate_config",
    "PerformanceMonitor",
    "ContextMetrics",
    "ContextVisualizer",
    "EventBus",
    "Event",
    # v3.2 新增
    "ContextFormatter",
    "format_context_result",
    "format_memory_cache",
    "format_prompt_analysis",
    "format_complete_prompt",
    # 日志前缀常量
    "LOG_PREFIX_PROCESS",
    "LOG_PREFIX_COMPLETE",
    "LOG_PREFIX_OPTIMIZE",
    "LOG_PREFIX_MEMORY",
    "LOG_PREFIX_PROMPT",
]
