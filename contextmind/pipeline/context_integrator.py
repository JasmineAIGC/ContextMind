"""
ContextIntegrator - 上下文整合器

整合收集到的上下文信息，包括去重、排序和组织。
此组件委托给 IntegrationStrategy 来执行实际整合逻辑。
"""

from typing import Optional

from ..data_models import ProcessedContext
from ..strategies import IntegrationStrategy, SimpleIntegrationStrategy
from ..logger import get_logger

logger = get_logger(__name__)


class ContextIntegrator:
    """
    上下文整合器
    
    对收集到的上下文进行整合处理，委托给可插拔的整合策略。
    默认使用 SimpleIntegrationStrategy。
    """
    
    def __init__(
        self, 
        deduplicate: bool = True,
        strategy: Optional[IntegrationStrategy] = None
    ):
        """
        初始化上下文整合器
        
        Args:
            deduplicate: 是否去重，默认为True
            strategy: 自定义整合策略，默认使用 SimpleIntegrationStrategy
        """
        self.strategy = strategy or SimpleIntegrationStrategy(deduplicate=deduplicate)
    
    async def integrate(self, context: ProcessedContext) -> ProcessedContext:
        """
        整合上下文
        
        Args:
            context: 待整合的上下文对象
            
        Returns:
            整合后的上下文对象
        """
        # 委托给策略执行整合
        result = await self.strategy.integrate(context)
        
        # 添加整合元数据
        result.metadata['integrated'] = True
        result.metadata['unique_items'] = len(result.items)
        
        logger.debug(f"Integrated {len(result.items)} context items")
        
        return result
