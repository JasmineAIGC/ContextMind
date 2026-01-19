"""
Memory System Configuration

Centralized configuration for memory extraction, retrieval, and optimization.
Makes the system more configurable and reduces hardcoded values.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExtractionConfig:
    """Configuration for knowledge extraction"""
    
    # Confidence thresholds
    min_confidence: float = 0.5
    preference_confidence: float = 0.85
    fact_confidence: float = 0.75
    event_confidence: float = 0.70
    
    # Extraction limits
    max_facts_per_message: int = 5
    max_preferences_per_message: int = 3
    
    # Pattern matching
    min_phrase_length: int = 2
    max_phrase_length: int = 20


@dataclass
class RetrievalConfig:
    """Configuration for memory retrieval"""
    
    # Retrieval limits
    default_limit: int = 5
    max_limit: int = 20
    
    # Scoring thresholds
    relevance_threshold: float = 0.3  # Minimum score to include memory
    high_relevance_threshold: float = 0.7  # Threshold for high relevance
    
    # Similarity calculation
    min_overlap_chars: int = 1  # Minimum character overlap for relevance
    base_score: float = 0.1  # Base score for any memory
    
    # Recency weighting
    enable_recency_boost: bool = True
    recency_weight: float = 0.2  # How much to boost recent memories (0-1)
    recency_days_threshold: int = 7  # Days within which memories get boost
    
    # Deduplication
    enable_deduplication: bool = True
    similarity_threshold_for_dedup: float = 0.9  # >0.9 similarity = duplicate


@dataclass
class SummarizationConfig:
    """Configuration for conversation summarization"""
    
    # Summarization triggers
    recent_turns: int = 3  # Number of recent turns to keep in full
    summarize_threshold: int = 5  # Conversation length to trigger summarization
    
    # Summarization behavior
    max_summary_length: int = 100  # Maximum characters for summary
    extract_top_keywords: int = 3  # Number of keywords to extract
    
    # LLM summarization (if available)
    use_llm_summarization: bool = False
    llm_max_turns_per_call: int = 10  # Max turns to send to LLM at once


@dataclass
class CompressionConfig:
    """Configuration for context compression"""
    
    # Item limits
    default_max_items: int = 10
    default_max_tokens: int = 4000
    
    # Source-aware allocation (percentages)
    min_memory_items: int = 2
    min_knowledge_items: int = 1
    memory_quota_percentage: float = 0.20  # 20% for memory
    knowledge_quota_percentage: float = 0.10  # 10% for knowledge
    
    # Truncation behavior
    prefer_recent: bool = True  # Prefer recent items when truncating
    preserve_high_score: bool = True  # Always keep high-scoring items


@dataclass
class MemorySystemConfig:
    """
    Complete memory system configuration
    
    Centralized config for all memory-related operations.
    Can be loaded from file, environment, or passed programmatically.
    """
    
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    summarization: SummarizationConfig = field(default_factory=SummarizationConfig)
    compression: CompressionConfig = field(default_factory=CompressionConfig)
    
    @classmethod
    def from_dict(cls, config_dict: dict) -> 'MemorySystemConfig':
        """Create config from dictionary"""
        return cls(
            extraction=ExtractionConfig(**config_dict.get('extraction', {})),
            retrieval=RetrievalConfig(**config_dict.get('retrieval', {})),
            summarization=SummarizationConfig(**config_dict.get('summarization', {})),
            compression=CompressionConfig(**config_dict.get('compression', {})),
        )
    
    def to_dict(self) -> dict:
        """Convert config to dictionary"""
        return {
            'extraction': self.extraction.__dict__,
            'retrieval': self.retrieval.__dict__,
            'summarization': self.summarization.__dict__,
            'compression': self.compression.__dict__,
        }


# Global default configuration
DEFAULT_MEMORY_CONFIG = MemorySystemConfig()
