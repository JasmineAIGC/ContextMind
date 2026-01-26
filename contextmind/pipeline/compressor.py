"""
ContextCompressor - Step 3 of Pipeline Architecture

Context compression and optimization.
"""

from typing import Optional

from ..core.models import ProcessedContext, ContextResult, get_logger
from ..core.strategies import CompressionStrategy

logger = get_logger(__name__)

# 默认最大 Session 项数量 (用于向后兼容)
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
        
        这是 pipeline 的最后一步，将 ProcessedContext 转换为 ContextResult。
        
        Args:
            context: 待压缩的上下文（ProcessedContext）
            
        Returns:
            压缩后的结果（ContextResult）
            
        Note:
            策略的 optimize() 方法已经负责转换为 ContextResult，
            这里直接返回策略的结果即可。
        """
        # 记录压缩前的信息
        input_items_count = len(context.items)
        
        # 委托给压缩策略 (策略会返回 ContextResult)
        result = await self.strategy.optimize(context)
        
        # 使用 ContextResult 的属性记录日志
        logger.debug(
            f"压缩上下文: "
            f"{input_items_count} 项 → "
            f"{len(result.recent_history)} 历史 + "
            f"{len(result.long_term_memory)} 记忆 + "
            f"{len(result.external_knowledge)} 知识"
        )
        
        return result
