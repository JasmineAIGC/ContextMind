"""
ContextReorderer - Step 4 of Pipeline Architecture

Context reordering and prioritization.
"""

from typing import Optional

from .models import ProcessedContext, get_logger
from .strategies import RerankingStrategy

logger = get_logger(__name__)


class ContextReorderer:
    """
    上下文重排序器
    
    对上下文进行重排序以突出关键信息:
    - 按时间戳排序
    - 按来源优先级排序
    - 按相关性评分排序 (预留)
    """
    
    def __init__(
        self,
        strategy: Optional[RerankingStrategy] = None,
    ):
        """
        初始化重排序器
        
        Args:
            strategy: 重排序策略 (可插拔)
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
        reordered = await self.strategy.optimize(context)
        
        logger.debug(f"重排序 {len(reordered.items)} 个上下文项")
        
        return reordered
