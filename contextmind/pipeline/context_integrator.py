"""
ContextIntegrator - 上下文整合器

整合收集到的上下文信息，包括去重、排序和组织。
"""

from typing import Optional

from ..data_models import ProcessedContext, ContextItem
from ..logger import get_logger

logger = get_logger(__name__)


class ContextIntegrator:
    """
    上下文整合器
    
    对收集到的上下文进行整合处理：
    - 去除重复内容
    - 按相关性和时间排序
    - 组织上下文结构
    """
    
    def __init__(self, deduplicate: bool = True):
        """
        初始化上下文整合器
        
        Args:
            deduplicate: 是否去重，默认为True
        """
        self.deduplicate = deduplicate
    
    async def integrate(self, context: ProcessedContext) -> ProcessedContext:
        """
        整合上下文
        
        Args:
            context: 待整合的上下文对象
            
        Returns:
            整合后的上下文对象
        """
        items = context.items
        
        # 去重
        if self.deduplicate:
            seen = set()
            unique_items = []
            for item in items:
                # 使用内容作为去重键
                content_key = item.content.strip()
                if content_key not in seen:
                    seen.add(content_key)
                    unique_items.append(item)
            
            removed_count = len(items) - len(unique_items)
            if removed_count > 0:
                logger.debug(f"Removed {removed_count} duplicate items")
            
            items = unique_items
        
        # 排序：先按分数（降序），再按时间（降序）
        items.sort(key=lambda x: (x.score, x.timestamp or 0), reverse=True)
        
        # 更新上下文
        context.items = items
        context.metadata['integrated'] = True
        context.metadata['unique_items'] = len(items)
        
        logger.debug(f"Integrated {len(items)} context items")
        
        return context
