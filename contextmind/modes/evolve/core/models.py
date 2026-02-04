"""
核心数据模型模块 (v0.2.1 兼容层)

模块 - 从拆分的模块导入。
对于新代码，请直接从 types、data_models、configs 或 utils.logger 导入。

此模块通过重新导出v0.2.1中引入的新模块化结构的所有组件。
"""

# 从新的模块化结构导入
from .types import (
    KnowledgeType,
    MemoryType,
    MessageRole,
    ContextSource,
)

from .data_models import (
    EmbeddingInfo,
    ScoreInfo,
    VersionRecord,
    Message,
    ContextItem,
    ContextResult,
    ProcessedContext,
    MemoryNote,
    Chunk,
    ContextState,
    Knowledge,
)

from .configs import (
    RetrievalConfig,
    ExtractionConfig,
    CompressionConfig,
    SummarizationConfig,
    MemorySystemConfig,
    DEFAULT_MEMORY_CONFIG,
)

from contextmind.core.common.utils.logger import (
    LogLevel,
    EvolveLogger,
    get_logger,
    setup_logging,
    set_global_log_level,
    get_global_log_level,
    INFO,
    DEBUG,
)

# 重新导出所有内容
__all__ = [
    # 类型
    "KnowledgeType",
    "MemoryType",
    "MessageRole",
    "ContextSource",
    # 数据模型
    "EmbeddingInfo",
    "ScoreInfo",
    "VersionRecord",
    "Message",
    "ContextItem",
    "ContextResult",
    "ProcessedContext",
    "MemoryNote",
    "Chunk",
    "ContextState",
    "Knowledge",
    # 配置
    "RetrievalConfig",
    "ExtractionConfig",
    "CompressionConfig",
    "SummarizationConfig",
    "MemorySystemConfig",
    "DEFAULT_MEMORY_CONFIG",
    # 日志
    "LogLevel",
    "EvolveLogger",
    "get_logger",
    "setup_logging",
    "set_global_log_level",
    "get_global_log_level",
    "INFO",
    "DEBUG",
]
