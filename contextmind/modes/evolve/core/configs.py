"""用于检索、提取、压缩和记忆系统的配置数据类。"""

from dataclasses import dataclass, field


@dataclass
class RetrievalConfig:
    """上下文检索配置 — 控制从记忆库检索候选项的评分、过滤和去重流程。"""
    top_k: int = 5
    min_score: float = 0.5  # 0.5 在召回率与噪声之间取得平衡；低于此值的候选通常不相关
    use_semantic: bool = True
    use_keyword: bool = False
    min_overlap_chars: int = 3  # 关键词评分所需的最小字符重叠量
    base_score: float = 0.3  # 每个候选的基础分，确保弱匹配也不会被赋零分
    relevance_threshold: float = 0.0  # 0.0 禁用阈值过滤；设置大于 0 可强制最低相关度要求
    enable_recency_boost: bool = True
    recency_weight: float = 0.2  # 近期性在最终评分中所占比例；保持低值使相关性居主导
    recency_days_threshold: int = 7  # 7 天内访问过的记忆被视为"近期"记忆
    enable_deduplication: bool = True
    similarity_threshold_for_dedup: float = 0.95  # 超过此余弦相似度的两个候选将被合并为重复项
    max_limit: int = 100  # 从存储中获取的候选数量上限，防止内存扫描开销过大


@dataclass
class ExtractionConfig:
    """知识提取配置 — 控制从对话消息中提取结构化知识的方法、置信度门槛和类型开关。"""
    extraction_method: str = "rule"  # 'rule'：快速正则/启发式管道；'llm'：较慢但能处理复杂表达
    min_confidence: float = 0.5  # 降至 0.5 以捕获更多潜在有用信息；提高可减少噪声
    max_phrase_length: int = 100  # 允许提取更长的描述性短语；防止格式错误输入导致提取失控
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
    llm_temperature: float = 0.1  # 低温度确保提取结果的确定性和稳定性（减少幻觉属性）
    llm_max_tokens: int = 1000
    llm_batch_size: int = 10


@dataclass
class CompressionConfig:
    """上下文压缩配置"""
    max_tokens: int = 2000
    strategy: str = "simple"  # 'simple'：按时间窗口截断；可继承 OptimizationStrategy 实现自定义策略


@dataclass
class SummarizationConfig:
    """对话摘要配置"""
    enabled: bool = False  # 默认关闭以避免额外的 LLM 调用；长会话场景可启用
    max_turns: int = 10  # 超过此轮数后触发摘要生成


@dataclass
class MemorySystemConfig:
    """记忆系统配置"""
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    compression: CompressionConfig = field(default_factory=CompressionConfig)
    summarization: SummarizationConfig = field(default_factory=SummarizationConfig)


DEFAULT_MEMORY_CONFIG = MemorySystemConfig()
