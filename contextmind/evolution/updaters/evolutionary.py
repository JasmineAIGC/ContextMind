"""
进化式记忆更新器

借鉴 AlphaEvolve 和 ThetaEvolve 的进化思想，实现对话任务中记忆库的智能优化。
通过适应度评估、选择、合并和淘汰等进化操作，维持高质量的记忆库。

核心思想：
- 将记忆库视为一个进化的"种群"
- 每条记忆是种群中的一个"个体"
- 通过适应度函数评估记忆的价值
- 应用选择、变异、交叉等进化操作优化记忆库
"""

from typing import List, Optional, Dict, Any, Tuple
import time
from datetime import datetime

from contextmind.core.data_models import ContextItem, Knowledge
from contextmind.core.types import ContextSource
from contextmind.core.strategies import UpdateStrategy as BaseUpdater
from contextmind.utils.logger import get_logger
from contextmind.utils.embedding import calculate_embedding_similarity

from contextmind.memory.memory_fitness import MemoryFitness, FitnessCalculator

logger = get_logger(__name__)


class EvolutionaryMemoryUpdater(BaseUpdater):
    """
    进化式记忆更新器
    
    借鉴进化算法思想，通过以下机制优化记忆库：
    
    1. **适应度评估**: 评估每条记忆的价值（使用频率、准确性、新鲜度）
    2. **精英选择**: 保留高适应度的优质记忆
    3. **记忆合并**: 合并相似记忆（类似交叉操作）
    4. **记忆更新**: 基于新知识更新记忆（类似变异操作）
    5. **容量控制**: 淘汰低适应度记忆，维持合理容量
    
    与 AlphaEvolve/ThetaEvolve 的对应关系：
    - 候选解 → 记忆条目
    - 适应度 → 记忆有用性
    - 种群 → 记忆库
    - 进化 → 对话驱动的更新
    """
    
    def __init__(
        self,
        max_memory_size: int = 100,
        elite_ratio: float = 0.7,  # 保留前70%的记忆
        similarity_threshold: float = 0.85,  # 相似度阈值（用于合并）
        min_fitness_threshold: float = 0.2,  # 最低适应度阈值
        fitness_weights: Optional[Dict[str, float]] = None,
        enable_decay: bool = True  # 是否启用使用次数衰减
    ):
        """
        初始化进化式记忆更新器
        
        Args:
            max_memory_size: 记忆库最大容量
            elite_ratio: 精英保留比例（0-1）
            similarity_threshold: 记忆合并的相似度阈值
            min_fitness_threshold: 淘汰的最低适应度阈值
            fitness_weights: 适应度计算权重配置
            enable_decay: 是否启用使用次数衰减
        """
        self.max_memory_size = max_memory_size
        self.elite_ratio = elite_ratio
        self.similarity_threshold = similarity_threshold
        self.min_fitness_threshold = min_fitness_threshold
        self.enable_decay = enable_decay
        
        # 适应度计算器
        self.fitness_calculator = FitnessCalculator(weights=fitness_weights)
        
        # 统计信息
        self.stats = {
            'updates': 0,
            'merges': 0,
            'evictions': 0,
            'additions': 0
        }
        
        logger.info(
            f"[EvolutionaryUpdater] 初始化 - max_size={max_memory_size}, "
            f"elite_ratio={elite_ratio}, similarity_threshold={similarity_threshold}"
        )
    
    async def update(
        self,
        memory_cache: List[ContextItem],
        new_knowledge: List[Knowledge]
    ) -> List[ContextItem]:
        """
        进化式更新记忆库
        
        核心流程：
        1. 适应度评估：计算所有现有记忆的适应度
        2. 精英选择：保留高适应度记忆
        3. 知识过滤：过滤低质量新知识
        4. 记忆合并：合并新旧记忆中的相似项
        5. 添加新记忆：加入高质量新知识
        6. 容量控制：淘汰低适应度记忆
        
        Args:
            memory_cache: 当前记忆库
            new_knowledge: 新提取的知识
            
        Returns:
            更新后的记忆库
        """
        self.stats['updates'] += 1
        
        if not new_knowledge:
            logger.debug("[EvolutionaryUpdater] 无新知识，跳过更新")
            return memory_cache
        
        logger.info(
            f"[EvolutionaryUpdater] 开始进化式更新 - "
            f"现有记忆={len(memory_cache)}, 新知识={len(new_knowledge)}"
        )
        
        # 阶段1: 适应度评估（为现有记忆计算适应度）
        evaluated_cache = self._evaluate_fitness(memory_cache)
        
        # 阶段2: 精英选择（保留高质量记忆）
        elite_memories = self._elite_selection(evaluated_cache)
        logger.debug(f"[EvolutionaryUpdater] 精英选择: {len(memory_cache)} → {len(elite_memories)} 条记忆")
        
        # 阶段3: 过滤低质量新知识
        filtered_knowledge = self._filter_knowledge(new_knowledge)
        logger.debug(f"[EvolutionaryUpdater] 知识过滤: {len(new_knowledge)} → {len(filtered_knowledge)} 条知识")
        
        # 阶段4: 记忆合并（检测相似记忆并合并）
        merged_cache, new_items = self._merge_memories(elite_memories, filtered_knowledge)
        logger.info(
            f"[EvolutionaryUpdater] 记忆合并: 合并 {self.stats['merges']} 对, "
            f"新增 {len(new_items)} 条"
        )
        
        # 阶段5: 添加新记忆
        updated_cache = merged_cache + new_items
        
        # 阶段6: 容量控制（淘汰低适应度记忆）
        final_cache = self._capacity_control(updated_cache)
        
        # 可选：使用次数衰减（防止旧记忆永久霸占位置）
        if self.enable_decay:
            final_cache = self.fitness_calculator.decay_usage_counts(final_cache)
        
        logger.info(
            f"[EvolutionaryUpdater] ✓ 更新完成 - "
            f"最终记忆数={len(final_cache)}, "
            f"新增={self.stats['additions']}, 合并={self.stats['merges']}, "
            f"淘汰={self.stats['evictions']}"
        )
        
        return final_cache
    
    def _evaluate_fitness(self, memories: List[ContextItem]) -> List[ContextItem]:
        """
        评估所有记忆的适应度
        
        为每条记忆计算适应度分数，并更新到 metadata 中。
        
        Args:
            memories: 记忆列表
            
        Returns:
            带有适应度评分的记忆列表
        """
        evaluated = []
        
        for memory in memories:
            # 计算适应度分数
            fitness_score = self.fitness_calculator.calculate_fitness_score(memory)
            
            # 更新 metadata
            updated_metadata = {
                **(memory.metadata or {}),
                'fitness_score': fitness_score
            }
            
            evaluated_memory = ContextItem(
                content=memory.content,
                source=memory.source,
                score=memory.score,
                timestamp=memory.timestamp,
                embeddings=memory.embeddings,
                metadata=updated_metadata
            )
            evaluated.append(evaluated_memory)
        
        return evaluated
    
    def _elite_selection(self, memories: List[ContextItem]) -> List[ContextItem]:
        """
        精英选择策略
        
        保留适应度最高的记忆（类似进化算法中的精英保留）。
        
        Args:
            memories: 评估后的记忆列表
            
        Returns:
            精英记忆列表
        """
        if not memories:
            return []
        
        # 按适应度分数排序
        sorted_memories = sorted(
            memories,
            key=lambda m: m.metadata.get('fitness_score', 0.0),
            reverse=True
        )
        
        # 计算精英数量
        elite_count = max(1, int(len(sorted_memories) * self.elite_ratio))
        
        # 保留前N个精英
        elite = sorted_memories[:elite_count]
        
        # 统计被淘汰的记忆
        evicted = len(sorted_memories) - elite_count
        if evicted > 0:
            self.stats['evictions'] += evicted
            logger.debug(f"[EvolutionaryUpdater] 初步淘汰 {evicted} 条低适应度记忆")
        
        return elite
    
    def _filter_knowledge(self, knowledge_list: List[Knowledge]) -> List[Knowledge]:
        """
        过滤低质量新知识
        
        借鉴 SimpleUpdater 的过滤逻辑，确保只添加高质量知识。
        
        Args:
            knowledge_list: 新知识列表
            
        Returns:
            过滤后的知识列表
        """
        from contextmind.core.types import KnowledgeType
        
        # 质量阈值（继承自 SimpleUpdater）
        THRESHOLD_PREFERENCE = 0.75
        THRESHOLD_FACT = 0.70
        THRESHOLD_EVENT = 0.70
        MIN_LENGTH = 5
        
        filtered = []
        for k in knowledge_list:
            min_confidence = {
                KnowledgeType.PREFERENCE: THRESHOLD_PREFERENCE,
                KnowledgeType.FACT: THRESHOLD_FACT,
                KnowledgeType.EVENT: THRESHOLD_EVENT,
            }.get(k.type, THRESHOLD_FACT)
            
            if (k.confidence >= min_confidence 
                and len(k.content.strip()) >= MIN_LENGTH
                and not k.content.isdigit()):
                filtered.append(k)
        
        return filtered
    
    def _merge_memories(
        self,
        existing_memories: List[ContextItem],
        new_knowledge: List[Knowledge]
    ) -> Tuple[List[ContextItem], List[ContextItem]]:
        """
        合并相似记忆（类似遗传算法的交叉操作）
        
        检测新旧记忆中的相似项，并进行合并或更新。
        这是进化思想的核心应用之一。
        
        Args:
            existing_memories: 现有记忆列表
            new_knowledge: 新知识列表
            
        Returns:
            (更新后的现有记忆, 新增的记忆项)
        """
        updated_existing = list(existing_memories)
        new_items = []
        merge_count = 0
        
        for k in new_knowledge:
            formatted_content = f"[{k.type.value.upper()}] {k.content}"
            
            # 寻找相似的现有记忆
            best_match_idx = None
            best_similarity = 0.0
            
            for idx, existing in enumerate(updated_existing):
                similarity = self._calculate_similarity(k, existing)
                
                if similarity >= self.similarity_threshold and similarity > best_similarity:
                    best_similarity = similarity
                    best_match_idx = idx
            
            if best_match_idx is not None:
                # 找到相似记忆，执行合并
                existing_item = updated_existing[best_match_idx]
                
                # 选择置信度更高的版本（适者生存）
                if k.confidence > existing_item.score:
                    logger.debug(
                        f"[EvolutionaryUpdater] 🔄 合并记忆 "
                        f"(相似度={best_similarity:.2f}, 新置信度={k.confidence:.2f} > 旧={existing_item.score:.2f})"
                    )
                    
                    # 继承旧记忆的适应度信息
                    old_fitness = self.fitness_calculator.get_fitness(existing_item)
                    
                    # 创建新记忆，保留使用统计
                    updated_existing[best_match_idx] = ContextItem(
                        content=formatted_content,
                        source=ContextSource.MEMORY,
                        score=k.confidence,
                        timestamp=datetime.now(),
                        embeddings=k.embeddings,
                        metadata={
                            **k.metadata,
                            'merged': True,
                            'usage_count': old_fitness.usage_count,  # 继承使用次数
                            'last_used': old_fitness.last_used,      # 继承最后使用时间
                            'accuracy': old_fitness.accuracy,        # 继承准确性
                            'previous_score': existing_item.score
                        }
                    )
                    merge_count += 1
                    self.stats['merges'] += 1
                # else: 保留旧记忆（置信度更高）
            else:
                # 没有相似记忆，作为新项添加
                new_items.append(ContextItem(
                    content=formatted_content,
                    source=ContextSource.MEMORY,
                    score=k.confidence,
                    timestamp=datetime.now(),
                    embeddings=k.embeddings,
                    metadata={
                        **k.metadata,
                        'usage_count': 0,
                        'creation_time': time.time()
                    }
                ))
                self.stats['additions'] += 1
        
        return updated_existing, new_items
    
    def _calculate_similarity(self, knowledge: Knowledge, memory: ContextItem) -> float:
        """
        计算知识与记忆的相似度
        
        优先使用嵌入向量，回退到文本相似度。
        
        Args:
            knowledge: 新知识
            memory: 现有记忆
            
        Returns:
            相似度分数 (0-1)
        """
        # 优先使用嵌入向量
        if knowledge.embeddings and memory.embeddings:
            knowledge_emb = knowledge.embeddings.get('default')
            memory_emb = memory.embeddings.get('default')
            
            if knowledge_emb and memory_emb:
                similarity, success = calculate_embedding_similarity(knowledge_emb, memory_emb)
                if success:
                    return similarity
        
        # 回退到文本相似度
        import re
        formatted_content = f"[{knowledge.type.value.upper()}] {knowledge.content}"
        
        clean1 = re.sub(r'\[.*?\]\s*', '', formatted_content).strip().lower()
        clean2 = re.sub(r'\[.*?\]\s*', '', memory.content).strip().lower()
        
        if not clean1 or not clean2:
            return 0.0
        
        # Jaccard 相似度
        chars1 = set(c for c in clean1 if c.strip() and c not in '，。！？,.!?；:：')
        chars2 = set(c for c in clean2 if c.strip() and c not in '，。！？,.!?；:：')
        
        if not chars1 or not chars2:
            return 0.0
        
        intersection = len(chars1 & chars2)
        union = len(chars1 | chars2)
        
        return intersection / union if union > 0 else 0.0
    
    def _capacity_control(self, memories: List[ContextItem]) -> List[ContextItem]:
        """
        容量控制（淘汰机制）
        
        当记忆数量超过上限时，淘汰低适应度的记忆。
        确保记忆库保持在合理大小。
        
        Args:
            memories: 记忆列表
            
        Returns:
            容量控制后的记忆列表
        """
        if len(memories) <= self.max_memory_size:
            return memories
        
        # 重新评估适应度（因为可能有新添加的记忆）
        evaluated = self._evaluate_fitness(memories)
        
        # 按适应度排序
        sorted_memories = sorted(
            evaluated,
            key=lambda m: m.metadata.get('fitness_score', 0.0),
            reverse=True
        )
        
        # 保留前 max_memory_size 个
        kept = sorted_memories[:self.max_memory_size]
        evicted = len(sorted_memories) - self.max_memory_size
        
        if evicted > 0:
            self.stats['evictions'] += evicted
            logger.info(f"[EvolutionaryUpdater] 容量控制: 淘汰 {evicted} 条低适应度记忆")
        
        return kept
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取更新器统计信息
        
        Returns:
            统计信息字典
        """
        return {
            **self.stats,
            'max_memory_size': self.max_memory_size,
            'elite_ratio': self.elite_ratio,
            'similarity_threshold': self.similarity_threshold
        }
