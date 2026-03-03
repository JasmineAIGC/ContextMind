"""
ContextCompressor - 管道架构步骤3

上下文压缩和优化。
"""

from typing import Optional

from ..core.data_models import ProcessedContext, ContextResult
from contextmind.infra.logger import get_logger
from ..core.strategies import CompressionStrategy

logger = get_logger(__name__)

DEFAULT_MAX_SESSION_ITEMS = 10  # 默认保留最近10条会话条目，平衡上下文完整性和Token开销


class ContextCompressor:
    """
    上下文压缩器，将收集到的上下文压缩以减少Token消耗。

    策略将原始条目分类为近期历史、长期记忆和外部知识三层结构，
    使 LLM 提示保持在合理的 Token 预算内。
    """

    def __init__(
        self,
        strategy: Optional[CompressionStrategy] = None,
        max_session_items: int = 10,
    ):
        self.strategy = strategy or CompressionStrategy(
            max_items=max_session_items
        )

    async def compress(
        self,
        context: ProcessedContext,
    ) -> ContextResult:
        """
        将 ProcessedContext 分层压缩为 ContextResult。

        CompressionStrategy 负责按优先级将条目分配到
        recent_history / long_term_memory / external_knowledge 三个槽位。
        """
        input_items_count = len(context.items)

        result = await self.strategy.optimize(context)

        logger.debug(
            f"压缩上下文: "
            f"{input_items_count} 项 → "
            f"{len(result.recent_history)} 历史 + "
            f"{len(result.long_term_memory)} 记忆 + "
            f"{len(result.external_knowledge)} 知识"
        )
        
        return result
