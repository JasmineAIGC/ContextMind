"""用于检索、提取、压缩和记忆系统的配置数据类。"""

from dataclasses import dataclass, field


@dataclass
class RetrievalConfig:
    """上下文检索配置 — 控制从记忆库检索候选项的评分、过滤和去重流程。"""
    top_k: int = 5
    min_score: float = 0.5  # 0.5 balances recall vs. noise; below this candidates are usually irrelevant
    use_semantic: bool = True
    use_keyword: bool = False
    min_overlap_chars: int = 3  # minimum character overlap required to award keyword score
    base_score: float = 0.3  # baseline added to every candidate so even weak matches aren't zeroed out
    relevance_threshold: float = 0.0  # 0.0 disables threshold filtering; set >0 to enforce minimum relevance
    enable_recency_boost: bool = True
    recency_weight: float = 0.2  # fraction of final score contributed by recency; keep low so relevance dominates
    recency_days_threshold: int = 7  # items accessed within 7 days are considered "recent"
    enable_deduplication: bool = True
    similarity_threshold_for_dedup: float = 0.95  # cosine similarity above which two candidates are merged as duplicates
    max_limit: int = 100  # hard cap on candidates fetched from storage to bound memory scan cost


@dataclass
class ExtractionConfig:
    """知识提取配置 — 控制从对话消息中提取结构化知识的方法、置信度门槛和类型开关。"""
    extraction_method: str = "rule"  # 'rule': fast regex/heuristic pipeline; 'llm': slower but handles complex phrasing
    min_confidence: float = 0.5  # lowered to 0.5 to capture more potentially useful information; raise to reduce noise
    max_phrase_length: int = 100  # allows longer descriptive phrases; prevents runaway extraction on malformed input
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
    llm_temperature: float = 0.1  # low temperature for deterministic, stable extractions (avoids hallucinated attributes)
    llm_max_tokens: int = 1000
    llm_batch_size: int = 10


@dataclass
class CompressionConfig:
    """上下文压缩配置"""
    max_tokens: int = 2000
    strategy: str = "simple"  # 'simple': recency-window truncation; extend with custom OptimizationStrategy subclasses


@dataclass
class SummarizationConfig:
    """对话摘要配置"""
    enabled: bool = False  # disabled by default to avoid extra LLM calls; enable for long-running sessions
    max_turns: int = 10  # trigger summarization once conversation exceeds this many turns


@dataclass
class MemorySystemConfig:
    """记忆系统配置"""
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    compression: CompressionConfig = field(default_factory=CompressionConfig)
    summarization: SummarizationConfig = field(default_factory=SummarizationConfig)


DEFAULT_MEMORY_CONFIG = MemorySystemConfig()
