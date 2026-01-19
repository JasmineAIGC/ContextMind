"""
ContextReorderer - 上下文重排序模块

职责：
- 重排序上下文
- 重要性评分
- 避免Lost-in-the-Middle问题

可插拔策略：
- PPR (Personalized PageRank)
- 重要性评分
- LongGenBench mitigation
- 相关性排序
"""

from typing import List, Optional
from ..data_models import ProcessedContext
from ..strategies.optimization import RerankingStrategy
from ..logger import get_logger

logger = get_logger(__name__)


class ContextReorderer:
    """
    上下文重排序器
    
    对上下文进行重排序以突出关键信息：
    - 按时间戳排序
    - 按来源优先级排序
    - 按相关性评分排序（预留）
    """
    
    def __init__(
        self,
        strategy: Optional[RerankingStrategy] = None,
    ):
        """
        初始化重排序器
        
        Args:
            strategy: 重排序策略（可插拔）
        """
        self.strategy = strategy or RerankingStrategy()
    
    async def reorder(
        self,
        context: ProcessedContext,
    ) -> ProcessedContext:
        """
        重排序上下文
        
        Args:
            context: 待重排序的上下文
            
        Returns:
            重排序后的上下文
        """
        # 委托给重排序策略
        reordered = await self.strategy.integrate(context)
        
        logger.debug(f"Reordered {len(reordered.items)} context items")
        
        return reordered
