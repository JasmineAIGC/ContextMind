"""
Core Data Models Module

Core data models for messages, context, and configuration.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional


# ============================================================================
# Knowledge Types - Define early since used by other classes
# ============================================================================

class KnowledgeType(str, Enum):
    """
    从对话中提取的知识类型 (40种)
    
    分为10大类：用户画像、认知、行为、意图、关系、知识、情感、策略、上下文、多轮对话
    """
    # 原有9种基础类型
    PREFERENCE = "preference"  # 用户偏好（喜欢/不喜欢）
    FACT = "fact"              # 关于用户或主题的事实
    EVENT = "event"            # 事件或行为
    INTENT = "intent"          # 用户意图（想要做什么）
    NEED = "need"              # 用户需求（需要什么）
    OPINION = "opinion"        # 用户观点/看法
    HABIT = "habit"            # 用户习惯
    CONSTRAINT = "constraint"  # 约束条件（如预算、时间限制）
    INTEREST = "interest"      # 用户兴趣
    
    # 1. 用户画像类 (User Profile) - 4种
    USER_INFO = "user_info"            # 基本信息（年龄、职业、位置、姓名等）
    PERSONALITY = "personality"        # 性格特征
    VALUES = "values"                  # 价值观
    LIFESTYLE = "lifestyle"            # 生活方式
    
    # 2. 认知类 (Cognitive) - 3种新增（opinion已有）
    BELIEF = "belief"                  # 信念
    ATTITUDE = "attitude"              # 态度
    VALUE_JUDGMENT = "value_judgment"  # 价值判断
    
    # 3. 行为类 (Behavioral) - 3种新增（event, habit已有）
    EXPERIENCE = "experience"          # 经验
    SKILL = "skill"                    # 技能
    ACHIEVEMENT = "achievement"        # 成就
    
    # 4. 意图类 (Intentional) - 3种新增（intent, need已有）
    GOAL = "goal"                      # 目标
    PLAN = "plan"                      # 计划
    EXPECTATION = "expectation"        # 期望
    
    # 5. 关系类 (Relational) - 3种
    RELATIONSHIP = "relationship"              # 社交关系
    EMOTIONAL_CONNECTION = "emotional_connection"  # 情感连接
    INFLUENCE = "influence"                    # 影响因素
    
    # 6. 知识类 (Epistemic) - 3种新增（fact已有）
    PROCEDURAL = "procedural"          # 程序性知识（如何做某事）
    DOMAIN_KNOWLEDGE = "domain_knowledge"  # 领域知识
    COMMON_SENSE = "common_sense"      # 常识
    
    # 7. 情感类 (Emotional) - 2种新增（preference已有）
    EMOTION = "emotion"                # 情绪状态
    SENTIMENT = "sentiment"            # 情感倾向
    
    # 8. 策略类 (Strategic) - 4种
    SOLUTION = "solution"              # 解决方案
    STRATEGY = "strategy"              # 策略
    BEST_PRACTICE = "best_practice"    # 最佳实践
    LESSON_LEARNED = "lesson_learned"  # 经验教训
    
    # 9. 上下文类 (Contextual) - 2种新增（constraint, interest已有）
    TOPIC = "topic"                    # 话题
    SCENARIO = "scenario"              # 场景
    
    # 10. 多轮对话类 (Multi-turn) - 4种
    CONVERSATION_PATTERN = "conversation_pattern"        # 对话模式
    TOPIC_EVOLUTION = "topic_evolution"                  # 主题演变
    PROBLEM_SOLUTION_SEQ = "problem_solution_sequence"   # 问题-解决序列
    CAUSALITY = "causality"                              # 因果关系


class MemoryType(str, Enum):
    """记忆存储类型"""
    SEMANTIC = "semantic"      # 语义/向量存储
    KEYWORD = "keyword"        # 关键词存储
    STRUCTURED = "structured"  # 结构化数据存储


@dataclass
class EmbeddingInfo:
    """
    Embedding向量信息
    
    支持多种embedding模型，便于跨模型检索和模型升级
    """
    model: str  # embedding模型名称
    vector: List[float]  # 向量数据
    dimension: int  # 向量维度
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ScoreInfo:
    """
    知识评分信息
    
    四维评分体系用于检索排序和知识淡化
    """
    importance: float = 0.5  # 重要性分数（基于访问频率和知识类型）
    confidence: float = 0.5  # 置信度分数（基于提取方法和验证次数）
    relevance: float = 0.5  # 相关性分数（基于时间衰减和上下文匹配）
    quality: float = 0.5  # 质量分数（基于来源可靠性和内容完整性）


@dataclass
class VersionRecord:
    """
    知识版本记录
    
    追踪知识的演化历史，支持回滚和审计
    """
    version: int
    content: str
    updated_at: datetime
    update_reason: str
    confidence_delta: float = 0.0
    updated_by: str = "system"


# ============================================================================
# Message and Context Types
# ============================================================================

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
        timestamp: 创建/更新时间
        embeddings: 向量嵌入（用于语义检索）
        metadata: 附加元数据
    """
    content: str
    source: ContextSource
    score: float = 1.0
    timestamp: datetime = field(default_factory=datetime.now)
    embeddings: Dict[str, EmbeddingInfo] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextResult:
    """
    Context 检索/处理结果
    
    Attributes:
        items: Context 项列表
        total_tokens: 总 Token 数
        compressed: 是否经过压缩
        metadata: 处理元数据
    """
    items: List[ContextItem] = field(default_factory=list)
    total_tokens: int = 0
    compressed: bool = False
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
    
    # 语义检索参数
    min_overlap_chars: int = 3  # 最小字符重叠数
    base_score: float = 0.3  # 基础相关性分数
    relevance_threshold: float = 0.0  # 相关性阈值 (0表示不使用阈值过滤)
    
    # 新近性加权
    enable_recency_boost: bool = True  # 是否启用新近性加权
    recency_weight: float = 0.2  # 新近性权重
    recency_days_threshold: int = 7  # 新近性天数阈值
    
    # 去重和限制
    enable_deduplication: bool = True  # 是否启用去重
    similarity_threshold_for_dedup: float = 0.95  # 去重相似度阈值
    max_limit: int = 100  # 最大返回数量


@dataclass
class ExtractionConfig:
    """知识提取配置"""
    # 提取方式: 'rule' (规则提取) 或 'llm' (LLM 自动提取)
    extraction_method: str = "rule"  # 'rule' or 'llm'
    
    # 通用配置
    min_confidence: float = 0.5  # 降低阈值，允许提取更多潜在有价值的信息
    max_phrase_length: int = 100  # 增加最大短语长度，允许提取更长的描述
    
    # 提取类型开关
    extract_preferences: bool = True
    extract_facts: bool = True
    extract_events: bool = True
    extract_entities: bool = True  # 实体提取 (人名、地名等)
    extract_relationships: bool = True  # 关系提取 (例如: "张三是李四的同事")
    
    # 各类知识的置信度设置
    preference_confidence: float = 0.8
    fact_confidence: float = 0.7
    event_confidence: float = 0.6
    entity_confidence: float = 0.75
    relationship_confidence: float = 0.7
    
    # LLM 提取专用配置
    llm_temperature: float = 0.1  # 较低的温度确保提取的稳定性
    llm_max_tokens: int = 1000  # 提取结果的最大 token 数
    llm_batch_size: int = 10  # 批量处理消息数


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


def setup_logging(level: LogLevel = LogLevel.BASIC, python_log_level=None, save_to_file: bool = True, log_dir: str = "logs"):
    """
    设置 ContextMind 日志配置
    
    Args:
        level: ContextMind 日志级别 (BASIC, DETAILED 或 DEBUG)
        python_log_level: Python 日志级别 (默认基于 ContextMind 级别)
        save_to_file: 是否自动保存日志到文件 (默认: True)
        log_dir: 日志文件保存目录 (默认: "logs")
    """
    # 设置全局 ContextMind 日志级别
    set_global_log_level(level)
    
    # 将 ContextMind 级别映射到 Python 日志级别
    if python_log_level is None:
        if level == LogLevel.DEBUG:
            python_log_level = logging.DEBUG
        else:
            python_log_level = logging.INFO
    
    # 配置 handlers
    handlers = []
    
    # 控制台 handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(python_log_level)
    console_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    handlers.append(console_handler)
    
    # 文件 handler (如果启用)
    if save_to_file:
        import os
        from pathlib import Path
        
        # 创建日志目录
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        
        # 生成日志文件名 (包含时间戳)
        log_filename = f"contextmind_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        log_filepath = log_path / log_filename
        
        # 创建文件 handler
        file_handler = logging.FileHandler(log_filepath, encoding='utf-8')
        file_handler.setLevel(python_log_level)
        file_formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        handlers.append(file_handler)
        
        print(f"📝 日志将自动保存到: {log_filepath}")
    
    # 配置 Python 日志
    logging.basicConfig(
        level=python_log_level,
        format='[%(asctime)s] %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=handlers,
        force=True  # 覆盖任何现有配置
    )


# 导出日志级别以保持向后兼容
INFO = logging.INFO
DEBUG = logging.DEBUG


# ============================================================================
# Knowledge Storage Model
# ============================================================================

@dataclass
class Knowledge:
    """
    优化的知识存储模型
    
    设计目标:
    1. 检索优化 - 多层次索引，支持向量+关键词混合检索
    2. 便于更新 - 版本追踪，冲突检测，智能合并
    3. 多模态支持 - 支持多种embedding算法和模型
    4. 算法驱动 - 动态评分，自动淡化，智能排序
    
    Attributes:
        memory_id: 唯一标识符
        user_id: 所属用户ID
        session_id: 所属会话ID（可选）
        
        knowledge_type: 知识类型 (preference/fact/event)
        content: 核心文本内容
        summary: 简短摘要（可选）
        
        embeddings: 多embedding向量字典 {name: EmbeddingInfo}
        scores: 四维评分信息
        version_history: 版本历史记录
        
        extraction_method: 提取方法 ('rule' 或 'llm')
        source_message_ids: 源消息ID列表（完整追溯）
        
        created_at: 创建时间
        updated_at: 最后更新时间
        last_accessed: 最后访问时间
        access_count: 访问次数
        
        status: 状态 (active/archived/deleted)
        metadata: 扩展元数据
            - category: 细分类别
            - tags: 标签列表
            - keywords: 关键词列表
            - entities: 实体列表 [{text, type, sentiment}]
            - relationships: 关系列表 [{relation_type, target, strength}]
            - context: 上下文信息
            - conflicts: 冲突记录
    
    参考文档: docs/KNOWLEDGE_STORAGE_DESIGN.md
    """
    # 知识内容（无默认值字段必须在前）
    knowledge_type: KnowledgeType  # 保持兼容性
    content: str
    
    # 核心标识
    memory_id: str = field(default_factory=lambda: str(__import__('uuid').uuid4()))
    user_id: str = ""
    session_id: Optional[str] = None
    
    # 其他内容
    summary: Optional[str] = None
    
    # 多模态支持
    embeddings: Dict[str, EmbeddingInfo] = field(default_factory=dict)
    
    # 评分系统
    scores: ScoreInfo = field(default_factory=ScoreInfo)
    
    # 版本历史
    version_history: List[VersionRecord] = field(default_factory=list)
    
    # 提取信息
    extraction_method: str = "rule"  # 'rule' or 'llm'
    source_message_ids: List[str] = field(default_factory=list)
    
    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    last_accessed: Optional[datetime] = None
    
    # 访问统计
    access_count: int = 0
    
    # 状态
    status: str = "active"  # active/archived/deleted
    
    # 扩展元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 兼容性属性
    @property
    def type(self) -> KnowledgeType:
        """兼容性别名: knowledge_type -> type"""
        return self.knowledge_type
    
    @property
    def confidence(self) -> float:
        """兼容性别名: scores.confidence -> confidence"""
        return self.scores.confidence
    
    @property
    def importance_score(self) -> float:
        """兼容性别名: scores.importance -> importance_score"""
        return self.scores.importance
    
    @property
    def timestamp(self) -> datetime:
        """兼容性别名: created_at -> timestamp"""
        return self.created_at
    
    @property
    def source(self) -> str:
        """兼容性别名: metadata中的source"""
        return self.metadata.get("source", "")
    
    def to_storage_dict(self) -> Dict[str, Any]:
        """
        转换为存储格式
        
        完整的JSON Schema参考: docs/KNOWLEDGE_STORAGE_DESIGN.md
        """
        return {
            "memory_id": self.memory_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "type": self.knowledge_type.value,
            "content": self.content,
            "summary": self.summary,
            "embeddings": {
                name: {
                    "model": emb.model,
                    "vector": emb.vector,
                    "dimension": emb.dimension,
                    "created_at": emb.created_at.isoformat()
                }
                for name, emb in self.embeddings.items()
            },
            "metadata": self.metadata,
            "scores": {
                "importance": self.scores.importance,
                "confidence": self.scores.confidence,
                "relevance": self.scores.relevance,
                "quality": self.scores.quality
            },
            "version_history": [
                {
                    "version": v.version,
                    "content": v.content,
                    "updated_at": v.updated_at.isoformat(),
                    "update_reason": v.update_reason,
                    "confidence_delta": v.confidence_delta,
                    "updated_by": v.updated_by
                }
                for v in self.version_history
            ],
            "extraction_method": self.extraction_method,
            "source_message_ids": self.source_message_ids,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "access_count": self.access_count,
            "status": self.status
        }
