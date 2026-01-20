"""
Retrieval Strategies - 检索策略实现

提供多种检索策略，用于从长期记忆或知识库中检索相关信息。
"""

from typing import List, Optional
import re

from ..core import ContextItem, ContextSource
from .base import RetrievalStrategy
from ..utils import get_logger

logger = get_logger(__name__)


class KeywordRetrievalStrategy(RetrievalStrategy):
    """
    关键词检索策略
    
    基于关键词匹配进行检索，适用于简单场景。
    """
    
    def __init__(self, case_sensitive: bool = False):
        """
        初始化关键词检索策略
        
        Args:
            case_sensitive: 是否区分大小写
        """
        self.case_sensitive = case_sensitive
    
    async def retrieve(self, query: str, limit: int = 5, **kwargs) -> List[ContextItem]:
        """
        基于关键词检索
        
        注意：这是一个简化实现，实际使用时应该配合MemoryManager使用。
        这里只是展示策略接口的使用方式。
        """
        # 实际实现中，这里应该调用外部服务或数据库
        # 这里只是返回空列表作为示例
        logger.debug(f"KeywordRetrievalStrategy: query='{query}', limit={limit}")
        return []


class VectorRetrievalStrategy(RetrievalStrategy):
    """
    向量检索策略（预留接口）
    
    基于向量相似度进行检索，需要配合向量数据库和嵌入模型使用。
    """
    
    def __init__(
        self,
        embedding_model: Optional[any] = None,
        vector_db: Optional[any] = None,
        similarity_threshold: float = 0.7,
    ):
        """
        初始化向量检索策略
        
        Args:
            embedding_model: 嵌入模型实例
            vector_db: 向量数据库实例
            similarity_threshold: 相似度阈值
        """
        self.embedding_model = embedding_model
        self.vector_db = vector_db
        self.similarity_threshold = similarity_threshold
    
    async def retrieve(self, query: str, limit: int = 5, **kwargs) -> List[ContextItem]:
        """
        基于向量相似度检索
        
        注意：这是预留接口，当前返回空列表。
        实际使用时需要配合 foundation.VectorClient 和嵌入模型实现。
        
        实现指南：
        1. 使用 embedding_model 将 query 转换为向量
        2. 在 vector_db 中搜索相似向量
        3. 返回相似度高于阈值的结果
        
        示例代码参考 foundation/vector_client.py
        """
        if not self.embedding_model or not self.vector_db:
            logger.warning("VectorRetrievalStrategy: embedding_model or vector_db not configured")
            return []
        
        logger.debug(f"VectorRetrievalStrategy: query='{query}', limit={limit}")
        
        # 当embedding_model和vector_db配置后，在此实现向量检索逻辑
        # 参考实现已在 foundation.VectorClient 中提供
        
        return []


class HybridRetrievalStrategy(RetrievalStrategy):
    """
    混合检索策略
    
    结合关键词检索和向量检索的优点，提供更好的检索效果。
    """
    
    def __init__(
        self,
        keyword_weight: float = 0.5,
        vector_weight: float = 0.5,
        keyword_strategy: Optional[RetrievalStrategy] = None,
        vector_strategy: Optional[RetrievalStrategy] = None,
    ):
        """
        初始化混合检索策略
        
        Args:
            keyword_weight: 关键词检索的权重
            vector_weight: 向量检索的权重
            keyword_strategy: 关键词检索策略实例
            vector_strategy: 向量检索策略实例
        """
        self.keyword_weight = keyword_weight
        self.vector_weight = vector_weight
        self.keyword_strategy = keyword_strategy or KeywordRetrievalStrategy()
        self.vector_strategy = vector_strategy or VectorRetrievalStrategy()
    
    async def retrieve(self, query: str, limit: int = 5, **kwargs) -> List[ContextItem]:
        """
        混合检索
        
        同时使用关键词和向量检索，并根据权重合并结果。
        """
        logger.debug(f"HybridRetrievalStrategy: query='{query}', limit={limit}")
        
        # 并发执行两种检索
        keyword_results = await self.keyword_strategy.retrieve(query, limit=limit * 2)
        vector_results = await self.vector_strategy.retrieve(query, limit=limit * 2)
        
        # 合并结果并调整分数
        merged_results = {}
        
        for item in keyword_results:
            key = item.content
            merged_results[key] = ContextItem(
                content=item.content,
                source=item.source,
                score=item.score * self.keyword_weight,
                timestamp=item.timestamp,
                metadata={**item.metadata, 'retrieval_method': 'keyword'}
            )
        
        for item in vector_results:
            key = item.content
            if key in merged_results:
                # 如果已存在，合并分数
                merged_results[key].score += item.score * self.vector_weight
                merged_results[key].metadata['retrieval_method'] = 'hybrid'
            else:
                merged_results[key] = ContextItem(
                    content=item.content,
                    source=item.source,
                    score=item.score * self.vector_weight,
                    timestamp=item.timestamp,
                    metadata={**item.metadata, 'retrieval_method': 'vector'}
                )
        
        # 排序并返回前N个结果
        sorted_results = sorted(
            merged_results.values(),
            key=lambda x: x.score,
            reverse=True
        )
        
        return sorted_results[:limit]
