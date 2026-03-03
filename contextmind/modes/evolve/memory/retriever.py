"""
记忆检索器 - 内存检索的插件实现

该模块提供各种策略用于根据当前查询/上下文检索相关记忆。
"""

from typing import List, Optional
import re

from ..core.data_models import ContextItem
from ..core.types import ContextSource
from ..core.configs import RetrievalConfig, DEFAULT_MEMORY_CONFIG
from contextmind.infra.logger import get_logger
from ..core.strategies import RetrievalStrategy as BaseRetriever  # Use core base class
from contextmind.infra.embedding import get_embedding_client, calculate_embedding_similarity

logger = get_logger(__name__)


class SemanticSearchRetriever(BaseRetriever):
    """语义搜索检索器，使用字符重叠和嵌入向量相似度检索相关记忆。"""
    
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
        logger.debug(f"[SemanticRetriever] === 开始记忆检索 ===")
        logger.debug(f"[SemanticRetriever] 查询: '{query}'")
        logger.debug(f"[SemanticRetriever] 缓存大小: {len(memory_cache)} 条记忆")
        logger.debug(f"[SemanticRetriever] Limit: {limit}")
        
        logger.info(f"[SemanticRetriever] 从缓存检索 - 查询: '{query[:50]}', 缓存大小: {len(memory_cache)}")
        
        if not memory_cache:
            logger.warning("[SemanticRetriever] 缓存为空 - 无法检索记忆")
            logger.debug(f"[SemanticRetriever] 输出: 0 条记忆")
            logger.debug(f"[SemanticRetriever] === 记忆检索完成 ===")
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
            logger.debug(f"[SemanticRetriever] 输出: {len(result)} 条记忆")
            for idx, (item, score) in enumerate(filtered_items[:limit], 1):
                logger.debug(f"[SemanticRetriever]   [{idx}] 分数={score:.3f}: {item.content[:60]}...")
        else:
            logger.info("[SemanticRetriever] ✗ 未找到相关记忆")
            logger.debug(f"[SemanticRetriever] 输出: 0 条记忆")
        
        logger.debug(f"[SemanticRetriever] === 记忆检索完成 ===")
        
        return result
    
    def _calculate_char_similarity(self, query_lower: str, content_lower: str) -> float:
        """计算字符级 Jaccard 相似度（嵌入向量不可用时的回退方案）"""
        if query_lower in content_lower or content_lower in query_lower:
            return 0.9
        
        query_chars = set(query_lower)
        content_chars = set(content_lower)
        overlap = len(query_chars & content_chars)
        
        if overlap >= self.config.min_overlap_chars:
            union = len(query_chars | content_chars)
            similarity = overlap / union if union > 0 else 0
            score = self.config.base_score + similarity * (0.9 - self.config.base_score)
        else:
            score = self.config.base_score
        
        return score
    
    def _deduplicate_memories(self, scored_items: List[tuple]) -> List[tuple]:
        if not scored_items:
            return []
        
        deduplicated = []
        seen_contents = []
        
        for item, score in scored_items:
            content = item.content.lower()
            
            is_duplicate = False
            for seen in seen_contents:
                similarity = self._calculate_similarity(content, seen)
                if similarity >= self.config.similarity_threshold_for_dedup:
                    is_duplicate = True
                    logger.debug(f"跳过重复的记忆（相似度={similarity:.2f}）: {item.content[:40]}...")
                    break
            
            if not is_duplicate:
                deduplicated.append((item, score))
                seen_contents.append(content)
        
        return deduplicated
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        chars1 = set(text1)
        chars2 = set(text2)
        
        if not chars1 or not chars2:
            return 0.0
        
        intersection = len(chars1 & chars2)
        union = len(chars1 | chars2)
        
        return intersection / union if union > 0 else 0.0


class HybridRetriever(BaseRetriever):
    """混合检索器（占位符），结合语义搜索和关键词匹配，当前回退到 SemanticSearchRetriever。"""
    
    def __init__(
        self,
        config: Optional[RetrievalConfig] = None,
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3
    ):
        self.config = config or DEFAULT_MEMORY_CONFIG.retrieval
        self.semantic_weight = semantic_weight
        self.keyword_weight = keyword_weight
        self._fallback = None  # 延迟初始化
        logger.info(f"[HybridRetriever] 已初始化（占位符）- semantic={semantic_weight}, keyword={keyword_weight}")
    
    async def retrieve(
        self,
        query: str,
        memory_cache: List[ContextItem],
        limit: int = 5
    ) -> List[ContextItem]:
        """使用混合语义 + 关键词方法检索（当前为占位符，回退到语义搜索）。"""
        logger.debug("[HybridRetriever] 使用 SemanticSearchRetriever 的回退方案（尚未实现）")
        return await self._get_fallback_retriever().retrieve(query, memory_cache, limit)
    
    def _get_fallback_retriever(self) -> SemanticSearchRetriever:
        if self._fallback is None:
            self._fallback = SemanticSearchRetriever(self.config)
        return self._fallback


class LocatorRetriever(BaseRetriever):
    """定位器检索器（占位符），基于上下文位置检索记忆，当前回退到 SemanticSearchRetriever。"""
    
    def __init__(
        self,
        config: Optional[RetrievalConfig] = None,
        use_metadata: bool = True
    ):
        self.config = config or DEFAULT_MEMORY_CONFIG.retrieval
        self.use_metadata = use_metadata
        self._fallback = None  # 延迟初始化
        logger.info(f"[LocatorRetriever] 已初始化（占位符）- metadata={use_metadata}")
    
    async def retrieve(
        self,
        query: str,
        memory_cache: List[ContextItem],
        limit: int = 5
    ) -> List[ContextItem]:
        """使用定位器机制检索记忆（当前为占位符，回退到语义搜索）。"""
        logger.debug("[LocatorRetriever] 使用 SemanticSearchRetriever 的回退方案（尚未实现）")
        return await self._get_fallback_retriever().retrieve(query, memory_cache, limit)
    
    def _get_fallback_retriever(self) -> SemanticSearchRetriever:
        if self._fallback is None:
            self._fallback = SemanticSearchRetriever(self.config)
        return self._fallback
