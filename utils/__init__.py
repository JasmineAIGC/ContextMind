"""通用工具模块 - ContextMind 通用工具集合

这个模块包含 ContextMind 框架和基础 DST 模式共用的工具：
- Logger: 统一的日志系统
- LLM Client: 统一的 LLM 客户端
- Embedding: 嵌入向量工具

所有模式都使用这些通用工具，确保一致性。
"""

from .logger import (
    LogLevel,
    ContextMindLogger,
    get_logger,
    setup_logging,
    set_global_log_level,
    get_global_log_level,
    INFO,
    DEBUG,
)

from .llm_client import (
    SimpleLLMClient,
    LLMConfig,
)

__all__ = [
    # Logger
    "LogLevel",
    "ContextMindLogger",
    "get_logger",
    "setup_logging",
    "set_global_log_level",
    "get_global_log_level",
    "INFO",
    "DEBUG",
    # LLM Client
    "SimpleLLMClient",
    "LLMConfig",
]
