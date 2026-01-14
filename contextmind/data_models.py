"""
ContextMind Data Models - 完整的数据模型定义

定义了上下文优化框架中所有核心数据结构，包括：
- 消息（Message）
- 上下文条目（ContextItem）
- 处理后的上下文（ProcessedContext）
- 上下文结果（ContextResult）
- 知识（Knowledge）

所有数据模型都使用 dataclass 实现，支持序列化和类型提示。
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum


class MessageRole(Enum):
    """消息角色枚举"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ContextSource(Enum):
    """上下文来源枚举"""
    SESSION = "session"
    MEMORY = "memory"
    KNOWLEDGE = "knowledge"
    EXTERNAL = "external"


class KnowledgeType(Enum):
    """知识类型枚举"""
    FACT = "fact"
    EVENT = "event"
    PREFERENCE = "preference"
    ENTITY = "entity"
    RULE = "rule"


@dataclass
class Message:
    """
    对话消息数据模型
    
    表示对话中的一条消息，包含角色、内容、时间戳和元数据。
    
    Attributes:
        role: 消息角色（用户、助手、系统）
        content: 消息内容
        timestamp: 消息时间戳
        metadata: 附加元数据字典
    """
    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            'role': self.role.value,
            'content': self.content,
            'timestamp': self.timestamp.isoformat(),
            'metadata': self.metadata
        }


@dataclass
class ContextItem:
    """
    上下文条目数据模型
    
    表示上下文中的一条信息，包含内容、来源、分数、时间戳和元数据。
    
    Attributes:
        content: 上下文内容
        source: 上下文来源（会话、记忆、知识、外部）
        score: 相关性分数（0-1），默认为1.0
        timestamp: 时间戳
        metadata: 附加元数据字典
    """
    content: str
    source: ContextSource
    score: float = 1.0
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            'content': self.content,
            'source': self.source.value,
            'score': self.score,
            'timestamp': self.timestamp.isoformat(),
            'metadata': self.metadata
        }


@dataclass
class ProcessedContext:
    """
    处理后的上下文数据模型
    
    包含一组上下文条目和相关元数据，用于在处理流水线中传递。
    
    Attributes:
        items: 上下文条目列表
        metadata: 处理过程中的元数据
    """
    items: List[ContextItem] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_item(self, item: ContextItem) -> None:
        """添加上下文条目"""
        self.items.append(item)
    
    def get_by_source(self, source: ContextSource) -> List[ContextItem]:
        """根据来源筛选上下文条目"""
        return [item for item in self.items if item.source == source]
    
    def get_text(self, max_length: Optional[int] = None) -> str:
        """
        获取所有上下文条目的文本表示
        
        Args:
            max_length: 最大长度限制，超过则截断
            
        Returns:
            合并后的文本字符串
        """
        text = "\n\n".join(item.content for item in self.items)
        if max_length and len(text) > max_length:
            return text[:max_length]
        return text
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            'items': [item.to_dict() for item in self.items],
            'metadata': self.metadata
        }


@dataclass
class ContextResult:
    """
    上下文优化结果数据模型
    
    包含优化后的所有上下文信息，分为近期历史、长期记忆和外部知识。
    这是 ContextEngine.optimize() 方法的返回类型。
    
    Attributes:
        recent_history: 近期对话历史消息列表
        long_term_memory: 长期记忆上下文条目列表
        external_knowledge: 外部知识上下文条目列表
        metadata: 优化过程的元数据
    """
    recent_history: List[Message] = field(default_factory=list)
    long_term_memory: List[ContextItem] = field(default_factory=list)
    external_knowledge: List[ContextItem] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_all_items(self) -> List[ContextItem]:
        """
        获取所有上下文项（包括历史消息转换为上下文项）
        
        Returns:
            合并后的上下文条目列表
        """
        items = []
        # 转换历史消息为上下文项
        for msg in self.recent_history:
            items.append(ContextItem(
                content=f"{msg.role.value}: {msg.content}",
                source=ContextSource.SESSION,
                timestamp=msg.timestamp,
                metadata=msg.metadata
            ))
        items.extend(self.long_term_memory)
        items.extend(self.external_knowledge)
        return items
    
    def get_all_context_text(self) -> str:
        """
        获取所有上下文的格式化文本表示
        
        Returns:
            格式化的上下文文本，包含对话历史、长期记忆和外部知识三个部分
        """
        parts = []
        
        if self.recent_history:
            history_text = "\n".join(
                f"{msg.role.value}: {msg.content}" 
                for msg in self.recent_history
            )
            parts.append(f"## 对话历史\n{history_text}")
        
        if self.long_term_memory:
            memory_text = "\n".join(
                f"- {item.content} (相关性: {item.score:.2f})"
                for item in self.long_term_memory
            )
            parts.append(f"## 长期记忆\n{memory_text}")
        
        if self.external_knowledge:
            knowledge_text = "\n".join(
                f"- {item.content}"
                for item in self.external_knowledge
            )
            parts.append(f"## 外部知识\n{knowledge_text}")
        
        return "\n\n".join(parts)
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            'recent_history': [msg.to_dict() for msg in self.recent_history],
            'long_term_memory': [item.to_dict() for item in self.long_term_memory],
            'external_knowledge': [item.to_dict() for item in self.external_knowledge],
            'metadata': self.metadata
        }


@dataclass
class Knowledge:
    """
    提取的知识数据模型
    
    表示从对话中提取的结构化知识，包含内容、类型、置信度和元数据。
    
    Attributes:
        content: 知识内容
        type: 知识类型（事实、事件、偏好、实体、规则）
        confidence: 置信度（0-1），默认为1.0
        timestamp: 提取时间戳
        metadata: 附加元数据字典
    """
    content: str
    type: KnowledgeType
    confidence: float = 1.0
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            'content': self.content,
            'type': self.type.value,
            'confidence': self.confidence,
            'timestamp': self.timestamp.isoformat(),
            'metadata': self.metadata
        }


# ============================================================================
# v3.2 Enhanced Data Models - 增强的数据模型
# ============================================================================


@dataclass
class Chunk:
    """
    上下文块（v3.2新增）
    
    比ContextItem更丰富的上下文单元，包含token计数和多种评分。
    用于更精细的上下文处理和优化。
    
    Attributes:
        content: 内容文本
        token_count: Token数量（由TokenizerService计算）
        relevance_score: 相关性分数（0-1）
        diversity_score: 多样性分数（0-1）
        entropy_score: 熵分数（信息量指标）
        source: 来源类型
        timestamp: 时间戳
        metadata: 附加元数据
    """
    content: str
    token_count: int = 0
    relevance_score: float = 1.0
    diversity_score: float = 0.0
    entropy_score: float = 0.0
    source: ContextSource = ContextSource.EXTERNAL
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            'content': self.content,
            'token_count': self.token_count,
            'relevance_score': self.relevance_score,
            'diversity_score': self.diversity_score,
            'entropy_score': self.entropy_score,
            'source': self.source.value,
            'timestamp': self.timestamp.isoformat(),
            'metadata': self.metadata
        }
    
    def to_context_item(self) -> ContextItem:
        """转换为ContextItem（兼容性）"""
        return ContextItem(
            content=self.content,
            source=self.source,
            score=self.relevance_score,
            timestamp=self.timestamp,
            metadata={
                **self.metadata,
                'token_count': self.token_count,
                'diversity_score': self.diversity_score,
                'entropy_score': self.entropy_score,
            }
        )


@dataclass
class ContextState:
    """
    上下文状态对象（v3.2新增）
    
    在流水线中流转的核心数据结构，包含完整的处理状态。
    这是一个"富对象"，记录了从原始查询到最终优化的全过程。
    
    使用场景：
    - 在Pipeline各阶段之间传递
    - 记录处理日志用于调试
    - 追踪Token预算使用情况
    
    Attributes:
        query: 用户查询
        raw_chunks: 原始召回的chunks
        ranked_chunks: 排序后的chunks
        optimized_chunks: 优化后的chunks
        budget_limit: Token预算限制
        current_usage: 当前Token使用量
        token_counts: 各阶段的Token统计
        logs: 可解释性日志
        metadata: 附加元数据
    """
    query: str = ""
    raw_chunks: List[Chunk] = field(default_factory=list)
    ranked_chunks: List[Chunk] = field(default_factory=list)
    optimized_chunks: List[Chunk] = field(default_factory=list)
    budget_limit: int = 4096
    current_usage: int = 0
    token_counts: Dict[str, int] = field(default_factory=dict)
    logs: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_log(self, message: str) -> None:
        """添加日志"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.logs.append(f"[{timestamp}] {message}")
    
    def update_token_count(self, stage: str, count: int) -> None:
        """更新Token计数"""
        self.token_counts[stage] = count
        self.current_usage = sum(self.token_counts.values())
    
    def has_budget(self, required: int) -> bool:
        """检查是否有足够的Token预算"""
        return (self.current_usage + required) <= self.budget_limit
    
    def remaining_budget(self) -> int:
        """获取剩余预算"""
        return max(0, self.budget_limit - self.current_usage)
    
    def to_processed_context(self) -> ProcessedContext:
        """转换为ProcessedContext（兼容性）"""
        items = [chunk.to_context_item() for chunk in self.optimized_chunks]
        return ProcessedContext(
            items=items,
            metadata={
                **self.metadata,
                'budget_limit': self.budget_limit,
                'current_usage': self.current_usage,
                'token_counts': self.token_counts,
                'logs': self.logs,
            }
        )
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            'query': self.query,
            'raw_chunks': [c.to_dict() for c in self.raw_chunks],
            'ranked_chunks': [c.to_dict() for c in self.ranked_chunks],
            'optimized_chunks': [c.to_dict() for c in self.optimized_chunks],
            'budget_limit': self.budget_limit,
            'current_usage': self.current_usage,
            'token_counts': self.token_counts,
            'logs': self.logs,
            'metadata': self.metadata
        }
