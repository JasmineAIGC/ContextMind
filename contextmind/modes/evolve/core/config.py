"""
Evolve 核心类型与配置

将枚举类型（KnowledgeType、MemoryType、MessageRole、ContextSource）
与系统配置数据类（RetrievalConfig、ExtractionConfig、CompressionConfig 等）
合并为单一模块，减少文件碎片化。
"""

from enum import Enum
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# 枚举类型（原 types.py）
# ---------------------------------------------------------------------------

class KnowledgeType(str, Enum):
    """
    从对话中提取的知识类型 (40种)

    分为10大类：用户画像、认知、行为、意图、关系、知识、情感、策略、上下文、多轮对话
    """
    # 原有9种基础类型
    PREFERENCE  = "preference"   # 用户偏好（喜欢/不喜欢）
    FACT        = "fact"         # 关于用户或主题的事实
    EVENT       = "event"        # 事件或行为
    INTENT      = "intent"       # 用户意图（想要做什么）
    NEED        = "need"         # 用户需求（需要什么）
    OPINION     = "opinion"      # 用户观点/看法
    HABIT       = "habit"        # 用户习惯
    CONSTRAINT  = "constraint"   # 约束条件（如预算、时间限制）
    INTEREST    = "interest"     # 用户兴趣

    # 1. 用户画像类 (User Profile) - 4种
    USER_INFO = "user_info"
    PERSONALITY = "personality"
    VALUES = "values"
    LIFESTYLE = "lifestyle"

    # 2. 认知类 (Cognitive) - 3种新增（opinion已有）
    BELIEF = "belief"
    ATTITUDE = "attitude"
    VALUE_JUDGMENT = "value_judgment"

    # 3. 行为类 (Behavioral) - 3种新增（event, habit已有）
    EXPERIENCE = "experience"
    SKILL = "skill"
    ACHIEVEMENT = "achievement"

    # 4. 意图类 (Intentional) - 3种新增（intent, need已有）
    GOAL = "goal"
    PLAN = "plan"
    EXPECTATION = "expectation"

    # 5. 关系类 (Relational) - 3种
    RELATIONSHIP = "relationship"
    EMOTIONAL_CONNECTION = "emotional_connection"
    INFLUENCE = "influence"

    # 6. 知识类 (Epistemic) - 3种新增（fact已有）
    PROCEDURAL = "procedural"
    DOMAIN_KNOWLEDGE = "domain_knowledge"
    COMMON_SENSE = "common_sense"

    # 7. 情感类 (Emotional) - 2种新增（preference已有）
    EMOTION = "emotion"
    SENTIMENT = "sentiment"

    # 8. 策略类 (Strategic) - 4种
    SOLUTION = "solution"
    STRATEGY = "strategy"
    BEST_PRACTICE = "best_practice"
    LESSON_LEARNED = "lesson_learned"

    # 9. 上下文类 (Contextual) - 2种新增（constraint, interest已有）
    TOPIC = "topic"
    SCENARIO = "scenario"

    # 10. 多轮对话类 (Multi-turn) - 4种
    CONVERSATION_PATTERN = "conversation_pattern"
    TOPIC_EVOLUTION = "topic_evolution"
    PROBLEM_SOLUTION_SEQ = "problem_solution_sequence"
    CAUSALITY = "causality"


class MemoryType(str, Enum):
    """记忆存储类型"""
    SEMANTIC = "semantic"      # 语义/向量存储
    KEYWORD = "keyword"        # 关键词存储
    STRUCTURED = "structured"  # 结构化数据存储


class MessageRole(str, Enum):
    """对话消息角色"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ContextSource(str, Enum):
    """上下文项来源——用于在上下文组装时确定优先级和过滤条件。"""
    MEMORY = "memory"    # 从历史对话中提取的长期知识
    RAG = "rag"          # 从外部文档库检索的内容
    HISTORY = "history"  # 当前会话的近期消息


# ---------------------------------------------------------------------------
# 配置数据类（原 configs.py）
# ---------------------------------------------------------------------------

@dataclass
class RetrievalConfig:
    """上下文检索配置 — 控制从记忆库检索候选项的评分、过滤和去重流程。"""
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
    """知识提取配置 — 控制从对话消息中提取结构化知识的方法、置信度门槛和类型开关。"""
    extraction_method: str = "rule"
    min_confidence: float = 0.5
    max_phrase_length: int = 100
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
    llm_temperature: float = 0.1
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


__all__ = [
    # 枚举类型
    "KnowledgeType",
    "MemoryType",
    "MessageRole",
    "ContextSource",
    # 配置数据类
    "RetrievalConfig",
    "ExtractionConfig",
    "CompressionConfig",
    "SummarizationConfig",
    "MemorySystemConfig",
    "DEFAULT_MEMORY_CONFIG",
]
