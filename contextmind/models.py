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


class MemoryType(str, Enum):
    """Type of memory storage"""
    SEMANTIC = "semantic"      # Semantic/vector-based storage
    KEYWORD = "keyword"        # Keyword-based storage
    STRUCTURED = "structured"  # Structured data storage


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


@dataclass
class MemoryNote:
    """
    Memory note stored in memory bank
    
    Attributes:
        content: Note content
        memory_type: Type of memory
        timestamp: When created
        metadata: Additional metadata (access_count, last_access, etc.)
    """
    content: str
    memory_type: str = "semantic"
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    """
    Text chunk for processing
    
    Attributes:
        text: Chunk text
        metadata: Chunk metadata
    """
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextState:
    """
    Context processing state
    
    Attributes:
        current_tokens: Current token count
        max_tokens: Maximum allowed tokens
        metadata: Additional state metadata
    """
    current_tokens: int = 0
    max_tokens: int = 2000
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


# Logging utilities and system
import logging
from enum import Enum as PyEnum

class LogLevel(PyEnum):
    """Logging levels for ContextMind"""
    BASIC = "BASIC"      # Basic mode: pipeline-level logs
    DETAILED = "DETAILED"  # Detailed mode: step-level logs
    DEBUG = "DEBUG"      # Debug mode: all logs including internal details


class ContextMindLogger:
    """
    Unified logging system for ContextMind v7.0
    
    Features:
    - Basic mode: Logs pipeline-level inputs, outputs, and key information
    - Detailed mode: Logs step-level inputs, outputs, and intermediate information
    - Debug mode: Logs all internal details
    
    Usage:
        logger = ContextMindLogger("MyModule", level=LogLevel.BASIC)
        logger.pipeline("Starting context optimization")
        logger.step("Step 1: Preprocessing")
        logger.detail("Detailed information")
    """
    
    def __init__(self, name: str, level: LogLevel = LogLevel.BASIC):
        """
        Initialize logger
        
        Args:
            name: Module name
            level: Logging level (BASIC, DETAILED, or DEBUG)
        """
        self.name = name
        self.level = level
        self._logger = logging.getLogger(name)
        
    def set_level(self, level: LogLevel):
        """Set logging level"""
        self.level = level
    
    def pipeline(self, message: str):
        """
        Pipeline-level log (shown in BASIC, DETAILED, and DEBUG modes)
        Use for major pipeline events: start, end, inputs, outputs
        """
        self._logger.info(f"[{self.name}] {message}")
    
    def step(self, message: str):
        """
        Step-level log (shown in DETAILED and DEBUG modes)
        Use for individual step events within the pipeline
        """
        if self.level in [LogLevel.DETAILED, LogLevel.DEBUG]:
            self._logger.info(f"[{self.name}] {message}")
    
    def detail(self, message: str):
        """
        Detailed log (shown in DEBUG mode only)
        Use for internal details and debugging information
        """
        if self.level == LogLevel.DEBUG:
            self._logger.debug(f"[{self.name}] {message}")
    
    def debug(self, message: str):
        """
        Debug log - backward compatibility alias for detail()
        Shown in DEBUG mode only
        """
        self.detail(message)
    
    def separator(self, char="=", length=100):
        """Print separator line (shown in all modes)"""
        self._logger.info(char * length)
    
    def section_start(self, title: str):
        """Start a major section (shown in all modes)"""
        self.separator("=")
        self._logger.info(f"[{self.name}] ========== {title} ==========")
        self.separator("=")
    
    def section_end(self, title: str = None):
        """End a major section (shown in all modes)"""
        if title:
            self.separator("-")
            self._logger.info(f"[{self.name}] ========== {title} 结束 ==========")
            self.separator("-")
        else:
            self.separator("-")
    
    def info(self, message: str):
        """General info log (shown in all modes)"""
        self._logger.info(f"[{self.name}] {message}")
    
    def warning(self, message: str):
        """Warning log (shown in all modes)"""
        self._logger.warning(f"[{self.name}] {message}")
    
    def error(self, message: str):
        """Error log (shown in all modes)"""
        self._logger.error(f"[{self.name}] {message}")


# Global logging level
_GLOBAL_LOG_LEVEL = LogLevel.BASIC


def set_global_log_level(level: LogLevel):
    """
    Set global logging level for all ContextMind loggers
    
    Args:
        level: LogLevel.BASIC, LogLevel.DETAILED, or LogLevel.DEBUG
    """
    global _GLOBAL_LOG_LEVEL
    _GLOBAL_LOG_LEVEL = level


def get_global_log_level() -> LogLevel:
    """Get current global logging level"""
    return _GLOBAL_LOG_LEVEL


def get_logger(name: str, level: LogLevel = None) -> ContextMindLogger:
    """
    Get a ContextMind logger instance
    
    Args:
        name: Logger name (usually module name)
        level: Logging level (uses global level if not specified)
        
    Returns:
        ContextMindLogger instance
    """
    if level is None:
        level = _GLOBAL_LOG_LEVEL
    return ContextMindLogger(name, level)


def setup_logging(level: LogLevel = LogLevel.BASIC, python_log_level=None):
    """
    Setup ContextMind logging configuration
    
    Args:
        level: ContextMind logging level (BASIC, DETAILED, or DEBUG)
        python_log_level: Python logging level (defaults based on ContextMind level)
    """
    # Set global ContextMind log level
    set_global_log_level(level)
    
    # Map ContextMind level to Python logging level
    if python_log_level is None:
        if level == LogLevel.DEBUG:
            python_log_level = logging.DEBUG
        else:
            python_log_level = logging.INFO
    
    # Configure Python logging
    logging.basicConfig(
        level=python_log_level,
        format='[%(asctime)s] %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        force=True  # Override any existing configuration
    )


# Export logging levels for backward compatibility
INFO = logging.INFO
DEBUG = logging.DEBUG
