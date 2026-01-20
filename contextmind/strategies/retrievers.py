"""
Memory Retrievers - Plugin implementations for memory retrieval

This module provides various strategies for retrieving relevant memories
based on the current query/context.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
import re

from ..models import ContextItem, ContextSource, RetrievalConfig, DEFAULT_MEMORY_CONFIG, get_logger

logger = get_logger(__name__)


class BaseRetriever(ABC):
    """
    Base interface for memory retrievers
    
    Retrievers find and rank relevant memories from the memory bank
    based on the current query or context.
    """
    
    @abstractmethod
    async def retrieve(
        self,
        query: str,
        memory_cache: List[ContextItem],
        limit: int = 5
    ) -> List[ContextItem]:
        """
        Retrieve relevant memories
        
        Args:
            query: Current query/context to match against
            memory_cache: Available memories to search
            limit: Maximum number of memories to return
            
        Returns:
            List of relevant context items, ranked by relevance
        """
        pass


class SemanticSearchRetriever(BaseRetriever):
    """
    Semantic search retriever (existing implementation)
    
    Uses character-level overlap and similarity metrics to find
    relevant memories. Supports recency weighting and deduplication.
    """
    
    def __init__(self, config: Optional[RetrievalConfig] = None):
        """
        Initialize semantic search retriever
        
        Args:
            config: Retrieval configuration, uses default if None
        """
        self.config = config or DEFAULT_MEMORY_CONFIG.retrieval
    
    async def retrieve(
        self,
        query: str,
        memory_cache: List[ContextItem],
        limit: int = 5
    ) -> List[ContextItem]:
        """
        Retrieve memories using semantic similarity
        
        Args:
            query: Query string
            memory_cache: Memory cache to search
            limit: Maximum results to return
            
        Returns:
            Ranked list of relevant memories
        """
        logger.info(f"[SemanticRetriever] 从缓存检索 - 查询: '{query[:50]}', 缓存大小: {len(memory_cache)}")
        
        if not memory_cache:
            logger.warning("[SemanticRetriever] 缓存为空 - 无法检索记忆")
            return []
        
        query_lower = query.lower()
        
        # Calculate relevance scores
        scored_items = []
        for item in memory_cache:
            content_lower = item.content.lower()
            
            # Method 1: Full match
            if query_lower in content_lower or content_lower in query_lower:
                score = 0.9
            # Method 2: Character overlap (better for Chinese)
            else:
                query_chars = set(query_lower)
                content_chars = set(content_lower)
                overlap = len(query_chars & content_chars)
                
                if overlap >= self.config.min_overlap_chars:
                    # Jaccard similarity
                    union = len(query_chars | content_chars)
                    similarity = overlap / union if union > 0 else 0
                    score = self.config.base_score + similarity * (0.9 - self.config.base_score)
                else:
                    score = self.config.base_score
            
            # Recency weighting
            if self.config.enable_recency_boost and item.timestamp:
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
                    logger.debug(f"Error calculating recency boost: {e}")
            
            scored_items.append((item, score))
        
        # Sort by score
        scored_items.sort(key=lambda x: x[1], reverse=True)
        
        # Relevance filtering
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
        
        # Deduplication
        if self.config.enable_deduplication:
            filtered_items = self._deduplicate_memories(filtered_items)
        
        # Limit results
        filtered_items = filtered_items[:min(limit, self.config.max_limit)]
        
        # Build result
        result = [
            ContextItem(
                content=item.content,
                source=item.source,
                score=score,
                timestamp=item.timestamp,
                metadata=item.metadata
            )
            for item, score in filtered_items
        ]
        
        if result:
            logger.info(f"[SemanticRetriever] ✓ 检索成功 - 找到 {len(result)} 条相关记忆 (最高分: {filtered_items[0][1]:.2f})")
            logger.debug(f"[SemanticRetriever] 检索结果详情:")
            for i, (item, score) in enumerate(filtered_items[:limit]):
                logger.debug(f"  {i+1}. [score={score:.2f}] {item.content[:80]}...")
        else:
            logger.warning(f"[SemanticRetriever] 未找到相关记忆 - 查询: '{query}'")
        
        return result
    
    def _deduplicate_memories(self, scored_items: List[tuple]) -> List[tuple]:
        """Remove highly similar memories"""
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
                    logger.debug(f"Skipping duplicate memory (similarity={similarity:.2f}): {item.content[:40]}...")
                    break
            
            if not is_duplicate:
                deduplicated.append((item, score))
                seen_contents.append(content)
        
        return deduplicated
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate Jaccard similarity between two texts"""
        chars1 = set(text1)
        chars2 = set(text2)
        
        if not chars1 or not chars2:
            return 0.0
        
        intersection = len(chars1 & chars2)
        union = len(chars1 | chars2)
        
        return intersection / union if union > 0 else 0.0


class HybridRetriever(BaseRetriever):
    """
    Hybrid retriever (placeholder for future implementation)
    
    Combines semantic search with keyword matching for improved
    retrieval accuracy. Supports type-based filtering.
    
    Future enhancements:
    - BM25 keyword scoring
    - Weighted combination of semantic + keyword
    - Memory type filtering
    - Query expansion
    """
    
    def __init__(
        self,
        config: Optional[RetrievalConfig] = None,
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3
    ):
        """
        Initialize hybrid retriever
        
        Args:
            config: Retrieval configuration
            semantic_weight: Weight for semantic similarity (0-1)
            keyword_weight: Weight for keyword matching (0-1)
        """
        self.config = config or DEFAULT_MEMORY_CONFIG.retrieval
        self.semantic_weight = semantic_weight
        self.keyword_weight = keyword_weight
        self._fallback = None  # Lazy initialization
        logger.info(f"[HybridRetriever] Initialized (placeholder) - semantic={semantic_weight}, keyword={keyword_weight}")
    
    async def retrieve(
        self,
        query: str,
        memory_cache: List[ContextItem],
        limit: int = 5
    ) -> List[ContextItem]:
        """
        Retrieve using hybrid semantic + keyword approach
        
        Current implementation is a placeholder that falls back to semantic search.
        
        Future TODO:
        - Implement BM25 keyword scoring
        - Combine semantic and keyword scores with weights
        - Add query expansion
        
        Args:
            query: Query string
            memory_cache: Memory cache
            limit: Maximum results
            
        Returns:
            Retrieved memories (currently uses fallback)
        """
        logger.debug("[HybridRetriever] Using fallback to SemanticSearchRetriever (not yet implemented)")
        return await self._get_fallback_retriever().retrieve(query, memory_cache, limit)
    
    def _get_fallback_retriever(self) -> SemanticSearchRetriever:
        """Get or create fallback retriever (lazy initialization)"""
        if self._fallback is None:
            self._fallback = SemanticSearchRetriever(self.config)
        return self._fallback


class LocatorRetriever(BaseRetriever):
    """
    Locator-based retriever (placeholder for future implementation)
    
    Uses precise location mechanisms to find memories based on
    contextual positioning and metadata. Particularly useful for
    long-context scenarios.
    
    Based on Locator mechanism research (2025 SOTA).
    
    Future enhancements:
    - Context-aware positioning
    - Metadata-based filtering
    - Multi-hop memory retrieval
    - Confidence boosting for frequently accessed memories
    """
    
    def __init__(
        self,
        config: Optional[RetrievalConfig] = None,
        use_metadata: bool = True
    ):
        """
        Initialize locator retriever
        
        Args:
            config: Retrieval configuration
            use_metadata: Whether to use metadata for locating
        """
        self.config = config or DEFAULT_MEMORY_CONFIG.retrieval
        self.use_metadata = use_metadata
        self._fallback = None  # Lazy initialization
        logger.info(f"[LocatorRetriever] Initialized (placeholder) - metadata={use_metadata}")
    
    async def retrieve(
        self,
        query: str,
        memory_cache: List[ContextItem],
        limit: int = 5
    ) -> List[ContextItem]:
        """
        Retrieve using locator mechanism
        
        Current implementation is a placeholder that falls back to semantic search.
        
        Future TODO:
        - Implement context-aware positioning
        - Add metadata-based filtering
        - Support multi-hop retrieval
        
        Args:
            query: Query string
            memory_cache: Memory cache
            limit: Maximum results
            
        Returns:
            Retrieved memories (currently uses fallback)
        """
        logger.debug("[LocatorRetriever] Using fallback to SemanticSearchRetriever (not yet implemented)")
        return await self._get_fallback_retriever().retrieve(query, memory_cache, limit)
    
    def _get_fallback_retriever(self) -> SemanticSearchRetriever:
        """Get or create fallback retriever (lazy initialization)"""
        if self._fallback is None:
            self._fallback = SemanticSearchRetriever(self.config)
        return self._fallback
