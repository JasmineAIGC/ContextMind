"""
反馈系统（Feedback System）

定义反馈和观测数据类型，并提供反馈收集器的具体实现。

数据类型（Data Types）：
  FeedbackSource           — 反馈来源枚举
  FeedbackEvent            — 单次反馈事件记录
  ObservationEvent         — 对话观测事件记录
  ConversationTurn         — 单轮对话完整记录
  ConversationSession      — 完整会话记录

收集器（Collectors）：
  ObservationCollector     — 收集检索/使用/忽略等记忆观测事件
  FeedbackCollector        — 收集显式和自动反馈，更新适应度
  ImplicitFeedbackAnalyzer — 从对话行为推断隐式反馈
"""

import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from contextmind.infra.logger import get_logger
from ..memory.fitness import FitnessCalculator, FeedbackType
from ..core.data_models import ContextItem

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 枚举类型
# ---------------------------------------------------------------------------

class FeedbackSource(Enum):
    """反馈来源"""
    EXPLICIT_USER = "explicit_user"
    CORRECTION = "correction"
    RATING = "rating"
    IMPLICIT_CONTINUATION = "implicit_cont"
    IMPLICIT_REPETITION = "implicit_rep"
    IMPLICIT_CLARIFICATION = "implicit_clar"
    IMPLICIT_TOPIC_SHIFT = "implicit_topic"
    IMPLICIT_RESPONSE_TIME = "implicit_time"
    AUTO_LLM_EVAL = "auto_llm"
    AUTO_CONSISTENCY = "auto_consistency"
    AUTO_FACT_CHECK = "auto_fact"


# FeedbackType 从 memory.fitness 导入，避免重复定义
# from ..memory.fitness import FeedbackType  (已在顶部导入)


# ---------------------------------------------------------------------------
# 数据类型
# ---------------------------------------------------------------------------

@dataclass
class FeedbackEvent:
    """
    记录一次完整的反馈信息，包括来源、类型、强度等。

    strength 表示信号强度（0-1），用于加权适应度更新，
    confidence 表示该反馈信号本身的可信度（隐式信号通常低于显式信号）。
    """
    memory_ids: List[str]
    feedback_type: FeedbackType
    source: FeedbackSource
    timestamp: float = field(default_factory=time.time)
    strength: float = 1.0
    confidence: float = 1.0
    details: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}
        if self.context is None:
            self.context = {}


@dataclass
class ObservationEvent:
    """对话观测事件，记录对话历史长度、话题、意图、上下文相关性和质量等信息，用于评估记忆在对话中的实际价值。"""
    turn_id: str
    event_type: str
    timestamp: float = field(default_factory=time.time)
    dialogue_history_length: int = 0
    current_topic: Optional[str] = None
    topic_changed: bool = False
    identified_intent: Optional[str] = None
    intent_confidence: float = 0.0
    intent_changed: bool = False
    context_items_count: int = 0
    context_relevance: float = 0.0
    referenced_history: bool = False
    coherence_score: float = 0.0
    understanding_level: float = 0.0
    related_memory_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationTurn:
    """记录单次对话交互的完整信息：内容、理解、质量和关联记忆。"""
    turn_id: str
    user_query: str
    system_response: str
    timestamp: float = field(default_factory=time.time)
    identified_intent: Optional[str] = None
    intent_confidence: float = 0.0
    current_topic: Optional[str] = None
    topic_changed: bool = False
    coherence_score: float = 0.0
    understanding_level: float = 0.0
    relevant_memory_ids: List[str] = field(default_factory=list)
    response_time: Optional[float] = None
    user_response_time: Optional[float] = None
    feedbacks: List[FeedbackEvent] = field(default_factory=list)
    observations: List[ObservationEvent] = field(default_factory=list)


@dataclass
class ConversationSession:
    """记录完整的对话会话信息。"""
    session_id: str
    user_id: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    turns: List[ConversationTurn] = field(default_factory=list)
    total_feedbacks: int = 0
    positive_feedbacks: int = 0
    negative_feedbacks: int = 0
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


# ---------------------------------------------------------------------------
# 收集器实现
# ---------------------------------------------------------------------------

class ObservationCollector:
    """收集对话过程中的观测数据：检索、使用、忽略等事件。"""

    def __init__(self, fitness_calculator: Optional[FitnessCalculator] = None):
        self.fitness_calculator = fitness_calculator or FitnessCalculator()
        self.observations: List[ObservationEvent] = []
        logger.info("[ObservationCollector] 初始化完成")

    def observe_retrieval(
        self,
        memory: ContextItem,
        query: str,
        position: int = 0
    ) -> ObservationEvent:
        """
        观测：记忆被检索。

        Args:
            memory: 被检索的记忆
            query: 触发检索的查询
            position: 在检索结果中的位置
        """
        memory_id = memory.metadata.get('id', str(id(memory))) if memory.metadata else str(id(memory))
        self.fitness_calculator.observe_retrieval(memory)
        event = ObservationEvent(
            turn_id=memory_id,
            event_type="retrieved",
            context_relevance=memory.score,
            related_memory_ids=[memory_id],
            metadata={'query': query, 'position': position},
        )
        self.observations.append(event)
        logger.debug(f"[Observation] 检索: memory={memory_id[:8]}, score={memory.score:.2f}")
        return event

    def observe_usage(
        self,
        memory: ContextItem,
        used_in_prompt: bool = True,
        contributed: bool = True
    ) -> ObservationEvent:
        """观测：记忆被实际使用。"""
        memory_id = memory.metadata.get('id', str(id(memory))) if memory.metadata else str(id(memory))
        self.fitness_calculator.observe_usage(memory)
        event = ObservationEvent(
            turn_id=memory_id,
            event_type="used",
            related_memory_ids=[memory_id],
            metadata={'used_in_prompt': used_in_prompt, 'contributed': contributed},
        )
        self.observations.append(event)
        logger.debug(f"[Observation] 使用: memory={memory_id[:8]}")
        return event

    def observe_ignored(
        self,
        memory: ContextItem,
        reason: Optional[str] = None
    ) -> ObservationEvent:
        """观测：记忆被检索但未使用。"""
        memory_id = memory.metadata.get('id', str(id(memory))) if memory.metadata else str(id(memory))
        self.fitness_calculator.observe_ignored(memory)
        event = ObservationEvent(
            turn_id=memory_id,
            event_type="ignored",
            related_memory_ids=[memory_id],
            metadata={'reason': reason} if reason else {},
        )
        self.observations.append(event)
        logger.debug(f"[Observation] 忽略: memory={memory_id[:8]}")
        return event

    def get_observations(self, memory_id: Optional[str] = None) -> List[ObservationEvent]:
        """获取观测事件，可按 memory_id 过滤。"""
        if memory_id:
            return [obs for obs in self.observations if memory_id in obs.related_memory_ids]
        return self.observations

    def clear_observations(self):
        """清空观测记录"""
        self.observations = []


class FeedbackCollector:
    """收集显式和自动反馈，并应用到记忆的适应度更新。"""

    def __init__(self, fitness_calculator: Optional[FitnessCalculator] = None):
        self.fitness_calculator = fitness_calculator or FitnessCalculator()
        self.feedbacks: List[FeedbackEvent] = []
        logger.info("[FeedbackCollector] 初始化完成")

    def collect_positive_feedback(
        self,
        memories: List[ContextItem],
        source: FeedbackSource = FeedbackSource.EXPLICIT_USER,
        strength: float = 1.0,
        details: Optional[Dict[str, Any]] = None
    ) -> FeedbackEvent:
        """收集正面反馈。"""
        memory_ids = [mem.metadata.get('id', str(id(mem))) if mem.metadata else str(id(mem)) for mem in memories]
        for memory in memories:
            self.fitness_calculator.record_positive_feedback(memory)
        event = FeedbackEvent(
            memory_ids=memory_ids,
            feedback_type=FeedbackType.POSITIVE,
            source=source,
            strength=strength,
            details=details or {}
        )
        self.feedbacks.append(event)
        logger.info(f"[Feedback] 正面反馈: {len(memories)}条记忆, 来源={source.value}")
        return event

    def collect_negative_feedback(
        self,
        memories: List[ContextItem],
        source: FeedbackSource = FeedbackSource.EXPLICIT_USER,
        strength: float = 1.0,
        details: Optional[Dict[str, Any]] = None
    ) -> FeedbackEvent:
        """收集负面反馈。"""
        memory_ids = [mem.metadata.get('id', str(id(mem))) if mem.metadata else str(id(mem)) for mem in memories]
        for memory in memories:
            self.fitness_calculator.record_negative_feedback(memory)
        event = FeedbackEvent(
            memory_ids=memory_ids,
            feedback_type=FeedbackType.NEGATIVE,
            source=source,
            strength=strength,
            details=details or {}
        )
        self.feedbacks.append(event)
        logger.info(f"[Feedback] 负面反馈: {len(memories)}条记忆, 来源={source.value}")
        return event

    def collect_correction(
        self,
        memories: List[ContextItem],
        correction_info: str,
        details: Optional[Dict[str, Any]] = None
    ) -> FeedbackEvent:
        """收集纠正反馈。"""
        memory_ids = [mem.metadata.get('id', str(id(mem))) if mem.metadata else str(id(mem)) for mem in memories]
        for memory in memories:
            self.fitness_calculator.record_correction(memory)
        event = FeedbackEvent(
            memory_ids=memory_ids,
            feedback_type=FeedbackType.CORRECTION,
            source=FeedbackSource.CORRECTION,
            details={'correction': correction_info, **(details or {})}
        )
        self.feedbacks.append(event)
        logger.info(f"[Feedback] 纠正反馈: {len(memories)}条记忆")
        return event

    def collect_rating(
        self,
        memories: List[ContextItem],
        rating: float,  # 0-1；>= 0.7 正面，<= 0.3 负面，中间为中性
        details: Optional[Dict[str, Any]] = None
    ) -> FeedbackEvent:
        """收集评分反馈，将 0-1 区间的评分映射到正/负/中性三类反馈。"""
        if rating >= 0.7:
            feedback_type = FeedbackType.POSITIVE
            for mem in memories:
                self.fitness_calculator.record_positive_feedback(mem)
        elif rating <= 0.3:
            feedback_type = FeedbackType.NEGATIVE
            for mem in memories:
                self.fitness_calculator.record_negative_feedback(mem)
        else:
            feedback_type = FeedbackType.NEUTRAL

        memory_ids = [mem.metadata.get('id', str(id(mem))) if mem.metadata else str(id(mem)) for mem in memories]
        event = FeedbackEvent(
            memory_ids=memory_ids,
            feedback_type=feedback_type,
            source=FeedbackSource.RATING,
            strength=abs(rating - 0.5) * 2,  # 偏离中立值(0.5)的程度线性映射为强度
            details={'rating': rating, **(details or {})}
        )
        self.feedbacks.append(event)
        logger.info(f"[Feedback] 评分反馈: rating={rating:.2f}, type={feedback_type.value}")
        return event

    def update_contribution_score(self, memory: ContextItem, score: float):
        """更新记忆的贡献度评分 (0-1)。"""
        self.fitness_calculator.update_contribution(memory, score)
        memory_id = memory.metadata.get('id', '') if memory.metadata else ''
        logger.debug(f"[Feedback] 更新贡献度: memory={memory_id[:8]}, score={score:.2f}")

    def get_feedbacks(
        self,
        memory_id: Optional[str] = None,
        feedback_type: Optional[FeedbackType] = None
    ) -> List[FeedbackEvent]:
        """获取反馈事件，可按 memory_id 或 feedback_type 过滤。"""
        result = self.feedbacks
        if memory_id:
            result = [fb for fb in result if memory_id in fb.memory_ids]
        if feedback_type:
            result = [fb for fb in result if fb.feedback_type == feedback_type]
        return result

    def get_feedback_stats(self) -> Dict[str, int]:
        """获取反馈统计。"""
        stats = {'total': len(self.feedbacks), 'positive': 0, 'negative': 0, 'neutral': 0, 'correction': 0}
        for fb in self.feedbacks:
            if fb.feedback_type == FeedbackType.POSITIVE:
                stats['positive'] += 1
            elif fb.feedback_type == FeedbackType.NEGATIVE:
                stats['negative'] += 1
            elif fb.feedback_type == FeedbackType.NEUTRAL:
                stats['neutral'] += 1
            elif fb.feedback_type == FeedbackType.CORRECTION:
                stats['correction'] += 1
        return stats


class ImplicitFeedbackAnalyzer:
    """
    从对话行为中推断隐式反馈。

    这些规则均为启发式信号，置信度低于显式反馈，
    主要用于在用户不主动评分时提供低成本的质量信号。
    """

    def __init__(self, feedback_collector: FeedbackCollector):
        self.feedback_collector = feedback_collector
        logger.info("[ImplicitFeedbackAnalyzer] 初始化完成")

    def analyze_continuation(
        self,
        current_turn: ConversationTurn,
        previous_turn: Optional[ConversationTurn]
    ):
        """分析对话延续行为。5分钟内继续对话视为正面信号。"""
        if not previous_turn or not previous_turn.relevant_memory_ids:
            return
        if current_turn.timestamp - previous_turn.timestamp < 300:  # 5分钟内
            logger.debug("[ImplicitFeedback] 对话延续 - 弱正面信号")
            # TODO: 获取记忆对象并应用反馈

    def analyze_repetition(
        self,
        current_turn: ConversationTurn,
        previous_turns: List[ConversationTurn]
    ):
        """
        分析重复提问行为。

        与最近3轮存在3个以上共同词时判定为重复，说明之前的回答未能满足用户需求。
        """
        if not previous_turns:
            return
        current_query_lower = current_turn.user_query.lower()
        for prev_turn in previous_turns[-3:]:
            prev_query_lower = prev_turn.user_query.lower()
            common_words = set(current_query_lower.split()) & set(prev_query_lower.split())
            if len(common_words) >= 3:
                logger.debug("[ImplicitFeedback] 重复提问 - 负面信号")
                # TODO: 对上一轮使用的记忆应用负面反馈
                break

    def analyze_clarification(
        self,
        current_turn: ConversationTurn,
        previous_turn: Optional[ConversationTurn]
    ):
        """分析澄清行为，检测用户纠正关键词。"""
        if not previous_turn:
            return
        clarification_keywords = ['不是', '不对', '我是说', '我的意思是', '澄清']
        if any(kw in current_turn.user_query for kw in clarification_keywords):
            logger.debug("[ImplicitFeedback] 澄清行为 - 负面信号")
            # TODO: 对上一轮使用的记忆应用负面反馈

    def analyze_response_time(
        self,
        current_turn: ConversationTurn,
        previous_turn: Optional[ConversationTurn]
    ):
        """分析用户响应时间，快速回复(<5s)为弱正面信号，慢回复(>60s)为弱负面信号。"""
        if not previous_turn:
            return
        response_time = current_turn.timestamp - previous_turn.timestamp
        if response_time < 5:
            logger.debug("[ImplicitFeedback] 快速回复 - 弱正面信号")
            # TODO: 弱正面反馈
        elif response_time > 60:
            logger.debug("[ImplicitFeedback] 长时间才回复 - 弱负面信号")
            # TODO: 弱负面反馈

    def analyze_turn(
        self,
        current_turn: ConversationTurn,
        session: ConversationSession
    ):
        """综合分析单轮对话。"""
        previous_turn = session.turns[-2] if len(session.turns) >= 2 else None
        self.analyze_continuation(current_turn, previous_turn)
        self.analyze_repetition(current_turn, session.turns[:-1])
        self.analyze_clarification(current_turn, previous_turn)
        self.analyze_response_time(current_turn, previous_turn)


__all__ = [
    'FeedbackSource',
    'FeedbackType',
    'FeedbackEvent',
    'ObservationEvent',
    'ConversationTurn',
    'ConversationSession',
    'ObservationCollector',
    'FeedbackCollector',
    'ImplicitFeedbackAnalyzer',
]
