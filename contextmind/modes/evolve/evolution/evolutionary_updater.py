"""
进化式记忆更新器

借鉴进化算法思想，通过适应度评估、精英选择、记忆合并和容量控制维持高质量记忆库。
"""

from typing import List, Optional, Dict, Any, Tuple
import time
from datetime import datetime

from ..core.data_models import ContextItem, Knowledge
from ..core.types import ContextSource
from ..core.strategies import UpdateStrategy as BaseUpdater
from contextmind.infra.logger import get_logger
from contextmind.infra.embedding import calculate_embedding_similarity

from ..memory.memory_fitness import MemoryFitness, FitnessCalculator

logger = get_logger(__name__)


class EvolutionaryMemoryUpdater(BaseUpdater):
    """
    进化式记忆更新器，通过适应度评估、精英选择、相似记忆合并和容量控制优化记忆库。
    """
    
    def __init__(
        self,
        max_memory_size: int = 100,
        elite_ratio: float = 0.7,
        similarity_threshold: float = 0.85,
        min_fitness_threshold: float = 0.2,
        fitness_weights: Optional[Dict[str, float]] = None,
        enable_decay: bool = True
    ):
        """
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
        self.fitness_calculator = FitnessCalculator(weights=fitness_weights)
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
        进化式更新记忆库。

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
        
        evaluated_cache = self._evaluate_fitness(memory_cache)
        elite_memories = self._elite_selection(evaluated_cache)
        logger.debug(f"[EvolutionaryUpdater] 精英选择: {len(memory_cache)} → {len(elite_memories)} 条记忆")
        
        filtered_knowledge = self._filter_knowledge(new_knowledge)
        logger.debug(f"[EvolutionaryUpdater] 知识过滤: {len(new_knowledge)} → {len(filtered_knowledge)} 条知识")
        
        merged_cache, new_items = self._merge_memories(elite_memories, filtered_knowledge)
        logger.info(
            f"[EvolutionaryUpdater] 记忆合并: 合并 {self.stats['merges']} 对, "
            f"新增 {len(new_items)} 条"
        )
        
        updated_cache = merged_cache + new_items
        final_cache = self._capacity_control(updated_cache)
        
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
        """为每条记忆计算适应度分数并更新到 metadata。"""
        evaluated = []
        
        for memory in memories:
            fitness_score = self.fitness_calculator.calculate_fitness_score(memory)
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
        """保留适应度最高的记忆（精英保留策略）。"""
        if not memories:
            return []
        
        sorted_memories = sorted(
            memories,
            key=lambda m: m.metadata.get('fitness_score', 0.0),
            reverse=True
        )
        elite_count = max(1, int(len(sorted_memories) * self.elite_ratio))
        elite = sorted_memories[:elite_count]
        evicted = len(sorted_memories) - elite_count
        if evicted > 0:
            self.stats['evictions'] += evicted
            logger.debug(f"[EvolutionaryUpdater] 初步淘汰 {evicted} 条低适应度记忆")
        
        return elite
    
    def _filter_knowledge(self, knowledge_list: List[Knowledge]) -> List[Knowledge]:
        """过滤低质量新知识，确保只添加满足置信度和长度要求的条目。"""
        from evolve.core.types import KnowledgeType
        
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
        合并相似记忆：对相似的新旧记忆取置信度更高的版本，无匹配的新增。

        Returns:
            (更新后的现有记忆, 新增的记忆项)
        """
        updated_existing = list(existing_memories)
        new_items = []
        merge_count = 0
        
        for k in new_knowledge:
            formatted_content = f"[{k.type.value.upper()}] {k.content}"
            
            best_match_idx = None
            best_similarity = 0.0
            
            for idx, existing in enumerate(updated_existing):
                similarity = self._calculate_similarity(k, existing)
                
                if similarity >= self.similarity_threshold and similarity > best_similarity:
                    best_similarity = similarity
                    best_match_idx = idx
            
            if best_match_idx is not None:
                existing_item = updated_existing[best_match_idx]
                
                if k.confidence > existing_item.score:
                    logger.debug(
                        f"[EvolutionaryUpdater] 🔄 合并记忆 "
                        f"(相似度={best_similarity:.2f}, 新置信度={k.confidence:.2f} > 旧={existing_item.score:.2f})"
                    )
                    
                    old_fitness = self.fitness_calculator.get_fitness(existing_item)
                    
                    updated_existing[best_match_idx] = ContextItem(
                        content=formatted_content,
                        source=ContextSource.MEMORY,
                        score=k.confidence,
                        timestamp=datetime.now(),
                        embeddings=k.embeddings,
                        metadata={
                            **k.metadata,
                            'merged': True,
                            'usage_count': old_fitness.usage_count,
                            'last_used': old_fitness.last_used,
                            'accuracy': old_fitness.accuracy,
                            'previous_score': existing_item.score
                        }
                    )
                    merge_count += 1
                    self.stats['merges'] += 1
            else:
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
        计算知识与记忆的相似度，优先使用嵌入向量，回退到 Jaccard 字符集相似度。

        Returns:
            相似度分数 (0-1)
        """
        if knowledge.embeddings and memory.embeddings:
            knowledge_emb = knowledge.embeddings.get('default')
            memory_emb = memory.embeddings.get('default')
            
            if knowledge_emb and memory_emb:
                similarity, success = calculate_embedding_similarity(knowledge_emb, memory_emb)
                if success:
                    return similarity
        
        import re
        formatted_content = f"[{knowledge.type.value.upper()}] {knowledge.content}"
        
        clean1 = re.sub(r'\[.*?\]\s*', '', formatted_content).strip().lower()
        clean2 = re.sub(r'\[.*?\]\s*', '', memory.content).strip().lower()
        
        if not clean1 or not clean2:
            return 0.0
        
        chars1 = set(c for c in clean1 if c.strip() and c not in '，。！？,.!?；:：')
        chars2 = set(c for c in clean2 if c.strip() and c not in '，。！？,.!?；:：')
        
        if not chars1 or not chars2:
            return 0.0
        
        intersection = len(chars1 & chars2)
        union = len(chars1 | chars2)
        
        return intersection / union if union > 0 else 0.0
    
    def _capacity_control(self, memories: List[ContextItem]) -> List[ContextItem]:
        """当记忆数量超过上限时，淘汰低适应度的记忆。"""
        if len(memories) <= self.max_memory_size:
            return memories
        
        evaluated = self._evaluate_fitness(memories)
        sorted_memories = sorted(
            evaluated,
            key=lambda m: m.metadata.get('fitness_score', 0.0),
            reverse=True
        )
        kept = sorted_memories[:self.max_memory_size]
        evicted = len(sorted_memories) - self.max_memory_size
        
        if evicted > 0:
            self.stats['evictions'] += evicted
            logger.info(f"[EvolutionaryUpdater] 容量控制: 淘汰 {evicted} 条低适应度记忆")
        
        return kept
    
    def get_stats(self) -> Dict[str, Any]:
        """获取更新器统计信息。"""
        return {
            **self.stats,
            'max_memory_size': self.max_memory_size,
            'elite_ratio': self.elite_ratio,
            'similarity_threshold': self.similarity_threshold
        }
