"""
Integration Strategies - 整合策略实现

提供多种整合策略，用于整合来自不同来源的上下文信息。
"""

from typing import Dict, List
from datetime import datetime

from ..data_models import ProcessedContext, ContextItem, ContextSource
from .base import IntegrationStrategy
from ..logger import get_logger

logger = get_logger(__name__)


class SimpleIntegrationStrategy(IntegrationStrategy):
    """
    简单整合策略
    
    基本的整合逻辑：去重、排序。
    """
    
    def __init__(self, deduplicate: bool = True):
        """
        初始化简单整合策略
        
        Args:
            deduplicate: 是否去重
        """
        self.deduplicate = deduplicate
    
    async def integrate(self, context: ProcessedContext) -> ProcessedContext:
        """
        整合上下文
        
        执行去重和排序操作。
        """
        items = context.items
        
        # 去重
        if self.deduplicate:
            seen = set()
            unique_items = []
            for item in items:
                content_key = item.content.strip()
                if content_key not in seen:
                    seen.add(content_key)
                    unique_items.append(item)
            items = unique_items
        
        # 排序：按分数降序，时间降序
        items.sort(key=lambda x: (x.score, x.timestamp or datetime.min), reverse=True)
        
        context.items = items
        context.metadata['integration_strategy'] = 'simple'
        
        logger.debug(f"SimpleIntegration: {len(items)} items after integration")
        
        return context


class PriorityIntegrationStrategy(IntegrationStrategy):
    """
    优先级整合策略
    
    根据来源的优先级进行整合，不同来源的内容有不同的权重。
    """
    
    def __init__(
        self,
        source_priorities: Dict[ContextSource, float] = None,
        deduplicate: bool = True,
    ):
        """
        初始化优先级整合策略
        
        Args:
            source_priorities: 来源优先级字典，值越大优先级越高
            deduplicate: 是否去重
        """
        self.deduplicate = deduplicate
        
        # 默认优先级：记忆 > 会话 > 知识 > 外部
        self.source_priorities = source_priorities or {
            ContextSource.MEMORY: 1.0,
            ContextSource.SESSION: 0.8,
            ContextSource.KNOWLEDGE: 0.6,
            ContextSource.EXTERNAL: 0.4,
        }
    
    async def integrate(self, context: ProcessedContext) -> ProcessedContext:
        """
        整合上下文
        
        根据来源优先级调整分数，然后去重和排序。
        """
        items = context.items
        
        # 根据来源调整分数
        for item in items:
            priority = self.source_priorities.get(item.source, 0.5)
            # 将优先级加权到分数中
            item.score = item.score * priority
            item.metadata['priority'] = priority
        
        # 去重
        if self.deduplicate:
            seen = set()
            unique_items = []
            for item in items:
                content_key = item.content.strip()
                if content_key not in seen:
                    seen.add(content_key)
                    unique_items.append(item)
            items = unique_items
        
        # 排序：按调整后的分数降序
        items.sort(key=lambda x: x.score, reverse=True)
        
        context.items = items
        context.metadata['integration_strategy'] = 'priority'
        context.metadata['source_priorities'] = {
            k.value: v for k, v in self.source_priorities.items()
        }
        
        logger.debug(f"PriorityIntegration: {len(items)} items after integration")
        
        return context
