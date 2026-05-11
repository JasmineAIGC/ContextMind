"""
记忆适应度评估模块

基于进化算法的适应度概念，通过观测使用情况和反馈来评估记忆价值。
"""

import time
from dataclasses import dataclass, field
from typing import Dict, Optional
from enum import Enum

from ..core.data_models import ContextItem
from contextmind.infra.logger import get_logger

logger = get_logger(__name__)


class DialogueObservationType(Enum):
    """对话观测类型，涵盖对话历史、意图识别、理解程度和对话质量。"""
    NEW_TURN = "new_turn"
    TOPIC_CHANGED = "topic_changed"
    CONTEXT_EXPANDED = "context_expanded"
    HISTORY_REFERENCED = "history_referenced"
    
    INTENT_IDENTIFIED = "intent_identified"
    INTENT_UNCLEAR = "intent_unclear"
    INTENT_CHANGED = "intent_changed"
    MULTI_INTENT = "multi_intent"
    
    UNDERSTOOD_WELL = "understood_well"
    MISUNDERSTOOD = "misunderstood"
    CLARIFICATION_NEEDED = "clarification_needed"
    AMBIGUOUS = "ambiguous"
    
    COHERENT_DIALOGUE = "coherent_dialogue"
    BROKEN_DIALOGUE = "broken_dialogue"
    REPETITIVE = "repetitive"
    OFF_TOPIC = "off_topic"


class FeedbackType(Enum):
    """反馈类型"""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    CORRECTION = "correction"
    NEUTRAL = "neutral"


@dataclass
class DialogueObservation:
    """对话观测记录，记录对话历史、意图、上下文及质量的演化信息。"""
    turn_id: str
    observation_type: DialogueObservationType
    timestamp: float = field(default_factory=time.time)
    
    dialogue_history_length: int = 0
    current_topic: Optional[str] = None
    previous_topic: Optional[str] = None
    
    identified_intent: Optional[str] = None
    intent_confidence: float = 0.0
    intent_category: Optional[str] = None
    
    context_items_count: int = 0
    context_relevance: float = 0.0
    referenced_history_turns: list = field(default_factory=list)
    
    coherence_score: float = 0.0
    understanding_level: float = 0.0
    
    related_memory_ids: list = field(default_factory=list)


@dataclass
class MemoryFitness:
    """记忆适应度评分，通过观测使用情况和反馈来评估记忆价值。"""
    usage_count: int = 0
    last_used: float = field(default_factory=time.time)
    creation_time: float = field(default_factory=time.time)
    
    retrieval_count: int = 0
    actual_usage_count: int = 0
    ignored_count: int = 0
    
    accuracy: float = 1.0
    relevance: float = 1.0
    contribution_score: float = 0.5
    
    positive_feedback_count: int = 0
    negative_feedback_count: int = 0
    correction_count: int = 0
    
    # 遗留字段（为了兼容性）
    recency: float = 1.0
    
    @property
    def usage_rate(self) -> float:
        """使用率 = 实际使用次数 / 检索次数"""
        if self.retrieval_count == 0:
            return 0.0
        return min(1.0, self.actual_usage_count / self.retrieval_count)
    
    @property
    def feedback_score(self) -> float:
        """基于正负反馈的比例计算综合评分（0-1）。"""
        total_feedback = (
            self.positive_feedback_count + 
            self.negative_feedback_count + 
            self.correction_count
        )
        if total_feedback == 0:
            return 0.5  # 无反馈时返回中性分数
        
        # 纠正惩罚力度(-0.5)小于纯负向反馈(-1.0)：纠正说明该记忆至少被引用过。
        score = (
            self.positive_feedback_count * 1.0 -
            self.negative_feedback_count * 1.0 -
            self.correction_count * 0.5
        ) / total_feedback
        
        return (score + 1.0) / 2.0
    
    def calculate_score(
        self,
        weights: Optional[Dict[str, float]] = None,
        current_time: Optional[float] = None
    ) -> float:
        """
        计算综合适应度分数（支持观测和反馈）
        
        Args:
            weights: 各维度权重配置，默认为均衡权重
            current_time: 当前时间戳，用于计算时间衰减
            
        Returns:
            综合适应度分数（0-1之间）
        """
        import math
        
        if weights is None:
            # 新的默认权重：更注重实际表现和反馈
            weights = {
                'usage': 0.20,           # 使用频率（降低权重，因为有使用率）
                'usage_rate': 0.15,      # 使用率（新增：检索后实际使用的比例）
                'recency': 0.15,         # 时间新鲜度
                'accuracy': 0.25,        # 准确性（基于真实反馈）
                'feedback': 0.15,        # 反馈得分（新增）
                'contribution': 0.10     # 贡献度（新增：对回复的实际贡献）
            }
        
        if current_time is None:
            current_time = time.time()
        
        # 对数尺度：100 次使用 ≈ 1.0，防止高频记忆无限主导检索排名
        # 而压制更新、更新鲜的记忆。
        usage_score = min(1.0, math.log(self.actual_usage_count + 1) / math.log(100))
        
        usage_rate_score = self.usage_rate
        
        time_since_use = current_time - self.last_used
        # 7 天半衰期对应短期对话相关性的典型时间窗口。
        half_life_seconds = 7 * 24 * 3600
        # 指数衰减 exp(-t/τ)：每 7 天不使用则分数减半；
        # τ = half_life_seconds 满足 exp(-τ/τ) = exp(-1) ≈ 0.368，
        # 实际半衰期为 half_life_seconds * ln(2) ≈ 4.85 天——
        # 足够接近 7 天的周级遗忘目标。
        recency_score = math.exp(-time_since_use / half_life_seconds)
        
        accuracy_score = self.accuracy
        
        feedback_score_value = self.feedback_score
        
        contribution_value = self.contribution_score
        
        score = (
            weights.get('usage', 0.20) * usage_score +
            weights.get('usage_rate', 0.15) * usage_rate_score +
            weights.get('recency', 0.15) * recency_score +
            weights.get('accuracy', 0.25) * accuracy_score +
            weights.get('feedback', 0.15) * feedback_score_value +
            weights.get('contribution', 0.10) * contribution_value
        )
        
        return max(0.0, min(1.0, score))
    
    def observe_retrieval(self):
        self.retrieval_count += 1
    
    def observe_usage(self):
        self.actual_usage_count += 1
        self.usage_count += 1
        self.last_used = time.time()
    
    def observe_ignored(self):
        self.ignored_count += 1
    
    def record_positive_feedback(self):
        self.positive_feedback_count += 1
        # 微小的 +0.05 增量：单次正向信号不应使准确度增长过快。
        self.accuracy = min(1.0, self.accuracy + 0.05)
    
    def record_negative_feedback(self):
        self.negative_feedback_count += 1
        # 负向反馈的惩罚力度是正向奖励的两倍（非对称更新），
        # 因为错误的代价远高于错失机会的代价。
        self.accuracy = max(0.0, self.accuracy - 0.1)
    
    def record_correction(self):
        self.correction_count += 1
        # 纠正（事实改写）是最强的不准确信号；-0.15 超过负向反馈惩罚，
        # 以强制快速重新评估该记忆。
        self.accuracy = max(0.0, self.accuracy - 0.15)
    
    def update_contribution(self, score: float):
        """
        更新贡献度评分
        
        Args:
            score: 贡献度评分 0-1
        """
        # 指数移动平均（α=0.3）：近期权重更大，同时保留历史数据以避免震荡。
        alpha = 0.3
        self.contribution_score = (
            alpha * score + (1 - alpha) * self.contribution_score
        )


class FitnessCalculator:
    """
    记忆适应度计算器
    
    提供统一的接口来计算和更新记忆的适应度分数。
    支持从 ContextItem 中提取适应度信息，或为新记忆创建初始适应度。
    """
    
    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        usage_decay_rate: float = 0.95
    ):
        """
        初始化适应度计算器
        
        Args:
            weights: 适应度各维度的权重配置
            usage_decay_rate: 使用次数的衰减率（防止旧记忆过度累积）
        """
        self.weights = weights or {
            'usage': 0.20,
            'usage_rate': 0.15,
            'recency': 0.15,
            'accuracy': 0.25,
            'feedback': 0.15,
            'contribution': 0.10
        }
        self.usage_decay_rate = usage_decay_rate
        logger.info(f"[FitnessCalculator] 初始化 - 权重={self.weights}")
    
    def get_fitness(self, memory: ContextItem) -> MemoryFitness:
        """
        从记忆项中提取或创建适应度评分（支持观测和反馈）
        
        Args:
            memory: 记忆项
            
        Returns:
            记忆适应度对象（包含观测和反馈数据）
        """
        metadata = memory.metadata or {}
        
        fitness = MemoryFitness(
            usage_count=metadata.get('usage_count', 0),
            last_used=metadata.get('last_used', memory.timestamp.timestamp() if memory.timestamp else time.time()),
            creation_time=memory.timestamp.timestamp() if memory.timestamp else time.time(),
            
            retrieval_count=metadata.get('retrieval_count', 0),
            actual_usage_count=metadata.get('actual_usage_count', 0),
            ignored_count=metadata.get('ignored_count', 0),
            
            accuracy=metadata.get('accuracy', 1.0),
            relevance=metadata.get('relevance', memory.score),
            contribution_score=metadata.get('contribution_score', 0.5),
            
            positive_feedback_count=metadata.get('positive_feedback_count', 0),
            negative_feedback_count=metadata.get('negative_feedback_count', 0),
            correction_count=metadata.get('correction_count', 0),
            
            recency=1.0,
        )
        
        return fitness
    
    def save_fitness(self, memory: ContextItem, fitness: MemoryFitness) -> ContextItem:
        """
        将适应度信息保存回记忆项的metadata（支持观测和反馈数据）
        
        Args:
            memory: 记忆项
            fitness: 适应度对象
            
        Returns:
            更新后的记忆项
        """
        updated_metadata = {
            **(memory.metadata or {}),
            'usage_count': fitness.usage_count,
            'last_used': fitness.last_used,
            'creation_time': fitness.creation_time,
            
            'retrieval_count': fitness.retrieval_count,
            'actual_usage_count': fitness.actual_usage_count,
            'ignored_count': fitness.ignored_count,
            
            'accuracy': fitness.accuracy,
            'relevance': fitness.relevance,
            'contribution_score': fitness.contribution_score,
            
            'positive_feedback_count': fitness.positive_feedback_count,
            'negative_feedback_count': fitness.negative_feedback_count,
            'correction_count': fitness.correction_count,
        }
        
        memory.metadata = updated_metadata
        return memory
    
    def observe_retrieval(self, memory: ContextItem) -> ContextItem:
        fitness = self.get_fitness(memory)
        fitness.observe_retrieval()
        return self.save_fitness(memory, fitness)
    
    def observe_usage(self, memory: ContextItem) -> ContextItem:
        fitness = self.get_fitness(memory)
        fitness.observe_usage()
        return self.save_fitness(memory, fitness)
    
    def observe_ignored(self, memory: ContextItem) -> ContextItem:
        fitness = self.get_fitness(memory)
        fitness.observe_ignored()
        return self.save_fitness(memory, fitness)
    
    def record_positive_feedback(self, memory: ContextItem) -> ContextItem:
        """
        记录正面反馈
        
        Args:
            memory: 收到正面反馈的记忆项
        """
        fitness = self.get_fitness(memory)
        fitness.record_positive_feedback()
        logger.info(f"[FitnessCalculator] 正面反馈 - 准确性提升至 {fitness.accuracy:.2f}")
        return self.save_fitness(memory, fitness)
    
    def record_negative_feedback(self, memory: ContextItem) -> ContextItem:
        """
        记录负面反馈
        
        Args:
            memory: 收到负面反馈的记忆项
        """
        fitness = self.get_fitness(memory)
        fitness.record_negative_feedback()
        logger.info(f"[FitnessCalculator] 负面反馈 - 准确性降至 {fitness.accuracy:.2f}")
        return self.save_fitness(memory, fitness)
    
    def record_correction(self, memory: ContextItem) -> ContextItem:
        """
        记录纠正
        
        Args:
            memory: 被纠正的记忆项
        """
        fitness = self.get_fitness(memory)
        fitness.record_correction()
        logger.info(f"[FitnessCalculator] 纠正反馈 - 准确性降至 {fitness.accuracy:.2f}")
        return self.save_fitness(memory, fitness)
    
    def update_contribution(self, memory: ContextItem, score: float) -> ContextItem:
        """
        更新贡献度评分
        
        Args:
            memory: 记忆项
            score: 贡献度评分 0-1
        """
        fitness = self.get_fitness(memory)
        fitness.update_contribution(score)
        logger.debug(f"[FitnessCalculator] 更新贡献度 - {fitness.contribution_score:.2f}")
        return self.save_fitness(memory, fitness)
    
    def calculate_fitness_score(self, memory: ContextItem) -> float:
        """
        计算记忆的当前适应度分数（使用观测和反馈数据）
        
        Args:
            memory: 记忆项
            
        Returns:
            适应度分数 (0-1)
        """
        fitness = self.get_fitness(memory)
        return fitness.calculate_score(self.weights)
    
    def decay_usage_counts(self, memories: list[ContextItem]) -> list[ContextItem]:
        """
        对所有记忆的使用次数应用衰减
        
        防止旧记忆因历史使用次数过高而难以被淘汰。
        
        Args:
            memories: 记忆列表
            
        Returns:
            应用衰减后的记忆列表
        """
        updated_memories = []
        
        for memory in memories:
            fitness = self.get_fitness(memory)
            # 每次演化周期的乘法衰减防止旧记忆的计数相对近期记忆
            # 不成比例地累积过高。
            fitness.usage_count = int(fitness.usage_count * self.usage_decay_rate)
            
            updated_metadata = {
                **(memory.metadata or {}),
                'usage_count': fitness.usage_count
            }
            
            updated_memory = ContextItem(
                content=memory.content,
                source=memory.source,
                score=memory.score,
                timestamp=memory.timestamp,
                embeddings=memory.embeddings,
                metadata=updated_metadata
            )
            updated_memories.append(updated_memory)
        
        return updated_memories
