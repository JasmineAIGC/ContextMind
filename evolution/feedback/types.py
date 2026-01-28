"""
反馈系统类型定义

定义反馈收集系统中使用的数据类型和枚举。
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import time


class FeedbackSource(Enum):
    """反馈来源"""
    EXPLICIT_USER = "explicit_user"          # 显式用户反馈（点赞/点踩）
    CORRECTION = "correction"                # 用户纠正
    RATING = "rating"                        # 评分
    IMPLICIT_CONTINUATION = "implicit_cont"  # 隐式：对话延续
    IMPLICIT_REPETITION = "implicit_rep"     # 隐式：重复提问
    IMPLICIT_CLARIFICATION = "implicit_clar" # 隐式：澄清
    IMPLICIT_TOPIC_SHIFT = "implicit_topic"  # 隐式：主题切换
    IMPLICIT_RESPONSE_TIME = "implicit_time" # 隐式：响应时间
    AUTO_LLM_EVAL = "auto_llm"              # 自动：LLM评估
    AUTO_CONSISTENCY = "auto_consistency"    # 自动：一致性检查
    AUTO_FACT_CHECK = "auto_fact"           # 自动：事实验证


class FeedbackType(Enum):
    """反馈类型"""
    POSITIVE = "positive"      # 正面反馈
    NEGATIVE = "negative"      # 负面反馈
    NEUTRAL = "neutral"        # 中性反馈
    CORRECTION = "correction"  # 纠正反馈


@dataclass
class FeedbackEvent:
    """
    反馈事件
    
    记录一次完整的反馈信息，包括来源、类型、强度等。
    """
    memory_ids: List[str]                    # 涉及的记忆ID列表
    feedback_type: FeedbackType              # 反馈类型
    source: FeedbackSource                   # 反馈来源
    timestamp: float = field(default_factory=time.time)
    
    # 可选字段
    strength: float = 1.0                    # 反馈强度 (0-1)
    confidence: float = 1.0                  # 置信度 (0-1)
    details: Optional[Dict[str, Any]] = None # 详细信息
    context: Optional[Dict[str, Any]] = None # 上下文信息
    
    def __post_init__(self):
        if self.details is None:
            self.details = {}
        if self.context is None:
            self.context = {}


@dataclass
class ObservationEvent:
    """
    观测事件
    
    记录对话过程中的观测信息，如检索、使用等。
    """
    memory_id: str                           # 记忆ID
    event_type: str                          # 事件类型: retrieved, used, ignored
    timestamp: float = field(default_factory=time.time)
    
    # 上下文信息
    query: Optional[str] = None              # 触发的查询
    relevance_score: Optional[float] = None  # 相关性分数
    position: Optional[int] = None           # 在检索结果中的位置
    used_in_prompt: bool = False             # 是否被用于prompt
    contributed_to_response: bool = False    # 是否对回复有贡献
    
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationTurn:
    """
    对话轮次
    
    记录单次对话交互的完整信息，用于后续分析。
    """
    turn_id: str
    user_query: str
    system_response: str
    timestamp: float = field(default_factory=time.time)
    
    # 记忆相关
    retrieved_memory_ids: List[str] = field(default_factory=list)
    used_memory_ids: List[str] = field(default_factory=list)
    ignored_memory_ids: List[str] = field(default_factory=list)
    
    # 元数据
    response_time: Optional[float] = None    # 生成回复耗时
    user_response_time: Optional[float] = None  # 用户回复耗时
    topic: Optional[str] = None
    
    # 反馈
    feedbacks: List[FeedbackEvent] = field(default_factory=list)
    observations: List[ObservationEvent] = field(default_factory=list)


@dataclass
class ConversationSession:
    """
    对话会话
    
    记录完整的对话会话信息。
    """
    session_id: str
    user_id: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    
    turns: List[ConversationTurn] = field(default_factory=list)
    
    # 会话级统计
    total_feedbacks: int = 0
    positive_feedbacks: int = 0
    negative_feedbacks: int = 0
    
    # 会话级评分（可选）
    overall_rating: Optional[float] = None
    
    def add_turn(self, turn: ConversationTurn):
        """添加对话轮次"""
        self.turns.append(turn)
    
    def get_last_turn(self) -> Optional[ConversationTurn]:
        """获取最后一轮对话"""
        return self.turns[-1] if self.turns else None
    
    def close(self):
        """结束会话"""
        self.end_time = time.time()
