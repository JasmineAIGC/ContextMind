"""
Memory Updaters - Plugin implementations for memory updates

This module provides various strategies for updating and maintaining
the memory bank (add, update, delete operations).
"""

from abc import ABC, abstractmethod
from typing import List, Optional
import re
from datetime import datetime

from ..models import ContextItem, ContextSource, Knowledge, KnowledgeType, get_logger

logger = get_logger(__name__)


class BaseUpdater(ABC):
    """
    Base interface for memory updaters
    
    Updaters handle the Add, Update, and Delete operations
    for maintaining the memory bank.
    """
    
    @abstractmethod
    async def update(
        self,
        memory_cache: List[ContextItem],
        new_knowledge: List[Knowledge]
    ) -> List[ContextItem]:
        """
        Update memory cache with new knowledge
        
        Handles:
        - Add: Insert new memories
        - Update: Merge or replace existing memories
        - Delete: Remove outdated or low-value memories
        
        Args:
            memory_cache: Current memory cache
            new_knowledge: New knowledge to integrate
            
        Returns:
            Updated memory cache
        """
        pass


class SimpleUpdater(BaseUpdater):
    """
    Simple memory updater (existing implementation)
    
    Basic add/update/dedup logic with configurable thresholds.
    Filters by confidence, deduplicates, and limits cache size.
    """
    
    # Storage thresholds (from existing code)
    STORAGE_THRESHOLD_PREFERENCE = 0.75
    STORAGE_THRESHOLD_FACT = 0.70
    STORAGE_THRESHOLD_EVENT = 0.70
    STORAGE_MIN_LENGTH = 3
    
    async def update(
        self,
        memory_cache: List[ContextItem],
        new_knowledge: List[Knowledge]
    ) -> List[ContextItem]:
        """
        Simple update strategy
        
        1. Filter low-quality knowledge
        2. Deduplicate against existing cache
        3. Add new items to cache
        
        Args:
            memory_cache: Current cache
            new_knowledge: New knowledge
            
        Returns:
            Updated cache
        """
        if not new_knowledge:
            logger.debug("[SimpleUpdater] 没有知识需要存储")
            return memory_cache
        
        logger.info(f"[SimpleUpdater] 开始存储知识 - 收到 {len(new_knowledge)} 条知识项")
        
        # Filter by confidence thresholds
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
                logger.debug(f"[SimpleUpdater] 过滤低质量知识: [{k.type.value}] {k.content[:50]}... (置信度={k.confidence:.2f})")
        
        if len(filtered_knowledge) < len(new_knowledge):
            logger.info(f"[SimpleUpdater] 质量过滤: {len(new_knowledge)} → {len(filtered_knowledge)} 条知识")
        
        # Deduplicate against existing cache
        new_items = []
        for k in filtered_knowledge:
            formatted_content = f"[{k.type.value.upper()}] {k.content}"
            
            # Check for duplicates
            is_duplicate = False
            for existing in memory_cache:
                if self._is_similar(formatted_content, existing.content):
                    logger.debug(f"[SimpleUpdater] 跳过重复知识: {formatted_content[:50]}...")
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                new_items.append(ContextItem(
                    content=formatted_content,
                    source=ContextSource.MEMORY,
                    score=k.confidence,
                    metadata=k.metadata
                ))
                logger.debug(f"[SimpleUpdater] 已存储: {formatted_content[:80]}...")
        
        if not new_items:
            logger.info("[SimpleUpdater] 所有知识项均为重复或低质量，未存储新内容")
            return memory_cache
        
        # Add to cache
        updated_cache = list(memory_cache) + new_items
        
        logger.info(f"[SimpleUpdater] ✓ 存储完成 - 新增 {len(new_items)} 条知识")
        logger.info(f"[SimpleUpdater] 当前记忆库总计: {len(updated_cache)} 条记忆")
        
        return updated_cache
    
    def _is_similar(self, text1: str, text2: str) -> bool:
        """Check if two texts are similar (supports Chinese)"""
        # Remove type tags for comparison
        clean1 = re.sub(r'\[.*?\]\s*', '', text1).strip()
        clean2 = re.sub(r'\[.*?\]\s*', '', text2).strip()
        
        if not clean1 or not clean2:
            return False
        
        # Substring match
        if clean1 in clean2 or clean2 in clean1:
            return True
        
        # Character-level Jaccard similarity for Chinese
        chars1 = set(clean1.lower())
        chars2 = set(clean2.lower())
        
        # Remove whitespace and punctuation
        chars1 = {c for c in chars1 if c.strip() and c not in '，。！？,.!?；:：'}
        chars2 = {c for c in chars2 if c.strip() and c not in '，。！？,.!?；:：'}
        
        if not chars1 or not chars2:
            return False
        
        # Jaccard similarity
        intersection = len(chars1 & chars2)
        union = len(chars1 | chars2)
        similarity = intersection / union if union > 0 else 0
        
        # 70% similarity threshold
        return similarity > 0.7


class ConflictResolverUpdater(BaseUpdater):
    """
    Conflict-aware updater (placeholder for future implementation)
    
    Detects and resolves conflicts when new information contradicts
    existing memories. Supports versioning and merge strategies.
    
    Future enhancements:
    - LLM-based conflict detection
    - Automatic contradiction resolution
    - Version history tracking
    - User preference for conflict handling
    """
    
    def __init__(
        self,
        llm_client: Optional[any] = None,
        enable_versioning: bool = True
    ):
        """
        Initialize conflict resolver
        
        Args:
            llm_client: LLM for conflict reasoning (optional)
            enable_versioning: Track version history
        """
        self.llm_client = llm_client
        self.enable_versioning = enable_versioning
        logger.info(f"[ConflictResolverUpdater] Initialized (placeholder) - versioning={enable_versioning}")
    
    async def update(
        self,
        memory_cache: List[ContextItem],
        new_knowledge: List[Knowledge]
    ) -> List[ContextItem]:
        """
        Update with conflict detection
        
        Current implementation is a placeholder that falls back to simple update.
        
        Future TODO:
        - Detect contradicting memories
        - Resolve conflicts (merge, replace, version)
        - Track update history
        
        Args:
            memory_cache: Current cache
            new_knowledge: New knowledge
            
        Returns:
            Updated cache (currently uses fallback)
        """
        logger.debug("[ConflictResolverUpdater] Using fallback to SimpleUpdater (not yet implemented)")
        
        # Fallback to simple update for now
        fallback = SimpleUpdater()
        return await fallback.update(memory_cache, new_knowledge)


class AdaptiveEvictionUpdater(BaseUpdater):
    """
    Adaptive eviction updater (placeholder for future implementation)
    
    Intelligently removes low-value memories based on importance,
    access patterns, and capacity constraints. Prevents cache bloat.
    
    Future enhancements:
    - Importance-based eviction (LRU + score)
    - Adaptive capacity limits
    - Predictive eviction
    - Access pattern analysis
    """
    
    def __init__(
        self,
        max_cache_size: int = 100,
        min_importance_threshold: float = 0.1
    ):
        """
        Initialize adaptive eviction updater
        
        Args:
            max_cache_size: Maximum number of cached memories
            min_importance_threshold: Minimum importance to keep
        """
        self.max_cache_size = max_cache_size
        self.min_importance_threshold = min_importance_threshold
        logger.info(f"[AdaptiveEvictionUpdater] Initialized (placeholder) - max_size={max_cache_size}, min_importance={min_importance_threshold}")
    
    async def update(
        self,
        memory_cache: List[ContextItem],
        new_knowledge: List[Knowledge]
    ) -> List[ContextItem]:
        """
        Update with adaptive eviction
        
        Current implementation is a placeholder that falls back to simple update.
        
        Future TODO:
        - Implement importance scoring
        - Evict low-value memories when cache is full
        - Consider access frequency and recency
        
        Args:
            memory_cache: Current cache
            new_knowledge: New knowledge
            
        Returns:
            Updated cache (currently uses fallback)
        """
        logger.debug("[AdaptiveEvictionUpdater] Using fallback to SimpleUpdater (not yet implemented)")
        
        # Fallback to simple update for now
        fallback = SimpleUpdater()
        updated_cache = await fallback.update(memory_cache, new_knowledge)
        
        # Future: Add eviction logic when cache exceeds max_cache_size
        # This would involve:
        # 1. Calculating importance scores for all cached items
        # 2. Sorting by importance (combining recency, access frequency, and score)
        # 3. Evicting lowest-importance items to reach target size
        # Example implementation (when importance scoring is ready):
        #   if len(updated_cache) > self.max_cache_size:
        #       updated_cache = self._evict_low_value_memories(updated_cache)
        
        return updated_cache
    
    def _evict_low_value_memories(self, cache: List[ContextItem]) -> List[ContextItem]:
        """
        Evict low-value memories to maintain cache size (placeholder)
        
        This method would intelligently remove memories with low importance
        scores while preserving high-value and recent items.
        
        Args:
            cache: Current memory cache
            
        Returns:
            Cache after eviction
        """
        # TODO: Implement when importance scoring is available
        # Current implementation just truncates to max_cache_size
        if len(cache) > self.max_cache_size:
            # Keep most recent items (simple strategy)
            return cache[-self.max_cache_size:]
        return cache
