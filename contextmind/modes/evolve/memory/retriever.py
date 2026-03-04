"""
记忆检索器 - 内存检索的插件实现

该模块提供各种策略用于根据当前查询/上下文检索相关记忆。
"""

from typing import List, Optional
import re

from ..core.data_models import ContextItem
from ..core.config import ContextSource
from ..core.config import RetrievalConfig, DEFAULT_MEMORY_CONFIG
from contextmind.infra.logger import get_logger
from ..core.strategies import RetrievalStrategy as BaseRetriever  # 使用核心基类
from contextmind.infra.embedding import get_embedding_client, calculate_embedding_similarity

logger = get_logger(__name__)


class SemanticSearchRetriever(BaseRetriever):
    """语义搜索检索器。

    Two-tier retrieval strategy:
    1. If embeddings are available for both query and stored memories, cosine
       similarity is used for dense semantic matching.
    2. Otherwise falls back to character-level Jaccard similarity, which is
       fast and language-agnostic but purely lexical.
    Recency boost is applied on top to surface recent memories.
    """
    
    def __init__(self, config: Optional[RetrievalConfig] = None):
        self.config = config or DEFAULT_MEMORY_CONFIG.retrieval
    
    async def retrieve(
        self,
        query: str,
        memory_cache: List[ContextItem],
        limit: int = 5
    ) -> List[ContextItem]:
        """
        使用嵌入向量 + 语义相似度检索记忆，不可用时回退到字符级相似度。

        Args:
            query: 查询字符串
            memory_cache: 待搜索的记忆缓存
            limit: 返回结果的最大数量

        Returns:
            按相关性排序的记忆列表
        """
        logger.info(f"[SemanticRetriever] 从缓存检索 - 查询: '{query[:50]}', 缓存大小: {len(memory_cache)}")
        
        if not memory_cache:
            logger.warning("[SemanticRetriever] 缓存为空 - 无法检索记忆")
            return []
        
        embedding_client = get_embedding_client()
        query_embedding = None
        if embedding_client:
            query_embedding = embedding_client.generate_embedding(query)
        
        use_embedding = query_embedding is not None
        if use_embedding:
            # 检查缓存中有多少项有嵌入向量
            items_with_embedding = sum(1 for item in memory_cache if item.embeddings)
            logger.debug(f"[SemanticRetriever] 缓存中有嵌入向量的项: {items_with_embedding}/{len(memory_cache)}")
            if items_with_embedding == 0:
                use_embedding = False
        
        logger.debug(f"[SemanticRetriever] 使用嵌入向量检索: {use_embedding}")
        
        query_lower = query.lower()
        
        scored_items = []
        for item in memory_cache:
            content_lower = item.content.lower()
            
            if use_embedding and item.embeddings:
                item_embedding = item.embeddings.get('default')
                if item_embedding:
                    similarity, success = calculate_embedding_similarity(query_embedding, item_embedding)
                    if success:
                        score = similarity
                    else:
                        score = self._calculate_char_similarity(query_lower, content_lower)
                else:
                    score = self._calculate_char_similarity(query_lower, content_lower)
            else:
                score = self._calculate_char_similarity(query_lower, content_lower)
                
            
            if self.config.enable_recency_boost and hasattr(item, 'timestamp') and item.timestamp:
                try:
                    from datetime import datetime
                    if isinstance(item.timestamp, datetime):
                        days_ago = (datetime.now() - item.timestamp).days
                        if days_ago <= self.config.recency_days_threshold:
                            # 线性衰减：记忆越新提升越多，到达阈值边界时提升归零。
                            recency_boost = self.config.recency_weight * (
                                1 - days_ago / self.config.recency_days_threshold
                            )
                            score = min(1.0, score + recency_boost)
                except Exception as e:
                    logger.debug(f"计算新近性加权时出错: {e}")
            
            
            scored_items.append((item, score))
        
        scored_items.sort(key=lambda x: x[1], reverse=True)
        
        if self.config.relevance_threshold > 0:
            filtered_items = [
                (item, score) for item, score in scored_items
                if score >= self.config.relevance_threshold
            ]
            
            if not filtered_items and scored_items:
                logger.debug(f"No memories above threshold {self.config.relevance_threshold}, using top items")
                filtered_items = scored_items[:limit]
        else:
            filtered_items = scored_items
        
        if self.config.enable_deduplication:
            deduplicated = []
            seen_contents = set()
            for item, score in filtered_items:
                content_key = item.content[:50].lower()
                if content_key not in seen_contents:
                    deduplicated.append((item, score))
                    seen_contents.add(content_key)
            filtered_items = deduplicated
        
        result = [item for item, score in filtered_items[:limit]]
        
        if result:
            logger.info(f"[SemanticRetriever] ✓ 检索成功 - 找到 {len(result)} 条相关记忆 (最高分: {filtered_items[0][1]:.2f})")
            for idx, (item, score) in enumerate(filtered_items[:limit], 1):
                logger.debug(f"[SemanticRetriever]   [{idx}] 分数={score:.3f}: {item.content[:60]}...")
        else:
            logger.info("[SemanticRetriever] ✗ 未找到相关记忆")
        
        return result
    
    def _calculate_char_similarity(self, query_lower: str, content_lower: str) -> float:
        """Character-level Jaccard similarity, used when embeddings are unavailable.

        Substring containment is scored at 0.9 so an embedding-based score can
        still outrank it. For partial overlaps, Jaccard over character sets is
        linearly scaled into [base_score, 0.9] to preserve relative ordering.
        """
        # 直接子串包含是强相关证据；评分为 0.9 而非 1.0，为向量检索保留超越空间。
        if query_lower in content_lower or content_lower in query_lower:
            return 0.9
        
        query_chars = set(query_lower)
        content_chars = set(content_lower)
        overlap = len(query_chars & content_chars)
        
        if overlap >= self.config.min_overlap_chars:
            union = len(query_chars | content_chars)
            similarity = overlap / union if union > 0 else 0
            # 将 Jaccard 相似度 [0, 1] 线性映射到 [base_score, 0.9]，
            # 在保持排序的同时将相似度范围映射到允许的输出区间。
            score = self.config.base_score + similarity * (0.9 - self.config.base_score)
        else:
            score = self.config.base_score
        
        return score
