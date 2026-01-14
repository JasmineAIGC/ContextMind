"""
ContextOptimizer - 上下文优化器

优化上下文以适应模型的输入限制，包括压缩、截断和重排。
"""

from typing import Optional

from ..data_models import ProcessedContext
from ..logger import get_logger

logger = get_logger(__name__)


class ContextOptimizer:
    """
    上下文优化器
    
    对整合后的上下文进行优化：
    - Token限制和截断
    - 重要信息前置
    - Lost-in-the-Middle 优化（可选）
    """
    
    def __init__(
        self,
        max_length: Optional[int] = None,
        max_items: Optional[int] = None,
    ):
        """
        初始化上下文优化器
        
        Args:
            max_length: 最大文本长度限制（字符数）
            max_items: 最大上下文项数量限制
        """
        self.max_length = max_length
        self.max_items = max_items
    
    async def optimize(
        self,
        context: ProcessedContext,
        max_length: Optional[int] = None,
        max_items: Optional[int] = None,
    ) -> ProcessedContext:
        """
        优化上下文
        
        Args:
            context: 待优化的上下文对象
            max_length: 最大文本长度（覆盖初始化参数）
            max_items: 最大项数量（覆盖初始化参数）
            
        Returns:
            优化后的上下文对象
        """
        # 使用传入参数或初始化参数
        max_len = max_length if max_length is not None else self.max_length
        max_it = max_items if max_items is not None else self.max_items
        
        items = context.items
        original_count = len(items)
        
        # 限制项数量
        if max_it and len(items) > max_it:
            items = items[:max_it]
            context.metadata['truncated_by_count'] = True
            logger.debug(f"Truncated items from {original_count} to {max_it}")
        
        # 限制文本长度
        if max_len:
            total_length = sum(len(item.content) for item in items)
            if total_length > max_len:
                # 简单截断策略：按比例保留每个项
                kept_items = []
                current_length = 0
                
                for item in items:
                    if current_length + len(item.content) <= max_len:
                        kept_items.append(item)
                        current_length += len(item.content)
                    else:
                        # 尝试截断当前项以填满剩余空间
                        remaining = max_len - current_length
                        if remaining > 100:  # 至少保留100字符
                            truncated_content = item.content[:remaining] + "..."
                            truncated_item = ContextItem(
                                content=truncated_content,
                                source=item.source,
                                score=item.score,
                                timestamp=item.timestamp,
                                metadata={**item.metadata, 'truncated': True}
                            )
                            kept_items.append(truncated_item)
                        break
                
                items = kept_items
                context.metadata['truncated_by_length'] = True
                logger.debug(f"Truncated by length from {total_length} to {max_len} chars")
        
        # 更新上下文
        context.items = items
        context.metadata['optimized'] = True
        context.metadata['final_items'] = len(items)
        
        logger.debug(f"Optimized to {len(items)} context items")
        
        return context
