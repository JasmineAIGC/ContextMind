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
        content: Knowledge content
        knowledge_type: Type of knowledge
        confidence: Confidence score (0-1)
        source: Source information
        timestamp: When extracted
        metadata: Additional metadata
    """
    content: str
    knowledge_type: KnowledgeType
    confidence: float = 1.0
    source: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ContextSource(str, Enum):
    """Source of context item"""
    MEMORY = "memory"
    RAG = "rag"
    HISTORY = "history"


@dataclass
class ContextItem:
    """
    Context item for prompt building
    
    Attributes:
        content: Item content
        source: Where this item comes from
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
    Result from context retrieval/processing
    
    Attributes:
        items: List of context items
        total_tokens: Total token count
        metadata: Processing metadata
    """
    items: List[ContextItem] = field(default_factory=list)
    total_tokens: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessedContext:
    """
    Processed and optimized context
    
    Attributes:
        items: List of context items
        metadata: Processing metadata (compression ratio, etc.)
    """
    items: List[ContextItem] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


# Configuration classes
@dataclass
class RetrievalConfig:
    """Configuration for context retrieval"""
    top_k: int = 5
    min_score: float = 0.5
    use_semantic: bool = True
    use_keyword: bool = False


@dataclass
class ExtractionConfig:
    """Configuration for knowledge extraction"""
    min_confidence: float = 0.6
    extract_preferences: bool = True
    extract_facts: bool = True
    extract_events: bool = True


@dataclass
class CompressionConfig:
    """Configuration for context compression"""
    max_tokens: int = 2000
    strategy: str = "simple"


@dataclass
class SummarizationConfig:
    """Configuration for conversation summarization"""
    enabled: bool = False
    max_turns: int = 10


@dataclass
class MemorySystemConfig:
    """Configuration for memory system"""
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    compression: CompressionConfig = field(default_factory=CompressionConfig)
    summarization: SummarizationConfig = field(default_factory=SummarizationConfig)


# Default configuration
DEFAULT_MEMORY_CONFIG = MemorySystemConfig()


# Logging utilities
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


def setup_logging(level=None):
    """Setup basic logging configuration"""
    import logging
    if level is None:
        level = logging.INFO
    logging.basicConfig(
        level=level,
        format='[%(asctime)s] %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


# Logging levels
import logging
INFO = logging.INFO
DEBUG = logging.DEBUG
