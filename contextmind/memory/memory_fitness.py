"""
记忆适应度评估模块

借鉴 AlphaEvolve/ThetaEvolve 的进化思想，为记忆库中的每条记忆计算适应度分数。
适应度分数用于指导记忆的选择、更新和淘汰。

该模块实现了多维度的记忆评估机制：
- 使用频率：记忆被使用的次数
- 时间新鲜度：最近使用的时间
- 准确性：基于反馈的准确性评分
- 相关性：与当前对话的相关程度
"""

import time
from dataclasses import dataclass, field
from typing import Dict, Optional
from datetime import datetime

from ..core.data_models import ContextItem
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class MemoryFitness:
    """
    记忆适应度评分
    
    借鉴进化算法的适应度概念，评估记忆条目的价值。
    多维度评分确保记忆库保持高质量和相关性。
    
    Attributes:
        usage_count: 记忆被使用的总次数（越多越好）
        last_used: 最后一次使用的时间戳（越新越好）
        accuracy: 准确性评分 0-1（基于用户反馈）
        relevance: 当前相关性评分 0-1
        recency: 新鲜度评分 0-1（基于创建时间）
        creation_time: 记忆创建时间戳
    """
    usage_count: int = 0
    last_used: float = field(default_factory=time.time)
    accuracy: float = 1.0  # 默认为完全准确
    relevance: float = 1.0  # 默认为高度相关
    recency: float = 1.0
    creation_time: float = field(default_factory=time.time)
    
    def calculate_score(
        self,
        weights: Optional[Dict[str, float]] = None,
        current_time: Optional[float] = None
    ) -> float:
        """
        计算综合适应度分数
        
        使用加权和的方式组合多个维度的评分。
        
        Args:
            weights: 各维度权重配置，默认为均衡权重
            current_time: 当前时间戳，用于计算时间衰减
            
        Returns:
            综合适应度分数（0-1之间）
        """
        if weights is None:
            # 默认权重：平衡各维度重要性
            weights = {
                'usage': 0.3,      # 使用频率权重
                'recency': 0.25,   # 新鲜度权重
                'accuracy': 0.25,  # 准确性权重
                'relevance': 0.2   # 相关性权重
            }
        
        if current_time is None:
            current_time = time.time()
        
        # 使用频率得分（归一化，使用对数缩放避免过大差异）
        import math
        usage_score = min(1.0, math.log(self.usage_count + 1) / math.log(100))
        
        # 时间衰减得分（最近使用的记忆得分更高）
        time_since_use = current_time - self.last_used
        # 使用指数衰减，半衰期为7天
        half_life_seconds = 7 * 24 * 3600
        recency_score = math.exp(-time_since_use / half_life_seconds)
        
        # 综合计算
        score = (
            weights.get('usage', 0.3) * usage_score +
            weights.get('recency', 0.25) * recency_score +
            weights.get('accuracy', 0.25) * self.accuracy +
            weights.get('relevance', 0.2) * self.relevance
        )
        
        return max(0.0, min(1.0, score))  # 确保在 [0, 1] 范围内


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
            'usage': 0.3,
            'recency': 0.25,
            'accuracy': 0.25,
            'relevance': 0.2
        }
        self.usage_decay_rate = usage_decay_rate
        logger.info(f"[FitnessCalculator] 初始化 - 权重={self.weights}")
    
    def get_fitness(self, memory: ContextItem) -> MemoryFitness:
        """
        从记忆项中提取或创建适应度评分
        
        Args:
            memory: 记忆项
            
        Returns:
            记忆适应度对象
        """
        # 尝试从 metadata 中获取已有的适应度信息
        metadata = memory.metadata or {}
        
        fitness = MemoryFitness(
            usage_count=metadata.get('usage_count', 0),
            last_used=metadata.get('last_used', memory.timestamp.timestamp() if memory.timestamp else time.time()),
            accuracy=metadata.get('accuracy', 1.0),
            relevance=metadata.get('relevance', memory.score),  # 使用记忆分数作为初始相关性
            recency=1.0,  # 新记忆默认新鲜度为1
            creation_time=memory.timestamp.timestamp() if memory.timestamp else time.time()
        )
        
        return fitness
    
    def update_fitness(
        self,
        memory: ContextItem,
        used: bool = False,
        accuracy_feedback: Optional[float] = None,
        relevance_feedback: Optional[float] = None
    ) -> ContextItem:
        """
        更新记忆的适应度信息
        
        Args:
            memory: 要更新的记忆项
            used: 记忆是否被使用
            accuracy_feedback: 准确性反馈 (0-1)
            relevance_feedback: 相关性反馈 (0-1)
            
        Returns:
            更新后的记忆项
        """
        fitness = self.get_fitness(memory)
        
        # 更新使用次数和时间
        if used:
            fitness.usage_count += 1
            fitness.last_used = time.time()
        
        # 更新准确性（如果有反馈）
        if accuracy_feedback is not None:
            # 使用移动平均
            alpha = 0.3  # 新反馈的权重
            fitness.accuracy = alpha * accuracy_feedback + (1 - alpha) * fitness.accuracy
        
        # 更新相关性（如果有反馈）
        if relevance_feedback is not None:
            fitness.relevance = relevance_feedback
        
        # 将适应度信息保存到 metadata
        updated_metadata = {
            **(memory.metadata or {}),
            'usage_count': fitness.usage_count,
            'last_used': fitness.last_used,
            'accuracy': fitness.accuracy,
            'relevance': fitness.relevance,
            'creation_time': fitness.creation_time,
            'fitness_score': fitness.calculate_score(self.weights)
        }
        
        # 创建更新后的记忆项
        from ..core.data_models import ContextItem
        updated_memory = ContextItem(
            content=memory.content,
            source=memory.source,
            score=memory.score,
            timestamp=memory.timestamp,
            embeddings=memory.embeddings,
            metadata=updated_metadata
        )
        
        return updated_memory
    
    def calculate_fitness_score(self, memory: ContextItem) -> float:
        """
        计算记忆的当前适应度分数
        
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
