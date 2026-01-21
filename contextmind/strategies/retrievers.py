"""
Memory Retrievers - 内存检索的插件实现

该模块提供各种策略用于根据当前查询/Context 检索相关记忆。
"""

from abc import ABC, abstractmethod
from typing import List, Optional
import re

from ..models import ContextItem, ContextSource, RetrievalConfig, DEFAULT_MEMORY_CONFIG, get_logger

logger = get_logger(__name__)


class BaseRetriever(ABC):
    """
    Memory Retriever 的基类接口
    
    Retriever 从 Memory Bank 中查找和排序相关记忆，
    基于当前查询或 Context。
    """
    
    @abstractmethod
    async def retrieve(
        self,
        query: str,
        memory_cache: List[ContextItem],
        limit: int = 5
    ) -> List[ContextItem]:
        """
        检索相关记忆
        
        Args:
            query: 待匹配的当前查询/Context
            memory_cache: 可用的记忆库进行搜索
            limit: 返回记忆的最大数量
            
        Returns:
            按相关性排序的相关 Context Item 列表
        """
        pass


class SemanticSearchRetriever(BaseRetriever):
    """
    Semantic Search Retriever（现有实现）
    
    使用字符级别的重叠度和相似性指标来查找相关记忆。
    支持新近性加权和去重。
    """
    
    def __init__(self, config: Optional[RetrievalConfig] = None):
        """
        初始化 Semantic Search Retriever
        
        Args:
            config: Retrieval 配置，若为 None 则使用默认配置
        """
        self.config = config or DEFAULT_MEMORY_CONFIG.retrieval
    
    async def retrieve(
        self,
        query: str,
        memory_cache: List[ContextItem],
        limit: int = 5
    ) -> List[ContextItem]:
        """
        使用 Semantic Similarity 检索记忆
        
        Args:
            query: 查询字符串
            memory_cache: 待搜索的 Memory Cache
            limit: 返回结果的最大数量
            
        Returns:
            按相关性排序的记忆列表
        """
        logger.info(f"[SemanticRetriever] 从缓存检索 - 查询: '{query[:50]}', 缓存大小: {len(memory_cache)}")
        
        if not memory_cache:
            logger.warning("[SemanticRetriever] 缓存为空 - 无法检索记忆")
            return []
        
        query_lower = query.lower()
        
        # 计算相关性分数
        scored_items = []
        for item in memory_cache:
            content_lower = item.content.lower()
            
            # 方法 1: 完全匹配
            if query_lower in content_lower or content_lower in query_lower:
                score = 0.9
            # 方法 2: 字符重叠（适合中文）
            else:
                query_chars = set(query_lower)
                content_chars = set(content_lower)
                overlap = len(query_chars & content_chars)
                
                if overlap >= self.config.min_overlap_chars:
                    # Jaccard Similarity（Jaccard 相似度）
                    union = len(query_chars | content_chars)
                    similarity = overlap / union if union > 0 else 0
                    score = self.config.base_score + similarity * (0.9 - self.config.base_score)
                else:
                    score = self.config.base_score
            
            # 新近性加权
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
                    logger.debug(f"计算新近性加权时出错: {e}")
            
            scored_items.append((item, score))
        
        # 按分数排序
        scored_items.sort(key=lambda x: x[1], reverse=True)
        
        # 相关性过滤
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
        
        # 去重
        if self.config.enable_deduplication:
            filtered_items = self._deduplicate_memories(filtered_items)
        
        # 限制结果数量
        filtered_items = filtered_items[:min(limit, self.config.max_limit)]
        
        # 构建结果
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
        """移除高度相似的记忆"""
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
        """计算两个文本之间的 Jaccard Similarity"""
        chars1 = set(text1)
        chars2 = set(text2)
        
        if not chars1 or not chars2:
            return 0.0
        
        intersection = len(chars1 & chars2)
        union = len(chars1 | chars2)
        
        return intersection / union if union > 0 else 0.0


class HybridRetriever(BaseRetriever):
    """
    混合 Retriever（未来实现的占位符）
    
    结合 Semantic Search 和关键词匹配以提高检索精度。
    支持基于类型的过滤。
    
    未来增强功能：
    - BM25 关键词评分
    - Semantic 和关键词的加权组合
    - Memory 类型过滤
    - Query 扩展
    """
    
    def __init__(
        self,
        config: Optional[RetrievalConfig] = None,
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3
    ):
        """
        初始化混合 Retriever
        
        Args:
            config: Retrieval 配置
            semantic_weight: Semantic Similarity 的权重（0-1）
            keyword_weight: 关键词匹配的权重（0-1）
        """
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
        """
        使用混合 Semantic + 关键词方法进行检索
        
        当前实现是一个占位符，会回退到 Semantic Search。
        
        未来待做事项：
        - 实现 BM25 关键词评分
        - 使用权重组合 Semantic 和关键词分数
        - 添加 Query 扩展
        
        Args:
            query: 查询字符串
            memory_cache: Memory Cache
            limit: 最大结果数
            
        Returns:
            检索到的记忆（目前使用回退方案）
        """
        logger.debug("[HybridRetriever] 使用 SemanticSearchRetriever 的回退方案（尚未实现）")
        return await self._get_fallback_retriever().retrieve(query, memory_cache, limit)
    
    def _get_fallback_retriever(self) -> SemanticSearchRetriever:
        """获取或创建回退 Retriever（延迟初始化）"""
        if self._fallback is None:
            self._fallback = SemanticSearchRetriever(self.config)
        return self._fallback


class LocatorRetriever(BaseRetriever):
    """
    基于 Locator 的 Retriever（未来实现的占位符）
    
    使用精确位置机制基于 Context 位置和元数据查找记忆。
    特别适用于长 Context 场景。
    
    基于 Locator 机制研究（2025 SOTA）。
    
    未来增强功能：
    - Context 感知定位
    - 基于元数据的过滤
    - 多跳 Memory 检索
    - 为频繁访问的记忆提升置信度
    """
    
    def __init__(
        self,
        config: Optional[RetrievalConfig] = None,
        use_metadata: bool = True
    ):
        """
        初始化 Locator Retriever
        
        Args:
            config: Retrieval 配置
            use_metadata: 是否使用元数据进行定位
        """
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
        """
        使用 Locator 机制进行检索
        
        当前实现是一个占位符，会回退到 Semantic Search。
        
        未来待做事项：
        - 实现 Context 感知定位
        - 添加基于元数据的过滤
        - 支持多跳检索
        
        Args:
            query: 查询字符串
            memory_cache: Memory Cache
            limit: 最大结果数
            
        Returns:
            检索到的记忆（目前使用回退方案）
        """
        logger.debug("[LocatorRetriever] 使用 SemanticSearchRetriever 的回退方案（尚未实现）")
        return await self._get_fallback_retriever().retrieve(query, memory_cache, limit)
    
    def _get_fallback_retriever(self) -> SemanticSearchRetriever:
        """获取或创建回退 Retriever（延迟初始化）"""
        if self._fallback is None:
            self._fallback = SemanticSearchRetriever(self.config)
        return self._fallback
