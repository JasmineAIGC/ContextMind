"""
默认策略实现

提供简单的默认实现用于策略以维持向后兼容性。
"""

from typing import List
from ..models import ProcessedContext, ContextResult, get_logger
from .base import OptimizationStrategy

logger = get_logger(__name__)


class CompressionStrategy(OptimizationStrategy):
    """
    默认压缩策略
    
    简单的滑动窗口策略，保留最近的N个条目。
    """
    
    def __init__(self, max_items: int = 10):
        """
        初始化压缩策略
        
        Args:
            max_items: 最大保留条目数
        """
        self.max_items = max_items
    
    async def optimize(self, context: ProcessedContext) -> ContextResult:
        """
        压缩上下文
        
        保留最近的max_items个条目。
        
        Args:
            context: 待压缩的上下文
            
        Returns:
            压缩后的上下文结果
        """
        # 简单滑动窗口策略：保留最近的条目
        if len(context.items) > self.max_items:
            logger.debug(f"[CompressionStrategy] 压缩前: {len(context.items)} 项")
            context.items = context.items[-self.max_items:]
            logger.debug(f"[CompressionStrategy] 压缩后: {len(context.items)} 项")
        
        # 转换为ContextResult
        return context.to_context_result()


class RerankingStrategy(OptimizationStrategy):
    """
    默认重排序策略
    
    按时间戳和来源重新排序上下文条目。
    """
    
    async def optimize(self, context: ProcessedContext) -> ProcessedContext:
        """
        重排序上下文
        
        Args:
            context: 待重排序的上下文
            
        Returns:
            重排序后的上下文
        """
        # 简单实现：按时间戳排序（保持原有顺序）
        # 更复杂的实现可以按相关性、重要性等进行排序
        logger.debug(f"[RerankingStrategy] 重排序 {len(context.items)} 项")
        
        # 这里可以添加更复杂的排序逻辑
        # 目前保持原有顺序
        return context
