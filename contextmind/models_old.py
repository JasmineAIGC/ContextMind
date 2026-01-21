"""
Data models for ContextMind v7.0

Minimal data classes for context engineering framework.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional


class MessageRole(str, Enum):
    """Message role in conversation"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class Message:
    """
    Conversation message
    
    Attributes:
        role: Message role (user/assistant/system)
        content: Message content
        timestamp: When the message was created
        metadata: Additional metadata
    """
    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class KnowledgeType(str, Enum):
    """Type of knowledge extracted from conversation"""
    PREFERENCE = "preference"  # User preferences
    FACT = "fact"              # Facts about user or topic
    EVENT = "event"            # Events or actions


@dataclass
class Knowledge:
    """
    Extracted knowledge from conversation
    
    Attributes:
        type: Type of knowledge
        content: Knowledge content
        source: Source of the knowledge
        confidence: Confidence score (0.0-1.0)
        metadata: Additional metadata
    """
    type: KnowledgeType
    content: str
    source: str = ""
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class ContextSource(str, Enum):
    """Source of context item"""
    SESSION = "session"        # From current session
    LONG_TERM = "long_term"    # From long-term memory


@dataclass
class ContextItem:
    """
    Item in optimized context
    
    Attributes:
        content: Item content
        source: Source of the item
        score: Relevance score
        metadata: Additional metadata
    """
    content: str
    source: ContextSource
    score: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextResult:
    """
    Result of context optimization
    
    Attributes:
        session_history: Recent session messages
        long_term_memory: Retrieved long-term memories
        user_input: Current user input
        metadata: Additional metadata (stats, scores, etc.)
    """
    session_history: List[Message] = field(default_factory=list)
    long_term_memory: List[ContextItem] = field(default_factory=list)
    user_input: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessedContext:
    """
    Processed/optimized context ready for LLM
    
    Attributes:
        items: List of context items
        metadata: Processing metadata (compression ratio, etc.)
    """
    items: List[ContextItem] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


def get_logger(name: str):
    """
    Simple logger factory
    
    Args:
        name: Logger name
        
    Returns:
        Python logger instance
    """
    import logging
    return logging.getLogger(name)
