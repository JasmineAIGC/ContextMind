"""
ContextMind Data Models

定义核心数据结构，用于上下文优化结果的表示。
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class Message:
    """对话消息
    
    表示对话中的单条消息，包含角色、内容、时间戳等信息。
    
    Attributes:
        role: 消息角色，可选值为 'user' | 'assistant' | 'system'
        content: 消息内容
        timestamp: 消息时间戳
        metadata: 额外的元数据信息
    """
    role: str  # 'user' | 'assistant' | 'system'
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Memory:
    """长期记忆条目
    
    表示从对话中提取或预设的长期记忆信息。
    
    Attributes:
        content: 记忆内容
        source: 记忆来源，可选值为 'seed' | 'extracted' | 'summary'
        timestamp: 记忆时间戳
        score: 相关性分数，用于排序和筛选
        metadata: 额外的元数据信息
    """
    content: str
    source: str  # 'seed' | 'extracted' | 'summary'
    timestamp: datetime
    score: float = 0.0  # 相关性分数
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextResult:
    """上下文优化结果
    
    包含经过优化的上下文信息，供应用层使用。
    
    Attributes:
        recent_history: 最近对话历史列表
        long_term_memory: 相关长期记忆列表
        metadata: 额外的元数据信息（如优化时间、统计信息等）
    """
    recent_history: List[Message] = field(default_factory=list)  # 最近对话历史
    long_term_memory: List[Memory] = field(default_factory=list)  # 相关长期记忆
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """转换为字典格式，便于应用层使用
        
        Returns:
            包含所有上下文信息的字典
        """
        return {
            'recent_history': [
                {
                    'role': m.role, 
                    'content': m.content, 
                    'timestamp': m.timestamp.isoformat(),
                    'metadata': m.metadata
                }
                for m in self.recent_history
            ],
            'long_term_memory': [
                {
                    'content': m.content, 
                    'score': m.score, 
                    'source': m.source,
                    'timestamp': m.timestamp.isoformat(),
                    'metadata': m.metadata
                }
                for m in self.long_term_memory
            ],
            'metadata': self.metadata
        }
