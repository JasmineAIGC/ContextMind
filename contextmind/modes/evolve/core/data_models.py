"""用于消息、上下文项、知识和其他核心数据结构的数据类模型。"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional

from .types import KnowledgeType, MessageRole, ContextSource
from contextmind.infra.data_models import EmbeddingInfo



@dataclass
class ScoreInfo:
    """四维评分体系（importance/confidence/relevance/quality）用于检索排序和知识淡化。"""
    importance: float = 0.5
    confidence: float = 0.5
    relevance: float = 0.5
    quality: float = 0.5


@dataclass
class VersionRecord:
    """追踪知识的演化历史，支持回滚和审计。"""
    version: int
    content: str
    updated_at: datetime
    update_reason: str
    confidence_delta: float = 0.0
    updated_by: str = "system"



@dataclass
class Message:
    """对话消息。"""
    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextItem:
    """用于 Prompt 构建的上下文项。"""
    content: str
    source: ContextSource
    score: float = 1.0
    timestamp: datetime = field(default_factory=datetime.now)
    embeddings: Dict[str, EmbeddingInfo] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextResult:
    """上下文检索/处理结果。"""
    items: List[ContextItem] = field(default_factory=list)
    total_tokens: int = 0
    compressed: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessedContext:
    """已处理和优化的上下文。"""
    items: List[ContextItem] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryNote:
    """存储在记忆库中的记忆笔记。"""
    content: str
    memory_type: str = "semantic"
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    """用于处理的文本块。"""
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextState:
    """上下文处理状态。"""
    current_tokens: int = 0
    max_tokens: int = 2000
    metadata: Dict[str, Any] = field(default_factory=dict)



@dataclass
class Knowledge:
    """
    优化的知识存储模型，支持多层次索引、版本追踪、四维评分和动态淡化。

    参考文档: docs/KNOWLEDGE_STORAGE_DESIGN.md
    """
    knowledge_type: KnowledgeType  # 保持兼容性
    content: str
    memory_id: str = field(default_factory=lambda: str(__import__('uuid').uuid4()))
    user_id: str = ""
    session_id: Optional[str] = None
    summary: Optional[str] = None
    embeddings: Dict[str, EmbeddingInfo] = field(default_factory=dict)
    scores: ScoreInfo = field(default_factory=ScoreInfo)
    version_history: List[VersionRecord] = field(default_factory=list)
    extraction_method: str = "rule"  # 'rule' 或 'llm'
    source_message_ids: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    last_accessed: Optional[datetime] = None
    access_count: int = 0
    status: str = "active"  # active/archived/deleted
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
