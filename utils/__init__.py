"""通用工具模块 - ContextMind 通用工具集合

这个模块包含 ContextMind 框架和基础 DST 模式共用的工具：
- Logger: 统一的日志系统
- LLM Client: 统一的 LLM 客户端
- Embedding: 嵌入向量工具
- Data Models: 工具模块的数据模型

所有模式都使用这些通用工具，确保一致性。
utils 模块是完全独立的，不依赖 baseline 或 evolve 模块。
"""

from .logger import (
    LogLevel,
    EvolveLogger,
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

from .data_models import (
    EmbeddingInfo,
)

__all__ = [
    # Logger
    "LogLevel",
    "EvolveLogger",
    "get_logger",
    "setup_logging",
    "set_global_log_level",
    "get_global_log_level",
    "INFO",
    "DEBUG",
    # LLM Client
    "SimpleLLMClient",
    "LLMConfig",
    # Data Models
    "EmbeddingInfo",
]

__version__ = "0.4.1"  # 独立工具模块，完全不依赖evolve/baseline
