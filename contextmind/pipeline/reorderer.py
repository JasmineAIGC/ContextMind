"""
ContextReorderer - 管道架构步骤4

上下文重排序和优先级处理。
"""

from typing import Optional

from ..core.data_models import ProcessedContext
from ..utils.logger import get_logger
from ..core.strategies import RerankingStrategy

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
