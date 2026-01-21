"""
ContextMind v7.0 数据模型

Context Engineering 框架的最小化数据类定义
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional


class MessageRole(str, Enum):
    """对话消息角色"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class Message:
    """
    对话消息
    
    Attributes:
        role: 消息角色 (user/assistant/system)
        content: 消息内容
        timestamp: 消息创建时间
        metadata: 附加元数据
    """
    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class KnowledgeType(str, Enum):
    """从对话中提取的知识类型"""
    PREFERENCE = "preference"  # 用户偏好
    FACT = "fact"              # 关于用户或主题的事实
    EVENT = "event"            # 事件或行为


class MemoryType(str, Enum):
    """记忆存储类型"""
    SEMANTIC = "semantic"      # 语义/向量存储
    KEYWORD = "keyword"        # 关键词存储
    STRUCTURED = "structured"  # 结构化数据存储


@dataclass
class Knowledge:
    """
    从对话中提取的知识
    
    Attributes:
        content: 知识内容
        knowledge_type: 知识类型
        confidence: 置信度分数 (0-1)
        source: 来源信息
        timestamp: 提取时间
        metadata: 附加元数据
    """
    content: str
    knowledge_type: KnowledgeType
    confidence: float = 1.0
    source: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ContextSource(str, Enum):
    """Context 项来源"""
    MEMORY = "memory"
    RAG = "rag"
    HISTORY = "history"


@dataclass
class ContextItem:
    """
    用于 Prompt 构建的 Context 项
    
    Attributes:
        content: 项内容
        source: 来源
        score: 相关性分数
        metadata: 附加元数据
    """
    content: str
    source: ContextSource
    score: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextResult:
    """
    Context 检索/处理结果
    
    Attributes:
        items: Context 项列表
        total_tokens: 总 Token 数
        metadata: 处理元数据
    """
    items: List[ContextItem] = field(default_factory=list)
    total_tokens: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessedContext:
    """
    已处理和优化的 Context
    
    Attributes:
        items: Context 项列表
        metadata: 处理元数据 (压缩比等)
    """
    items: List[ContextItem] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryNote:
    """
    存储在 Memory Bank 中的记忆笔记
    
    Attributes:
        content: 笔记内容
        memory_type: 记忆类型
        timestamp: 创建时间
        metadata: 附加元数据 (访问次数、最后访问时间等)
    """
    content: str
    memory_type: str = "semantic"
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    """
    用于处理的文本块
    
    Attributes:
        text: 文本块内容
        metadata: 文本块元数据
    """
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextState:
    """
    Context 处理状态
    
    Attributes:
        current_tokens: 当前 Token 数
        max_tokens: 最大允许 Token 数
        metadata: 附加状态元数据
    """
    current_tokens: int = 0
    max_tokens: int = 2000
    metadata: Dict[str, Any] = field(default_factory=dict)


# 配置类
@dataclass
class RetrievalConfig:
    """Context 检索配置"""
    top_k: int = 5
    min_score: float = 0.5
    use_semantic: bool = True
    use_keyword: bool = False


@dataclass
class ExtractionConfig:
    """知识提取配置"""
    min_confidence: float = 0.6
    extract_preferences: bool = True
    extract_facts: bool = True
    extract_events: bool = True


@dataclass
class CompressionConfig:
    """Context 压缩配置"""
    max_tokens: int = 2000
    strategy: str = "simple"


@dataclass
class SummarizationConfig:
    """对话摘要配置"""
    enabled: bool = False
    max_turns: int = 10


@dataclass
class MemorySystemConfig:
    """记忆系统配置"""
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    compression: CompressionConfig = field(default_factory=CompressionConfig)
    summarization: SummarizationConfig = field(default_factory=SummarizationConfig)


# 默认配置
DEFAULT_MEMORY_CONFIG = MemorySystemConfig()


# 日志工具和系统
import logging
from enum import Enum as PyEnum

class LogLevel(PyEnum):
    """ContextMind 日志级别"""
    BASIC = "BASIC"      # 基础模式: Pipeline 级别日志
    DETAILED = "DETAILED"  # 详细模式: 步骤级别日志
    DEBUG = "DEBUG"      # 调试模式: 所有日志包括内部细节


class ContextMindLogger:
    """
    ContextMind v7.0 统一日志系统
    
    功能特性:
    - 基础模式: 记录 Pipeline 级别的输入、输出和关键信息
    - 详细模式: 记录步骤级别的输入、输出和中间信息
    - 调试模式: 记录所有内部细节
    
    使用示例:
        logger = ContextMindLogger("MyModule", level=LogLevel.BASIC)
        logger.pipeline("Starting context optimization")
        logger.step("Step 1: Preprocessing")
        logger.detail("Detailed information")
    """
    
    # 类级别变量：跟踪全局日志级别
    _global_level: LogLevel = LogLevel.BASIC
    
    def __init__(self, name: str, level: LogLevel = LogLevel.BASIC):
        """
        初始化 Logger
        
        Args:
            name: 模块名称
            level: 日志级别 (BASIC, DETAILED 或 DEBUG)
        """
        self.name = name
        self.level = level
        self._logger = logging.getLogger(name)
        
    def set_level(self, level: LogLevel):
        """设置日志级别"""
        self.level = level
    
    @classmethod
    def get_current_level(cls) -> LogLevel:
        """
        获取当前全局日志级别
        
        Returns:
            LogLevel: 当前的全局日志级别
        """
        return cls._global_level
    
    @classmethod
    def set_global_level(cls, level: LogLevel):
        """
        设置全局日志级别
        
        Args:
            level: 要设置的日志级别
        """
        cls._global_level = level
    
    def pipeline(self, message: str):
        """
        Pipeline 级别日志 (在 BASIC、DETAILED 和 DEBUG 模式下显示)
        用于主要的 Pipeline 事件: 开始、结束、输入、输出
        """
        self._logger.info(f"[{self.name}] {message}")
    
    def step(self, message: str):
        """
        步骤级别日志 (在 DETAILED 和 DEBUG 模式下显示)
        用于 Pipeline 中的各个步骤事件
        """
        if self.level in [LogLevel.DETAILED, LogLevel.DEBUG]:
            self._logger.info(f"[{self.name}] {message}")
    
    def detail(self, message: str):
        """
        详细日志 (仅在 DEBUG 模式下显示)
        用于内部细节和调试信息
        """
        if self.level == LogLevel.DEBUG:
            self._logger.debug(f"[{self.name}] {message}")
    
    def debug(self, message: str):
        """
        调试日志 - detail() 的向后兼容别名
        仅在 DEBUG 模式下显示
        """
        self.detail(message)
    
    def separator(self, char="=", length=100):
        """打印分隔线 (在所有模式下显示)"""
        self._logger.info(char * length)
    
    def section_start(self, title: str):
        """开始主要章节 (在所有模式下显示)"""
        self.separator("=")
        self._logger.info(f"[{self.name}] ========== {title} ==========")
        self.separator("=")
    
    def section_end(self, title: str = None):
        """结束主要章节 (在所有模式下显示)"""
        if title:
            self.separator("-")
            self._logger.info(f"[{self.name}] ========== {title} 结束 ==========")
            self.separator("-")
        else:
            self.separator("-")
    
    def info(self, message: str):
        """常规信息日志 (在所有模式下显示)"""
        self._logger.info(f"[{self.name}] {message}")
    
    def warning(self, message: str):
        """警告日志 (在所有模式下显示)"""
        self._logger.warning(f"[{self.name}] {message}")
    
    def error(self, message: str):
        """错误日志 (在所有模式下显示)"""
        self._logger.error(f"[{self.name}] {message}")


# 全局日志级别
_GLOBAL_LOG_LEVEL = LogLevel.BASIC


def set_global_log_level(level: LogLevel):
    """
    为所有 ContextMind Logger 设置全局日志级别
    
    Args:
        level: LogLevel.BASIC, LogLevel.DETAILED 或 LogLevel.DEBUG
    """
    global _GLOBAL_LOG_LEVEL
    _GLOBAL_LOG_LEVEL = level
    # 同时更新类级别变量
    ContextMindLogger.set_global_level(level)


def get_global_log_level() -> LogLevel:
    """获取当前全局日志级别"""
    return _GLOBAL_LOG_LEVEL


def get_logger(name: str, level: LogLevel = None) -> ContextMindLogger:
    """
    获取 ContextMind Logger 实例
    
    Args:
        name: Logger 名称 (通常为模块名)
        level: 日志级别 (未指定时使用全局级别)
        
    Returns:
        ContextMindLogger 实例
    """
    if level is None:
        level = _GLOBAL_LOG_LEVEL
    return ContextMindLogger(name, level)


def setup_logging(level: LogLevel = LogLevel.BASIC, python_log_level=None):
    """
    设置 ContextMind 日志配置
    
    Args:
        level: ContextMind 日志级别 (BASIC, DETAILED 或 DEBUG)
        python_log_level: Python 日志级别 (默认基于 ContextMind 级别)
    """
    # 设置全局 ContextMind 日志级别
    set_global_log_level(level)
    
    # 将 ContextMind 级别映射到 Python 日志级别
    if python_log_level is None:
        if level == LogLevel.DEBUG:
            python_log_level = logging.DEBUG
        else:
            python_log_level = logging.INFO
    
    # 配置 Python 日志
    logging.basicConfig(
        level=python_log_level,
        format='[%(asctime)s] %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        force=True  # 覆盖任何现有配置
    )


# 导出日志级别以保持向后兼容
INFO = logging.INFO
DEBUG = logging.DEBUG
