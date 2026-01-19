"""
ContextCompressor - 上下文压缩模块

职责：
- 压缩历史上下文
- 减少Token消耗（核心痛点）
- 摘要生成

可插拔策略：
- LLMLingua2压缩
- Gist压缩
- LongLLMLingua
- AutoCompressor
- 滑动窗口
- 摘要策略（Summary）
"""

from typing import List, Optional
from ..data_models import ContextResult, ProcessedContext
from ..strategies.optimization import CompressionStrategy
from ..logger import get_logger

logger = get_logger(__name__)

# Default maximum number of session items (for backward compatibility)
DEFAULT_MAX_SESSION_ITEMS = 10


class ContextCompressor:
    """
    上下文压缩器
    
    将收集到的上下文进行压缩以减少Token消耗：
    - 滑动窗口策略
    - 摘要生成
    - 智能过滤
    """
    
    def __init__(
        self,
        strategy: Optional[CompressionStrategy] = None,
        max_session_items: int = 10,
    ):
        """
        初始化压缩器
        
        Args:
            strategy: 压缩策略（可插拔）
            max_session_items: 最大会话条目数
        """
        self.strategy = strategy or CompressionStrategy(
            max_items=max_session_items
        )
    
    async def compress(
        self,
        context: ProcessedContext,
    ) -> ContextResult:
        """
        压缩上下文
        
        Args:
            context: 待压缩的上下文
            
        Returns:
            压缩后的结果
        """
        # 委托给压缩策略
        result = await self.strategy.optimize(context)
        
        logger.debug(
            f"Compressed context: "
            f"{len(context.items)} items → "
            f"{len(result.recent_history)} history + "
            f"{len(result.long_term_memory)} memories"
        )
        
        return result
