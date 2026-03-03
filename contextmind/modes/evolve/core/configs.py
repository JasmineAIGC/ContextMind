"""用于检索、提取、压缩和记忆系统的配置数据类。"""

from dataclasses import dataclass, field


@dataclass
class RetrievalConfig:
    """上下文检索配置"""
    top_k: int = 5
    min_score: float = 0.5
    use_semantic: bool = True
    use_keyword: bool = False
    min_overlap_chars: int = 3
    base_score: float = 0.3
    relevance_threshold: float = 0.0
    enable_recency_boost: bool = True
    recency_weight: float = 0.2
    recency_days_threshold: int = 7
    enable_deduplication: bool = True
    similarity_threshold_for_dedup: float = 0.95
    max_limit: int = 100


@dataclass
class ExtractionConfig:
    """知识提取配置"""
    extraction_method: str = "rule"  # 'rule' 或 'llm'
    min_confidence: float = 0.5  # 降低阈值，允许提取更多潜在有价值的信息
    max_phrase_length: int = 100  # 增加最大短语长度，允许提取更长的描述
    extract_preferences: bool = True
    extract_facts: bool = True
    extract_events: bool = True
    extract_entities: bool = True
    extract_relationships: bool = True
    preference_confidence: float = 0.8
    fact_confidence: float = 0.7
    event_confidence: float = 0.6
    entity_confidence: float = 0.75
    relationship_confidence: float = 0.7
    llm_temperature: float = 0.1  # 较低的温度确保提取的稳定性
    llm_max_tokens: int = 1000
    llm_batch_size: int = 10


@dataclass
class CompressionConfig:
    """上下文压缩配置"""
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


DEFAULT_MEMORY_CONFIG = MemorySystemConfig()
