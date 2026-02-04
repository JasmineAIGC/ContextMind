"""
核心数据模型 (v0.2.1)

用于消息、上下文项、知识和其他核心数据结构的数据类模型。
在v0.2.1模块化重构期间从models.py中提取，以实现更好的组织结构。
在v0.2.1中，EmbeddingInfo移到utils模块以保持utils的独立性。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional

from .types import KnowledgeType, MessageRole, ContextSource
# EmbeddingInfo 现在从 utils 导入，保持 utils 模块独立性
from contextmind.core.common.utils.data_models import EmbeddingInfo


# ============================================================================
# 评分和版本模型
# ============================================================================


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
# 消息和上下文类型
# ============================================================================

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


@dataclass
class ContextItem:
    """
    用于 Prompt 构建的上下文项
    
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
    上下文检索/处理结果
    
    Attributes:
        items: 上下文项列表
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
    已处理和优化的上下文
    
    Attributes:
        items: 上下文项列表
        metadata: 处理元数据 (压缩比等)
    """
    items: List[ContextItem] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryNote:
    """
    存储在记忆库中的记忆笔记
    
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
    上下文处理状态
    
    Attributes:
        current_tokens: 当前 Token 数
        max_tokens: 最大允许 Token 数
        metadata: 附加状态元数据
    """
    current_tokens: int = 0
    max_tokens: int = 2000
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# 知识存储模型
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
        
        embeddings: 多嵌入向量字典 {name: EmbeddingInfo}
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
    extraction_method: str = "rule"  # 'rule' 或 'llm'
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
