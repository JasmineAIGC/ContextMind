"""
配置数据模型 (v0.4.1)

用于检索、提取、压缩和记忆系统的配置数据类。
在v0.4.1模块化重构期间从models.py中提取，以实现更好的组织结构。
"""

from dataclasses import dataclass, field


@dataclass
class RetrievalConfig:
    """上下文检索配置"""
    top_k: int = 5
    min_score: float = 0.5
    use_semantic: bool = True
    use_keyword: bool = False
    
    # 语义检索参数
    min_overlap_chars: int = 3  # 最小字符重叠数
    base_score: float = 0.3  # 基础相关性分数
    relevance_threshold: float = 0.0  # 相关性阈值 (0表示不使用阈值过滤)
    
    # 新近性加权
    enable_recency_boost: bool = True  # 是否启用新近性加权
    recency_weight: float = 0.2  # 新近性权重
    recency_days_threshold: int = 7  # 新近性天数阈值
    
    # 去重和限制
    enable_deduplication: bool = True  # 是否启用去重
    similarity_threshold_for_dedup: float = 0.95  # 去重相似度阈值
    max_limit: int = 100  # 最大返回数量


@dataclass
class ExtractionConfig:
    """知识提取配置"""
    # 提取方式: 'rule' (规则提取) 或 'llm' (LLM 自动提取)
    extraction_method: str = "rule"  # 'rule' 或 'llm'
    
    # 通用配置
    min_confidence: float = 0.5  # 降低阈值，允许提取更多潜在有价值的信息
    max_phrase_length: int = 100  # 增加最大短语长度，允许提取更长的描述
    
    # 提取类型开关
    extract_preferences: bool = True
    extract_facts: bool = True
    extract_events: bool = True
    extract_entities: bool = True  # 实体提取 (人名、地名等)
    extract_relationships: bool = True  # 关系提取 (例如: "张三是李四的同事")
    
    # 各类知识的置信度设置
    preference_confidence: float = 0.8
    fact_confidence: float = 0.7
    event_confidence: float = 0.6
    entity_confidence: float = 0.75
    relationship_confidence: float = 0.7
    
    # LLM 提取专用配置
    llm_temperature: float = 0.1  # 较低的温度确保提取的稳定性
    llm_max_tokens: int = 1000  # 提取结果的最大 token 数
    llm_batch_size: int = 10  # 批量处理消息数


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


# 默认配置
DEFAULT_MEMORY_CONFIG = MemorySystemConfig()
