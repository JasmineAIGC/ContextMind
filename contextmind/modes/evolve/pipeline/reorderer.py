"""
ContextReorderer - 管道架构步骤4

上下文重排序和优先级处理。
"""

from typing import Optional

from ..core.data_models import ProcessedContext
from contextmind.infra.logger import get_logger
from ..core.strategies import RerankingStrategy

logger = get_logger(__name__)


class ContextReorderer:
    """
    上下文重排序器，对上下文按时间戳、来源优先级或相关性重排序。

    正确的上下文顺序对 LLM 的注意力分配有显著影响：
    高相关内容应靠近 prompt 末尾（proximity bias），时间越近的历史优先级越高。
    """

    def __init__(
        self,
        strategy: Optional[RerankingStrategy] = None,
    ):
        self.strategy = strategy or RerankingStrategy()

    async def reorder(
        self,
        context: ProcessedContext,
    ) -> ProcessedContext:
        """对上下文条目重排序，使最相关/最新的内容出现在靠近查询的位置。"""
        reordered = await self.strategy.optimize(context)

        logger.debug(f"重排序 {len(reordered.items)} 个上下文项")

        return reordered
