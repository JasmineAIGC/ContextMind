"""
记忆适应度评估模块

借鉴 AlphaEvolve/ThetaEvolve 的进化思想，为记忆库中的每条记忆计算适应度分数。
适应度分数用于指导记忆的选择、更新和淘汰。

该模块实现了多维度的记忆评估机制，包含观测和反馈循环：

观测对象（对话层面）：
- 对话历史：话题变化、轮次数、历史引用
- 用户意图：意图识别、意图变化、多重意图
- 上下文：上下文扩展、相关性、演化过程
- 对话质量：连贯性、理解程度、话题偏离

评估维度：
- 使用频率：记忆被实际使用的次数
- 时间新鲜度：最近使用的时间
- 准确性：基于真实反馈的准确性评分
- 相关性：与当前对话的相关程度
- 贡献度：记忆对对话质量的实际贡献
"""

import time
from dataclasses import dataclass, field
from typing import Dict, Optional
from datetime import datetime
from enum import Enum

from ..core.data_models import ContextItem
from lib.utils.logger import get_logger

logger = get_logger(__name__)


class DialogueObservationType(Enum):
    """
    对话观测类型
    
    观测对象：对话历史、用户意图、上下文变化、对话质量
    用于理解对话的演化过程，而非单纯的记忆检索统计
    """
    # 对话历史观测
    NEW_TURN = "new_turn"                      # 新的对话轮次
    TOPIC_CHANGED = "topic_changed"            # 话题改变
    CONTEXT_EXPANDED = "context_expanded"      # 上下文扩展
    HISTORY_REFERENCED = "history_referenced"  # 引用历史对话
    
    # 意图观测
    INTENT_IDENTIFIED = "intent_identified"    # 意图识别成功
    INTENT_UNCLEAR = "intent_unclear"          # 意图不明确
    INTENT_CHANGED = "intent_changed"          # 意图变化
    MULTI_INTENT = "multi_intent"              # 多重意图
    
    # 理解程度观测
    UNDERSTOOD_WELL = "understood_well"        # 理解良好
    MISUNDERSTOOD = "misunderstood"            # 理解错误
    CLARIFICATION_NEEDED = "clarification_needed"  # 需要澄清
    AMBIGUOUS = "ambiguous"                    # 存在歧义
    
    # 对话质量观测
    COHERENT_DIALOGUE = "coherent_dialogue"    # 对话连贯
    BROKEN_DIALOGUE = "broken_dialogue"        # 对话中断
    REPETITIVE = "repetitive"                  # 重复问题
    OFF_TOPIC = "off_topic"                    # 偏离主题


class FeedbackType(Enum):
    """反馈类型"""
    POSITIVE = "positive"          # 正面反馈（用户满意）
    NEGATIVE = "negative"          # 负面反馈（用户不满）
    CORRECTION = "correction"      # 用户纠正
    NEUTRAL = "neutral"            # 中性反馈


@dataclass
class DialogueObservation:
    """
    对话观测记录
    
    观测对话本身的演化，包括：
    - 对话历史的变化（话题、轮次）
    - 用户意图的识别和变化
    - 上下文的扩展和演化
    - 对话质量和理解程度
    
    这些观测用于评估记忆在对话中的实际价值。
    """
    turn_id: str                                      # 对话轮次ID
    observation_type: DialogueObservationType
    timestamp: float = field(default_factory=time.time)
    
    # 对话历史信息
    dialogue_history_length: int = 0                  # 对话历史长度
    current_topic: Optional[str] = None               # 当前话题
    previous_topic: Optional[str] = None              # 前一个话题
    
    # 意图信息
    identified_intent: Optional[str] = None           # 识别到的意图
    intent_confidence: float = 0.0                    # 意图置信度
    intent_category: Optional[str] = None             # 意图类别
    
    # 上下文信息
    context_items_count: int = 0                      # 上下文项数量
    context_relevance: float = 0.0                    # 上下文相关性
    referenced_history_turns: list = field(default_factory=list)  # 引用的历史轮次
    
    # 对话质量
    coherence_score: float = 0.0                      # 连贯性评分
    understanding_level: float = 0.0                  # 理解程度
    
    # 关联的记忆（可选）
    related_memory_ids: list = field(default_factory=list)  # 相关记忆ID


@dataclass
class MemoryFitness:
    """
    记忆适应度评分（支持观测和反馈）
    
    借鉴进化算法的适应度概念，通过观测实际使用情况和收集反馈来评估记忆价值。
    
    Attributes:
        # 基础统计
        usage_count: 记忆被实际使用的次数
        last_used: 最后一次使用的时间戳
        creation_time: 记忆创建时间戳
        
        # 观测数据（新增）
        retrieval_count: 记忆被检索的次数（可能未被使用）
        actual_usage_count: 实际被使用的次数（用于生成回复）
        ignored_count: 被检索但未使用的次数
        
        # 评分维度
        accuracy: 准确性评分 0-1（基于真实反馈）
        relevance: 当前相关性评分 0-1
        contribution_score: 实际贡献度评分 0-1（基于观测）
        
        # 反馈统计（新增）
        positive_feedback_count: 正面反馈次数
        negative_feedback_count: 负面反馈次数
        correction_count: 被纠正次数
        
        # 计算属性
        usage_rate: 使用率 = actual_usage / retrieval（自动计算）
        feedback_score: 反馈综合评分（自动计算）
    """
    # 基础统计
    usage_count: int = 0
    last_used: float = field(default_factory=time.time)
    creation_time: float = field(default_factory=time.time)
    
    # 观测数据（新增）
    retrieval_count: int = 0       # 被检索次数
    actual_usage_count: int = 0    # 实际使用次数
    ignored_count: int = 0         # 被忽略次数
    
    # 评分维度
    accuracy: float = 1.0          # 默认为完全准确
    relevance: float = 1.0         # 默认为高度相关
    contribution_score: float = 0.5  # 默认中等贡献
    
    # 反馈统计（新增）
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
        """
        反馈综合评分
        
        基于正负反馈的比例计算，范围 0-1
        """
        total_feedback = (
            self.positive_feedback_count + 
            self.negative_feedback_count + 
            self.correction_count
        )
        if total_feedback == 0:
            return 0.5  # 无反馈时返回中性分数
        
        # 正面权重1.0，负面权重-1.0，纠正权重-0.5
        score = (
            self.positive_feedback_count * 1.0 -
            self.negative_feedback_count * 1.0 -
            self.correction_count * 0.5
        ) / total_feedback
        
        # 归一化到 [0, 1]
        return (score + 1.0) / 2.0
    
    def calculate_score(
        self,
        weights: Optional[Dict[str, float]] = None,
        current_time: Optional[float] = None
    ) -> float:
        """
        计算综合适应度分数（支持观测和反馈）
        
        整合多个维度的评分，其中包括基于真实观测和反馈的数据。
        
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
        
        # 1. 使用频率得分（归一化，使用对数缩放）
        usage_score = min(1.0, math.log(self.actual_usage_count + 1) / math.log(100))
        
        # 2. 使用率得分（观测数据：实际使用/检索）
        usage_rate_score = self.usage_rate
        
        # 3. 时间衰减得分（最近使用的记忆得分更高）
        time_since_use = current_time - self.last_used
        half_life_seconds = 7 * 24 * 3600  # 7天半衰期
        recency_score = math.exp(-time_since_use / half_life_seconds)
        
        # 4. 准确性得分（基于真实反馈更新的值）
        accuracy_score = self.accuracy
        
        # 5. 反馈得分（基于正负反馈统计）
        feedback_score_value = self.feedback_score
        
        # 6. 贡献度得分（观测到的实际贡献）
        contribution_value = self.contribution_score
        
        # 综合计算（加权和）
        score = (
            weights.get('usage', 0.20) * usage_score +
            weights.get('usage_rate', 0.15) * usage_rate_score +
            weights.get('recency', 0.15) * recency_score +
            weights.get('accuracy', 0.25) * accuracy_score +
            weights.get('feedback', 0.15) * feedback_score_value +
            weights.get('contribution', 0.10) * contribution_value
        )
        
        return max(0.0, min(1.0, score))  # 确保在 [0, 1] 范围内
    
    def observe_retrieval(self):
        """观测：记忆被检索"""
        self.retrieval_count += 1
    
    def observe_usage(self):
        """观测：记忆被实际使用"""
        self.actual_usage_count += 1
        self.usage_count += 1
        self.last_used = time.time()
    
    def observe_ignored(self):
        """观测：记忆被检索但未使用"""
        self.ignored_count += 1
    
    def record_positive_feedback(self):
        """记录正面反馈"""
        self.positive_feedback_count += 1
        # 提升准确性（逐步学习）
        self.accuracy = min(1.0, self.accuracy + 0.05)
    
    def record_negative_feedback(self):
        """记录负面反馈"""
        self.negative_feedback_count += 1
        # 降低准确性（逐步学习）
        self.accuracy = max(0.0, self.accuracy - 0.1)
    
    def record_correction(self):
        """记录纠正（用户纠正了记忆内容）"""
        self.correction_count += 1
        # 较大幅度降低准确性
        self.accuracy = max(0.0, self.accuracy - 0.15)
    
    def update_contribution(self, score: float):
        """
        更新贡献度评分
        
        Args:
            score: 贡献度评分 0-1
        """
        # 使用指数移动平均更新
        alpha = 0.3  # 学习率
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
        usage_decay_rate: float = 0.95  # 使用次数衰减率
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
        # 尝试从 metadata 中获取已有的适应度信息
        metadata = memory.metadata or {}
        
        fitness = MemoryFitness(
            # 基础统计
            usage_count=metadata.get('usage_count', 0),
            last_used=metadata.get('last_used', memory.timestamp.timestamp() if memory.timestamp else time.time()),
            creation_time=memory.timestamp.timestamp() if memory.timestamp else time.time(),
            
            # 观测数据
            retrieval_count=metadata.get('retrieval_count', 0),
            actual_usage_count=metadata.get('actual_usage_count', 0),
            ignored_count=metadata.get('ignored_count', 0),
            
            # 评分维度
            accuracy=metadata.get('accuracy', 1.0),
            relevance=metadata.get('relevance', memory.score),
            contribution_score=metadata.get('contribution_score', 0.5),
            
            # 反馈统计
            positive_feedback_count=metadata.get('positive_feedback_count', 0),
            negative_feedback_count=metadata.get('negative_feedback_count', 0),
            correction_count=metadata.get('correction_count', 0),
            
            recency=1.0,  # 新记忆默认新鲜度为1
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
            # 基础统计
            'usage_count': fitness.usage_count,
            'last_used': fitness.last_used,
            'creation_time': fitness.creation_time,
            
            # 观测数据
            'retrieval_count': fitness.retrieval_count,
            'actual_usage_count': fitness.actual_usage_count,
            'ignored_count': fitness.ignored_count,
            
            # 评分维度
            'accuracy': fitness.accuracy,
            'relevance': fitness.relevance,
            'contribution_score': fitness.contribution_score,
            
            # 反馈统计
            'positive_feedback_count': fitness.positive_feedback_count,
            'negative_feedback_count': fitness.negative_feedback_count,
            'correction_count': fitness.correction_count,
        }
        
        memory.metadata = updated_metadata
        return memory
    
    def observe_retrieval(self, memory: ContextItem) -> ContextItem:
        """
        观测：记忆被检索
        
        Args:
            memory: 被检索的记忆项
            
        Returns:
            更新后的记忆项
        """
        fitness = self.get_fitness(memory)
        fitness.observe_retrieval()
        return self.save_fitness(memory, fitness)
    
    def observe_usage(self, memory: ContextItem) -> ContextItem:
        """
        观测：记忆被实际使用
        
        Args:
            memory: 被使用的记忆项
            
        Returns:
            更新后的记忆项
        """
        fitness = self.get_fitness(memory)
        fitness.observe_usage()
        return self.save_fitness(memory, fitness)
    
    def observe_ignored(self, memory: ContextItem) -> ContextItem:
        """
        观测：记忆被检索但未使用
        
        Args:
            memory: 被忽略的记忆项
            
        Returns:
            更新后的记忆项
        """
        fitness = self.get_fitness(memory)
        fitness.observe_ignored()
        return self.save_fitness(memory, fitness)
    
    def record_positive_feedback(self, memory: ContextItem) -> ContextItem:
        """
        记录正面反馈
        
        Args:
            memory: 收到正面反馈的记忆项
            
        Returns:
            更新后的记忆项
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
            
        Returns:
            更新后的记忆项
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
            
        Returns:
            更新后的记忆项
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
            
        Returns:
            更新后的记忆项
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
            # 应用衰减
            fitness.usage_count = int(fitness.usage_count * self.usage_decay_rate)
            
            # 更新 metadata
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
