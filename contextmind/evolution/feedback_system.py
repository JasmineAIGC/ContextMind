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
    对话观测事件
    
    观测对话层面的信息：
    - 对话历史演化（话题变化、轮次）
    - 用户意图识别和变化
    - 上下文扩展和相关性
    - 对话质量和理解程度
    
    这些观测用于评估记忆在对话中的实际价值。
    """
    turn_id: str                             # 对话轮次ID
    event_type: str                          # 事件类型: dialogue, intent, context, quality
    timestamp: float = field(default_factory=time.time)
    
    # 对话历史相关
    dialogue_history_length: int = 0         # 对话历史长度
    current_topic: Optional[str] = None      # 当前话题
    topic_changed: bool = False              # 话题是否改变
    
    # 意图相关
    identified_intent: Optional[str] = None  # 识别到的意图
    intent_confidence: float = 0.0           # 意图置信度
    intent_changed: bool = False             # 意图是否变化
    
    # 上下文相关
    context_items_count: int = 0             # 上下文项数量
    context_relevance: float = 0.0           # 上下文相关性
    referenced_history: bool = False         # 是否引用历史
    
    # 对话质量相关
    coherence_score: float = 0.0             # 连贯性评分
    understanding_level: float = 0.0         # 理解程度
    
    # 关联的记忆（记录哪些记忆参与了这次对话）
    related_memory_ids: List[str] = field(default_factory=list)
    
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationTurn:
    """
    对话轮次
    
    记录单次对话交互的完整信息，聚焦于对话本身而非记忆检索。
    
    包含：
    - 对话内容（用户输入、系统回复）
    - 对话理解（意图、主题）
    - 对话质量（连贯性、理解程度）
    - 关联的记忆（哪些记忆参与了对话）
    """
    turn_id: str
    user_query: str
    system_response: str
    timestamp: float = field(default_factory=time.time)
    
    # 对话理解
    identified_intent: Optional[str] = None      # 识别到的意图
    intent_confidence: float = 0.0               # 意图置信度
    current_topic: Optional[str] = None          # 当前话题
    topic_changed: bool = False                  # 话题是否改变
    
    # 对话质量
    coherence_score: float = 0.0                 # 连贯性评分
    understanding_level: float = 0.0             # 理解程度
    
    # 关联的记忆（记录哪些记忆对这次对话有贡献）
    relevant_memory_ids: List[str] = field(default_factory=list)
    
    # 元数据
    response_time: Optional[float] = None        # 生成回复耗时
    user_response_time: Optional[float] = None   # 用户回复耗时
    
    # 反馈和观测
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
"""
反馈收集器实现

提供多种反馈收集方式的具体实现。
"""

from typing import List, Dict, Optional, Any, Callable
import time
from utils.logger import get_logger
from contextmind.memory.memory_fitness import FitnessCalculator
from contextmind.core.data_models import ContextItem

# Types are defined in this file (merged from types.py)
# FeedbackEvent, ObservationEvent, ConversationTurn, ConversationSession,
# FeedbackSource, FeedbackType

logger = get_logger(__name__)


class ObservationCollector:
    """
    观测收集器
    
    收集对话过程中的观测数据：检索、使用、忽略等事件。
    """
    
    def __init__(self, fitness_calculator: Optional[FitnessCalculator] = None):
        """
        初始化观测收集器
        
        Args:
            fitness_calculator: 适应度计算器（用于更新记忆）
        """
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
        观测：记忆被检索
        
        Args:
            memory: 被检索的记忆
            query: 触发检索的查询
            position: 在检索结果中的位置
            
        Returns:
            观测事件
        """
        # 更新记忆的适应度数据
        self.fitness_calculator.observe_retrieval(memory)
        
        # 记录观测事件
        event = ObservationEvent(
            memory_id=memory.metadata.get('id', str(id(memory))),
            event_type="retrieved",
            query=query,
            relevance_score=memory.score,
            position=position
        )
        
        self.observations.append(event)
        logger.debug(f"[Observation] 检索: memory={event.memory_id[:8]}, score={memory.score:.2f}")
        
        return event
    
    def observe_usage(
        self,
        memory: ContextItem,
        used_in_prompt: bool = True,
        contributed: bool = True
    ) -> ObservationEvent:
        """
        观测：记忆被实际使用
        
        Args:
            memory: 被使用的记忆
            used_in_prompt: 是否被放入prompt
            contributed: 是否对回复有贡献
            
        Returns:
            观测事件
        """
        # 更新记忆的适应度数据
        self.fitness_calculator.observe_usage(memory)
        
        # 记录观测事件
        event = ObservationEvent(
            memory_id=memory.metadata.get('id', str(id(memory))),
            event_type="used",
            used_in_prompt=used_in_prompt,
            contributed_to_response=contributed
        )
        
        self.observations.append(event)
        logger.debug(f"[Observation] 使用: memory={event.memory_id[:8]}")
        
        return event
    
    def observe_ignored(
        self,
        memory: ContextItem,
        reason: Optional[str] = None
    ) -> ObservationEvent:
        """
        观测：记忆被检索但未使用
        
        Args:
            memory: 被忽略的记忆
            reason: 忽略原因
            
        Returns:
            观测事件
        """
        # 更新记忆的适应度数据
        self.fitness_calculator.observe_ignored(memory)
        
        # 记录观测事件
        event = ObservationEvent(
            memory_id=memory.metadata.get('id', str(id(memory))),
            event_type="ignored",
            metadata={'reason': reason} if reason else {}
        )
        
        self.observations.append(event)
        logger.debug(f"[Observation] 忽略: memory={event.memory_id[:8]}")
        
        return event
    
    def get_observations(self, memory_id: Optional[str] = None) -> List[ObservationEvent]:
        """
        获取观测事件
        
        Args:
            memory_id: 可选的记忆ID过滤
            
        Returns:
            观测事件列表
        """
        if memory_id:
            return [obs for obs in self.observations if obs.memory_id == memory_id]
        return self.observations
    
    def clear_observations(self):
        """清空观测记录"""
        self.observations = []


class FeedbackCollector:
    """
    反馈收集器
    
    收集显式和自动反馈，并应用到记忆的适应度更新。
    """
    
    def __init__(self, fitness_calculator: Optional[FitnessCalculator] = None):
        """
        初始化反馈收集器
        
        Args:
            fitness_calculator: 适应度计算器
        """
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
        """
        收集正面反馈
        
        Args:
            memories: 收到正面反馈的记忆列表
            source: 反馈来源
            strength: 反馈强度 (0-1)
            details: 详细信息
            
        Returns:
            反馈事件
        """
        memory_ids = [mem.metadata.get('id', str(id(mem))) for mem in memories]
        
        # 更新记忆适应度
        for memory in memories:
            self.fitness_calculator.record_positive_feedback(memory)
        
        # 创建反馈事件
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
        """
        收集负面反馈
        
        Args:
            memories: 收到负面反馈的记忆列表
            source: 反馈来源
            strength: 反馈强度 (0-1)
            details: 详细信息
            
        Returns:
            反馈事件
        """
        memory_ids = [mem.metadata.get('id', str(id(mem))) for mem in memories]
        
        # 更新记忆适应度
        for memory in memories:
            self.fitness_calculator.record_negative_feedback(memory)
        
        # 创建反馈事件
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
        """
        收集纠正反馈
        
        Args:
            memories: 被纠正的记忆列表
            correction_info: 纠正信息
            details: 详细信息
            
        Returns:
            反馈事件
        """
        memory_ids = [mem.metadata.get('id', str(id(mem))) for mem in memories]
        
        # 更新记忆适应度
        for memory in memories:
            self.fitness_calculator.record_correction(memory)
        
        # 创建反馈事件
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
        rating: float,  # 0-1 范围
        details: Optional[Dict[str, Any]] = None
    ) -> FeedbackEvent:
        """
        收集评分反馈
        
        Args:
            memories: 相关记忆列表
            rating: 评分 (0-1)
            details: 详细信息
            
        Returns:
            反馈事件
        """
        # 根据评分判断反馈类型
        if rating >= 0.7:
            feedback_type = FeedbackType.POSITIVE
            source = FeedbackSource.RATING
            for mem in memories:
                self.fitness_calculator.record_positive_feedback(mem)
        elif rating <= 0.3:
            feedback_type = FeedbackType.NEGATIVE
            source = FeedbackSource.RATING
            for mem in memories:
                self.fitness_calculator.record_negative_feedback(mem)
        else:
            feedback_type = FeedbackType.NEUTRAL
            source = FeedbackSource.RATING
        
        memory_ids = [mem.metadata.get('id', str(id(mem))) for mem in memories]
        
        event = FeedbackEvent(
            memory_ids=memory_ids,
            feedback_type=feedback_type,
            source=source,
            strength=abs(rating - 0.5) * 2,  # 0.5 → 0, 0或1 → 1
            details={'rating': rating, **(details or {})}
        )
        
        self.feedbacks.append(event)
        logger.info(f"[Feedback] 评分反馈: rating={rating:.2f}, type={feedback_type.value}")
        
        return event
    
    def update_contribution_score(
        self,
        memory: ContextItem,
        score: float
    ):
        """
        更新记忆的贡献度评分
        
        Args:
            memory: 记忆项
            score: 贡献度评分 (0-1)
        """
        self.fitness_calculator.update_contribution(memory, score)
        logger.debug(f"[Feedback] 更新贡献度: memory={memory.metadata.get('id', '')[:8]}, score={score:.2f}")
    
    def get_feedbacks(
        self,
        memory_id: Optional[str] = None,
        feedback_type: Optional[FeedbackType] = None
    ) -> List[FeedbackEvent]:
        """
        获取反馈事件
        
        Args:
            memory_id: 可选的记忆ID过滤
            feedback_type: 可选的反馈类型过滤
            
        Returns:
            反馈事件列表
        """
        result = self.feedbacks
        
        if memory_id:
            result = [fb for fb in result if memory_id in fb.memory_ids]
        
        if feedback_type:
            result = [fb for fb in result if fb.feedback_type == feedback_type]
        
        return result
    
    def get_feedback_stats(self) -> Dict[str, int]:
        """
        获取反馈统计
        
        Returns:
            统计字典
        """
        stats = {
            'total': len(self.feedbacks),
            'positive': 0,
            'negative': 0,
            'neutral': 0,
            'correction': 0
        }
        
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
    隐式反馈分析器
    
    从对话行为中推断隐式反馈。
    """
    
    def __init__(self, feedback_collector: FeedbackCollector):
        """
        初始化隐式反馈分析器
        
        Args:
            feedback_collector: 反馈收集器（用于记录推断的反馈）
        """
        self.feedback_collector = feedback_collector
        logger.info("[ImplicitFeedbackAnalyzer] 初始化完成")
    
    def analyze_continuation(
        self,
        current_turn: ConversationTurn,
        previous_turn: Optional[ConversationTurn]
    ):
        """
        分析对话延续行为
        
        如果用户继续对话，说明对上一轮回复基本满意。
        
        Args:
            current_turn: 当前对话轮次
            previous_turn: 上一轮对话
        """
        if not previous_turn or not previous_turn.used_memory_ids:
            return
        
        # 用户在合理时间内继续对话 = 正面信号
        if current_turn.timestamp - previous_turn.timestamp < 300:  # 5分钟内
            logger.debug("[ImplicitFeedback] 对话延续 - 弱正面信号")
            
            # TODO: 获取记忆对象并应用反馈
            # 这里需要从memory_bank获取记忆
            # 暂时记录事件
    
    def analyze_repetition(
        self,
        current_turn: ConversationTurn,
        previous_turns: List[ConversationTurn]
    ):
        """
        分析重复提问行为
        
        如果用户重复或改写问题，说明上次回答不够满意。
        
        Args:
            current_turn: 当前对话轮次
            previous_turns: 之前的对话轮次
        """
        if not previous_turns:
            return
        
        # 简单检测：检查关键词相似度
        current_query_lower = current_turn.user_query.lower()
        
        for prev_turn in previous_turns[-3:]:  # 检查最近3轮
            prev_query_lower = prev_turn.user_query.lower()
            
            # 简单相似度检测（实际应该用更sophisticated的方法）
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
        """
        分析澄清行为
        
        如果用户澄清或纠正，说明上次理解有误。
        
        Args:
            current_turn: 当前对话轮次
            previous_turn: 上一轮对话
        """
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
        """
        分析用户响应时间
        
        快速回复可能表示积极参与，长时间才回复可能表示犹豫。
        
        Args:
            current_turn: 当前对话轮次
            previous_turn: 上一轮对话
        """
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
        """
        综合分析单轮对话
        
        Args:
            current_turn: 当前对话轮次
            session: 对话会话
        """
        previous_turn = session.turns[-2] if len(session.turns) >= 2 else None
        
        # 运行各项分析
        self.analyze_continuation(current_turn, previous_turn)
        self.analyze_repetition(current_turn, session.turns[:-1])
        self.analyze_clarification(current_turn, previous_turn)
        self.analyze_response_time(current_turn, previous_turn)
