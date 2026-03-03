"""
记忆更新器 - 记忆更新的插件实现

该模块提供各种策略用于更新和维护记忆库（增加、更新、删除操作）。
"""

from typing import List, Optional
import re
from datetime import datetime

from ..core.data_models import ContextItem, Knowledge
from ..core.types import ContextSource, KnowledgeType
from contextmind.infra.logger import get_logger
from ..core.strategies import UpdateStrategy as BaseUpdater  # Use core base class
from contextmind.infra.embedding import calculate_embedding_similarity

logger = get_logger(__name__)


class SimpleUpdater(BaseUpdater):
    """简单记忆更新器，基本的增加/更新/去重逻辑，支持记忆合并。"""
    
    # Storage threshold rationale: preferences require higher confidence than
    # facts/events because a wrong preference silently degrades every future
    # interaction, while an incorrect fact is more likely to be caught and
    # corrected through explicit user feedback.
    STORAGE_THRESHOLD_PREFERENCE = 0.80  # 0.75 → 0.80
    STORAGE_THRESHOLD_FACT = 0.75  # 0.70 → 0.75
    STORAGE_THRESHOLD_EVENT = 0.75  # 0.70 → 0.75
    STORAGE_MIN_LENGTH = 5  # 3 → 5 最小字符数
    
    # 80% merge threshold prevents semantically distinct facts from being collapsed.
    # 92% duplicate threshold is strict enough to catch only near-verbatim repeats,
    # avoiding the memory pool stagnation that a lower threshold would cause.
    SIMILARITY_THRESHOLD_FOR_MERGE = 0.80  # 提高到80%，避免误判不同事实为相似（修复记忆库不增长问题）
    EXACT_DUPLICATE_THRESHOLD = 0.92  # 提高到92%，更精确地识别完全重复项
    
    async def update(
        self,
        memory_cache: List[ContextItem],
        new_knowledge: List[Knowledge]
    ) -> List[ContextItem]:
        """
        更新记忆缓存：过滤低质量知识、检测相似记忆并合并、添加新条目。

        Args:
            memory_cache: 当前缓存
            new_knowledge: 新知识

        Returns:
            更新后的缓存
        """
        if not new_knowledge:
            logger.debug("[SimpleUpdater] 没有知识需要存储")
            return memory_cache
        
        logger.info(f"[SimpleUpdater] 开始存储知识 - 收到 {len(new_knowledge)} 条知识项")
        
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
            else:
                if k.confidence < min_confidence:
                    reason = f"置信度不足 ({k.confidence:.2f} < {min_confidence:.2f})"
                elif len(k.content.strip()) < self.STORAGE_MIN_LENGTH:
                    reason = f"内容过短 ({len(k.content.strip())} < {self.STORAGE_MIN_LENGTH})"
                else:  # k.content.isdigit()
                    reason = "纯数字内容"
                logger.debug(f"[SimpleUpdater] 过滤低质量知识 ({reason}): [{k.type.value}] {k.content[:50]}...")
        
        if len(filtered_knowledge) < len(new_knowledge):
            logger.info(f"[SimpleUpdater] 质量过滤: {len(new_knowledge)} → {len(filtered_knowledge)} 条知识")
        
        updated_cache = list(memory_cache)
        new_items = []
        merged_count = 0
        
        for k in filtered_knowledge:
            formatted_content = f"[{k.type.value.upper()}] {k.content}"
            
            merge_target_idx = None
            max_similarity = 0.0
            
            for idx, existing in enumerate(updated_cache):
                similarity = self._calculate_similarity_with_embedding(k, existing)
                
                if similarity >= self.EXACT_DUPLICATE_THRESHOLD:
                    logger.debug(f"[SimpleUpdater] 跳过完全重复知识 (相似度={similarity:.2f}): {formatted_content[:50]}...")
                    # Sentinel -1 means "skip entirely" (exact duplicate), distinct from
                    # None (no match found) and a valid index (merge candidate found).
                    merge_target_idx = -1
                    break
                
                if similarity >= self.SIMILARITY_THRESHOLD_FOR_MERGE and similarity > max_similarity:
                    max_similarity = similarity
                    merge_target_idx = idx
            
            if merge_target_idx == -1:
                continue
            elif merge_target_idx is not None:
                existing_item = updated_cache[merge_target_idx]
                
                # Only replace if the new knowledge has higher confidence; otherwise
                # retain the existing entry to avoid overwriting well-established facts
                # with noisier extractions from less reliable message contexts.
                if k.confidence > existing_item.score:
                    logger.info(f"[SimpleUpdater] 🔄 合并记忆 (相似度={max_similarity:.2f}, 新置信度={k.confidence:.2f} > 旧={existing_item.score:.2f})")
                    logger.debug(f"  旧: {existing_item.content[:60]}...")
                    logger.debug(f"  新: {formatted_content[:60]}...")
                    
                    updated_cache[merge_target_idx] = ContextItem(
                        content=formatted_content,
                        source=ContextSource.MEMORY,
                        score=k.confidence,
                        timestamp=datetime.now(),  # 更新时间戳
                        embeddings=k.embeddings,  # 保留嵌入向量
                        metadata={**k.metadata, 'updated': True, 'previous_score': existing_item.score}
                    )
                    merged_count += 1
                else:
                    logger.debug(f"[SimpleUpdater] 保留旧记忆 (相似度={max_similarity:.2f}, 旧置信度={existing_item.score:.2f} >= 新={k.confidence:.2f}): {existing_item.content[:50]}...")
            else:
                new_items.append(ContextItem(
                    content=formatted_content,
                    source=ContextSource.MEMORY,
                    score=k.confidence,
                    timestamp=datetime.now(),
                    embeddings=k.embeddings,  # 添加嵌入向量
                    metadata=k.metadata
                ))
                logger.debug(f"[SimpleUpdater] 已存储: {formatted_content[:80]}...")
        
        if not new_items and merged_count == 0:
            logger.info("[SimpleUpdater] 所有知识项均为重复或低质量，未存储新内容")
            return updated_cache
        
        if new_items:
            updated_cache.extend(new_items)
        
        logger.info(f"[SimpleUpdater] ✓ 存储完成 - 新增 {len(new_items)} 条知识, 合并/更新 {merged_count} 条")
        logger.info(f"[SimpleUpdater] 当前记忆库总计: {len(updated_cache)} 条记忆")
        
        return updated_cache
    
    def _calculate_similarity_with_embedding(self, knowledge: Knowledge, existing: ContextItem) -> float:
        """计算知识与现有记忆的相似度，优先使用嵌入向量。"""
        if knowledge.embeddings and existing.embeddings:
            knowledge_emb = knowledge.embeddings.get('default')
            existing_emb = existing.embeddings.get('default')
            
            if knowledge_emb and existing_emb:
                similarity, success = calculate_embedding_similarity(knowledge_emb, existing_emb)
                if success:
                    return similarity
        
        formatted_content = f"[{knowledge.type.value.upper()}] {knowledge.content}"
        return self._calculate_similarity(formatted_content, existing.content)
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Character-set Jaccard similarity after stripping type-tag prefixes.

        Type tags like [PREFERENCE] are removed before comparison so that two
        memories with different tags but identical content are correctly detected
        as duplicates. Punctuation is excluded to avoid inflating similarity
        between unrelated sentences that share only common delimiters.
        """
        clean1 = re.sub(r'\[.*?\]\s*', '', text1).strip().lower()
        clean2 = re.sub(r'\[.*?\]\s*', '', text2).strip().lower()
        
        if not clean1 or not clean2:
            return 0.0
        
        chars1 = set(clean1)
        chars2 = set(clean2)
        
        chars1 = {c for c in chars1 if c.strip() and c not in '，。！？,.!?；:：'}
        chars2 = {c for c in chars2 if c.strip() and c not in '，。！？,.!?；:：'}
        
        if not chars1 or not chars2:
            return 0.0
        
        intersection = len(chars1 & chars2)
        union = len(chars1 | chars2)
        
        return intersection / union if union > 0 else 0.0
    
    def _is_similar(self, text1: str, text2: str) -> bool:
        """检查两文本是否相似（字符级 Jaccard 相似度）。"""
        clean1 = re.sub(r'\[.*?\]\s*', '', text1).strip()
        clean2 = re.sub(r'\[.*?\]\s*', '', text2).strip()
        
        if not clean1 or not clean2:
            return False
        
        if clean1 in clean2 or clean2 in clean1:
            return True
        
        chars1 = set(clean1.lower())
        chars2 = set(clean2.lower())
        
        chars1 = {c for c in chars1 if c.strip() and c not in '，。！？,.!?；:：'}
        chars2 = {c for c in chars2 if c.strip() and c not in '，。！？,.!?；:：'}
        
        if not chars1 or not chars2:
            return False
        
        intersection = len(chars1 & chars2)
        union = len(chars1 | chars2)
        similarity = intersection / union if union > 0 else 0
        
        return similarity > 0.7  # 0.7 Jaccard: high enough to suppress paraphrases,
        # but low enough to keep factually distinct memories that share common words.


class ConflictResolverUpdater(BaseUpdater):
    """冲突感知更新器（占位符），检测并解决新信息与现有记忆的冲突，当前回退到 SimpleUpdater。"""
    
    def __init__(
        self,
        llm_client: Optional[any] = None,
        enable_versioning: bool = True
    ):
        self.llm_client = llm_client
        self.enable_versioning = enable_versioning
        logger.info(f"[ConflictResolverUpdater] 已初始化（占位符）- versioning={enable_versioning}")
    
    async def update(
        self,
        memory_cache: List[ContextItem],
        new_knowledge: List[Knowledge]
    ) -> List[ContextItem]:
        """带冲突检测的更新（当前为占位符，回退到 SimpleUpdater）。"""
        logger.debug("[ConflictResolverUpdater] 使用 SimpleUpdater 的回退方案（尚未实现）")
        
        fallback = SimpleUpdater()
        return await fallback.update(memory_cache, new_knowledge)


class AdaptiveEvictionUpdater(BaseUpdater):
    """自适应驱逐更新器（占位符），基于重要性智能移除低价值记忆，当前回退到 SimpleUpdater。"""
    
    def __init__(
        self,
        max_cache_size: int = 100,
        min_importance_threshold: float = 0.1
    ):
        self.max_cache_size = max_cache_size
        self.min_importance_threshold = min_importance_threshold
        logger.info(f"[AdaptiveEvictionUpdater] 已初始化（占位符）- max_size={max_cache_size}, min_importance={min_importance_threshold}")
    
    async def update(
        self,
        memory_cache: List[ContextItem],
        new_knowledge: List[Knowledge]
    ) -> List[ContextItem]:
        """带自适应驱逐的更新（当前为占位符，回退到 SimpleUpdater）。"""
        logger.debug("[AdaptiveEvictionUpdater] 使用 SimpleUpdater 的回退方案（尚未实现）")
        
        fallback = SimpleUpdater()
        updated_cache = await fallback.update(memory_cache, new_knowledge)
        
        return updated_cache
    
    def _evict_low_value_memories(self, cache: List[ContextItem]) -> List[ContextItem]:
        """驱逐低价值记忆以维持缓存大小（占位符）。"""
        if len(cache) > self.max_cache_size:
            return cache[-self.max_cache_size:]
        return cache
