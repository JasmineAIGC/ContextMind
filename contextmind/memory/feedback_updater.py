"""
Feedback-Based Memory Updater - 基于反馈信号的记忆更新器

该模块实现基于反馈信号/奖励惩罚机制的记忆库更新策略。
参考最新研究论文中的强化学习方法，通过反馈信号动态调整记忆的重要性和保留策略。

设计参考:
1. Reflexion (Shinn et al., 2023): 基于反思和反馈的自我改进
2. Memetic Proxies (Park et al., 2023): 记忆的重要性评分和衰减
3. MemPrompt (Madaan et al., 2022): 基于效用的记忆选择
4. Generative Agents (Park et al., 2023): 记忆的重要性、新近性和相关性打分

核心机制:
- 反馈信号类型: 正向(helpful)、负向(harmful)、中性(neutral)
- 奖励函数: 根据反馈调整记忆的置信度和重要性
- 衰减机制: 未被使用的记忆逐渐降低重要性
- 强化机制: 有用的记忆增强保留优先级
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from enum import Enum
import math

from ..core.data_models import ContextItem, Knowledge
from ..core.types import ContextSource, KnowledgeType
from ..utils.logger import get_logger
from ..core.strategies import UpdateStrategy as BaseUpdater
from ..utils.embedding import calculate_embedding_similarity

logger = get_logger(__name__)


class FeedbackSignal(Enum):
    """反馈信号类型"""
    POSITIVE = "positive"  # 正向反馈：记忆有助于生成好的回复
    NEGATIVE = "negative"  # 负向反馈：记忆导致不准确或不相关的回复
    NEUTRAL = "neutral"    # 中性反馈：记忆未被使用或影响不明确
    IMPLICIT_POSITIVE = "implicit_positive"  # 隐式正向：记忆被多次使用
    IMPLICIT_NEGATIVE = "implicit_negative"  # 隐式负向：记忆长时间未被使用


class FeedbackBasedUpdater(BaseUpdater):
    """
    基于反馈信号的记忆更新器
    
    核心功能:
    1. 反馈驱动的置信度调整
    2. 基于效用的记忆淡化和删除
    3. 正向强化有用记忆
    4. 负向惩罚无用或有害记忆
    5. 时间衰减机制
    
    参数说明:
    - feedback_learning_rate: 反馈学习率 (0.1-0.5)
    - decay_rate: 时间衰减率
    - min_confidence_threshold: 最低置信度阈值，低于此值删除
    - max_memory_size: 记忆库最大容量
    """
    
    # 基础阈值
    STORAGE_THRESHOLD_PREFERENCE = 0.70
    STORAGE_THRESHOLD_FACT = 0.65
    STORAGE_THRESHOLD_EVENT = 0.65
    STORAGE_MIN_LENGTH = 5
    
    # 相似度阈值
    SIMILARITY_THRESHOLD_FOR_MERGE = 0.80
    EXACT_DUPLICATE_THRESHOLD = 0.92
    
    # 反馈学习参数
    FEEDBACK_LEARNING_RATE = 0.2  # 反馈信号对置信度的影响权重
    POSITIVE_REWARD = 0.15  # 正向反馈奖励
    NEGATIVE_PENALTY = -0.25  # 负向反馈惩罚
    IMPLICIT_POSITIVE_REWARD = 0.05  # 隐式正向奖励（每次使用）
    
    # 时间衰减参数 (基于Ebbinghaus遗忘曲线)
    DECAY_RATE = 0.1  # 衰减率
    DECAY_THRESHOLD_DAYS = 7  # 开始衰减的天数阈值
    
    # 容量管理
    MAX_MEMORY_SIZE = 100  # 记忆库最大容量
    MIN_CONFIDENCE_FOR_RETENTION = 0.3  # 保留的最低置信度
    
    def __init__(self):
        """初始化反馈更新器"""
        super().__init__()
        # 跟踪每条记忆的反馈历史
        self.feedback_history: Dict[str, List[Dict[str, Any]]] = {}
        # 跟踪记忆使用情况
        self.usage_stats: Dict[str, Dict[str, Any]] = {}
    
    async def update(
        self,
        memory_cache: List[ContextItem],
        new_knowledge: List[Knowledge],
        feedback_signals: Optional[Dict[str, FeedbackSignal]] = None
    ) -> List[ContextItem]:
        """
        基于反馈信号更新记忆库
        
        Args:
            memory_cache: 当前记忆缓存
            new_knowledge: 新提取的知识
            feedback_signals: 反馈信号字典 {memory_content: FeedbackSignal}
            
        Returns:
            更新后的记忆缓存
        """
        logger.info(f"[FeedbackUpdater] 开始更新记忆库 - 当前: {len(memory_cache)}条, 新知识: {len(new_knowledge)}条")
        
        # 第一步: 应用反馈信号调整现有记忆
        updated_cache = await self._apply_feedback_signals(memory_cache, feedback_signals or {})
        
        # 第二步: 应用时间衰减
        updated_cache = await self._apply_temporal_decay(updated_cache)
        
        # 第三步: 删除低置信度记忆
        updated_cache = await self._remove_low_confidence_memories(updated_cache)
        
        # 第四步: 添加新知识（类似SimpleUpdater但考虑反馈）
        updated_cache = await self._add_new_knowledge(updated_cache, new_knowledge)
        
        # 第五步: 容量管理 - 如果超过最大容量，保留最重要的
        updated_cache = await self._manage_capacity(updated_cache)
        
        logger.info(f"[FeedbackUpdater] 更新完成 - 最终: {len(updated_cache)}条记忆")
        
        return updated_cache
    
    async def _apply_feedback_signals(
        self,
        memory_cache: List[ContextItem],
        feedback_signals: Dict[str, FeedbackSignal]
    ) -> List[ContextItem]:
        """应用反馈信号调整记忆置信度"""
        if not feedback_signals:
            return memory_cache
        
        updated_cache = []
        feedback_applied_count = 0
        
        for item in memory_cache:
            # 检查是否有针对该记忆的反馈
            feedback = feedback_signals.get(item.content)
            
            if feedback:
                # 计算奖励/惩罚
                reward = self._calculate_reward(feedback)
                
                # 更新置信度（使用指数移动平均）
                old_score = item.score
                new_score = old_score + self.FEEDBACK_LEARNING_RATE * reward
                new_score = max(0.0, min(1.0, new_score))  # 限制在[0, 1]
                
                # 记录反馈历史
                memory_id = item.metadata.get('memory_id', item.content[:50])
                if memory_id not in self.feedback_history:
                    self.feedback_history[memory_id] = []
                
                self.feedback_history[memory_id].append({
                    'timestamp': datetime.now(),
                    'signal': feedback.value,
                    'old_score': old_score,
                    'new_score': new_score,
                    'reward': reward
                })
                
                # 更新记忆项
                item.score = new_score
                item.metadata['feedback_count'] = item.metadata.get('feedback_count', 0) + 1
                item.metadata['last_feedback'] = datetime.now()
                
                logger.debug(
                    f"[FeedbackUpdater] 应用反馈 {feedback.value}: "
                    f"{item.content[:50]}... 置信度 {old_score:.2f} → {new_score:.2f}"
                )
                feedback_applied_count += 1
            
            updated_cache.append(item)
        
        if feedback_applied_count > 0:
            logger.info(f"[FeedbackUpdater] 应用了 {feedback_applied_count} 条反馈信号")
        
        return updated_cache
    
    def _calculate_reward(self, feedback: FeedbackSignal) -> float:
        """根据反馈信号计算奖励值"""
        reward_map = {
            FeedbackSignal.POSITIVE: self.POSITIVE_REWARD,
            FeedbackSignal.NEGATIVE: self.NEGATIVE_PENALTY,
            FeedbackSignal.NEUTRAL: 0.0,
            FeedbackSignal.IMPLICIT_POSITIVE: self.IMPLICIT_POSITIVE_REWARD,
            FeedbackSignal.IMPLICIT_NEGATIVE: -self.IMPLICIT_POSITIVE_REWARD,
        }
        return reward_map.get(feedback, 0.0)
    
    async def _apply_temporal_decay(self, memory_cache: List[ContextItem]) -> List[ContextItem]:
        """
        应用时间衰减机制（基于Ebbinghaus遗忘曲线）
        
        衰减公式: score_new = score_old * exp(-decay_rate * days_since_access)
        """
        now = datetime.now()
        decayed_count = 0
        
        for item in memory_cache:
            # 获取最后访问时间
            last_accessed = item.metadata.get('last_accessed', item.timestamp)
            days_since_access = (now - last_accessed).days
            
            # 只对超过阈值天数的记忆应用衰减
            if days_since_access > self.DECAY_THRESHOLD_DAYS:
                # 计算衰减因子 (指数衰减)
                decay_factor = math.exp(-self.DECAY_RATE * (days_since_access - self.DECAY_THRESHOLD_DAYS))
                
                old_score = item.score
                new_score = old_score * decay_factor
                
                if new_score != old_score:
                    item.score = new_score
                    item.metadata['decayed'] = True
                    item.metadata['decay_factor'] = decay_factor
                    decayed_count += 1
                    
                    logger.debug(
                        f"[FeedbackUpdater] 时间衰减: {item.content[:50]}... "
                        f"({days_since_access}天未访问) 置信度 {old_score:.2f} → {new_score:.2f}"
                    )
        
        if decayed_count > 0:
            logger.info(f"[FeedbackUpdater] 应用时间衰减: {decayed_count} 条记忆")
        
        return memory_cache
    
    async def _remove_low_confidence_memories(self, memory_cache: List[ContextItem]) -> List[ContextItem]:
        """删除低置信度记忆"""
        before_count = len(memory_cache)
        
        # 过滤掉低于最低阈值的记忆
        filtered_cache = [
            item for item in memory_cache
            if item.score >= self.MIN_CONFIDENCE_FOR_RETENTION
        ]
        
        removed_count = before_count - len(filtered_cache)
        if removed_count > 0:
            logger.info(
                f"[FeedbackUpdater] 删除低置信度记忆: {removed_count} 条 "
                f"(阈值: {self.MIN_CONFIDENCE_FOR_RETENTION})"
            )
        
        return filtered_cache
    
    async def _add_new_knowledge(
        self,
        memory_cache: List[ContextItem],
        new_knowledge: List[Knowledge]
    ) -> List[ContextItem]:
        """添加新知识（类似SimpleUpdater但初始置信度略低，需要反馈强化）"""
        if not new_knowledge:
            return memory_cache
        
        # 质量过滤
        filtered_knowledge = []
        for k in new_knowledge:
            min_confidence = {
                KnowledgeType.PREFERENCE: self.STORAGE_THRESHOLD_PREFERENCE,
                KnowledgeType.FACT: self.STORAGE_THRESHOLD_FACT,
                KnowledgeType.EVENT: self.STORAGE_THRESHOLD_EVENT,
            }.get(k.type, self.STORAGE_THRESHOLD_FACT)
            
            if (k.confidence >= min_confidence 
                and len(k.content.strip()) >= self.STORAGE_MIN_LENGTH
                and not k.content.isdigit()):
                filtered_knowledge.append(k)
        
        logger.info(f"[FeedbackUpdater] 新知识过滤: {len(new_knowledge)} → {len(filtered_knowledge)}")
        
        # 合并和去重逻辑（类似SimpleUpdater）
        updated_cache = list(memory_cache)
        new_items = []
        merged_count = 0
        
        for k in filtered_knowledge:
            formatted_content = f"[{k.type.value.upper()}] {k.content}"
            
            # 检查相似度
            merge_target_idx = None
            max_similarity = 0.0
            
            for idx, existing in enumerate(updated_cache):
                similarity = self._calculate_similarity_with_embedding(k, existing)
                
                if similarity >= self.EXACT_DUPLICATE_THRESHOLD:
                    merge_target_idx = -1  # 完全重复
                    break
                
                if similarity >= self.SIMILARITY_THRESHOLD_FOR_MERGE and similarity > max_similarity:
                    max_similarity = similarity
                    merge_target_idx = idx
            
            if merge_target_idx == -1:
                continue  # 跳过重复
            elif merge_target_idx is not None:
                # 合并：取较高置信度
                existing_item = updated_cache[merge_target_idx]
                if k.confidence > existing_item.score:
                    updated_cache[merge_target_idx] = ContextItem(
                        content=formatted_content,
                        source=ContextSource.MEMORY,
                        score=k.confidence,
                        timestamp=datetime.now(),
                        embeddings=k.embeddings,
                        metadata={
                            **k.metadata,
                            'updated': True,
                            'previous_score': existing_item.score,
                            'last_accessed': datetime.now()
                        }
                    )
                    merged_count += 1
            else:
                # 新增记忆 - 初始置信度设置为提取置信度的90%，留空间让反馈强化
                initial_score = k.confidence * 0.9
                new_items.append(ContextItem(
                    content=formatted_content,
                    source=ContextSource.MEMORY,
                    score=initial_score,
                    timestamp=datetime.now(),
                    embeddings=k.embeddings,
                    metadata={
                        **k.metadata,
                        'last_accessed': datetime.now(),
                        'access_count': 0,
                        'feedback_count': 0
                    }
                ))
        
        if new_items:
            updated_cache.extend(new_items)
            logger.info(f"[FeedbackUpdater] 新增 {len(new_items)} 条记忆, 合并 {merged_count} 条")
        
        return updated_cache
    
    def _calculate_similarity_with_embedding(self, knowledge: Knowledge, existing: ContextItem) -> float:
        """计算相似度（优先使用嵌入向量）"""
        if knowledge.embeddings and existing.embeddings:
            knowledge_emb = knowledge.embeddings.get('default')
            existing_emb = existing.embeddings.get('default')
            
            if knowledge_emb and existing_emb:
                similarity, success = calculate_embedding_similarity(
                    knowledge_emb.vector if hasattr(knowledge_emb, 'vector') else knowledge_emb,
                    existing_emb.vector if hasattr(existing_emb, 'vector') else existing_emb
                )
                if success:
                    return similarity
        
        # 回退到文本相似度
        import re
        formatted_content = f"[{knowledge.type.value.upper()}] {knowledge.content}"
        clean1 = re.sub(r'\[.*?\]\s*', '', formatted_content).strip().lower()
        clean2 = re.sub(r'\[.*?\]\s*', '', existing.content).strip().lower()
        
        if not clean1 or not clean2:
            return 0.0
        
        # Jaccard相似度
        chars1 = set(c for c in clean1 if c.strip() and c not in '，。！？,.!?；:：')
        chars2 = set(c for c in clean2 if c.strip() and c not in '，。！？,.!?；:：')
        
        if not chars1 or not chars2:
            return 0.0
        
        intersection = len(chars1 & chars2)
        union = len(chars1 | chars2)
        
        return intersection / union if union > 0 else 0.0
    
    async def _manage_capacity(self, memory_cache: List[ContextItem]) -> List[ContextItem]:
        """
        容量管理：如果超过最大容量，保留最重要的记忆
        
        重要性评分 = 0.5 * confidence + 0.3 * recency + 0.2 * feedback_quality
        """
        if len(memory_cache) <= self.MAX_MEMORY_SIZE:
            return memory_cache
        
        logger.info(
            f"[FeedbackUpdater] 记忆库超过容量 ({len(memory_cache)} > {self.MAX_MEMORY_SIZE}), "
            f"执行容量管理"
        )
        
        # 计算每条记忆的重要性分数
        now = datetime.now()
        scored_memories = []
        
        for item in memory_cache:
            # 置信度权重: 50%
            confidence_score = item.score * 0.5
            
            # 新近性权重: 30% (最近访问的更重要)
            last_accessed = item.metadata.get('last_accessed', item.timestamp)
            days_since_access = (now - last_accessed).days
            recency_score = math.exp(-0.1 * days_since_access) * 0.3
            
            # 反馈质量权重: 20% (有正向反馈的更重要)
            feedback_count = item.metadata.get('feedback_count', 0)
            feedback_score = min(feedback_count * 0.05, 0.2)
            
            importance = confidence_score + recency_score + feedback_score
            
            scored_memories.append((importance, item))
        
        # 按重要性排序，保留前MAX_MEMORY_SIZE条
        scored_memories.sort(key=lambda x: x[0], reverse=True)
        retained_cache = [item for _, item in scored_memories[:self.MAX_MEMORY_SIZE]]
        
        removed_count = len(memory_cache) - len(retained_cache)
        logger.info(f"[FeedbackUpdater] 容量管理完成 - 删除 {removed_count} 条低重要性记忆")
        
        return retained_cache
    
    def record_memory_usage(self, memory_content: str, was_helpful: bool):
        """
        记录记忆使用情况（用于生成隐式反馈）
        
        Args:
            memory_content: 记忆内容
            was_helpful: 是否有帮助
        """
        if memory_content not in self.usage_stats:
            self.usage_stats[memory_content] = {
                'use_count': 0,
                'helpful_count': 0,
                'last_used': None
            }
        
        stats = self.usage_stats[memory_content]
        stats['use_count'] += 1
        if was_helpful:
            stats['helpful_count'] += 1
        stats['last_used'] = datetime.now()
    
    def generate_implicit_feedback(self) -> Dict[str, FeedbackSignal]:
        """
        基于使用统计生成隐式反馈信号
        
        Returns:
            隐式反馈信号字典
        """
        feedback_signals = {}
        now = datetime.now()
        
        for content, stats in self.usage_stats.items():
            # 如果经常被使用且有帮助，给予正向反馈
            if stats['use_count'] >= 3:
                helpfulness_ratio = stats['helpful_count'] / stats['use_count']
                if helpfulness_ratio >= 0.6:
                    feedback_signals[content] = FeedbackSignal.IMPLICIT_POSITIVE
                elif helpfulness_ratio <= 0.3:
                    feedback_signals[content] = FeedbackSignal.IMPLICIT_NEGATIVE
            
            # 如果长时间未使用，给予负向反馈
            if stats['last_used']:
                days_unused = (now - stats['last_used']).days
                if days_unused > 14:  # 2周未使用
                    feedback_signals[content] = FeedbackSignal.IMPLICIT_NEGATIVE
        
        return feedback_signals
