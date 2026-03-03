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
    """上下文重排序器，对上下文按时间戳、来源优先级或相关性重排序。"""

    def __init__(
        self,
        strategy: Optional[RerankingStrategy] = None,
    ):
        self.strategy = strategy or RerankingStrategy()

    async def reorder(
        self,
        context: ProcessedContext,
    ) -> ProcessedContext:
        reordered = await self.strategy.optimize(context)

        logger.debug(f"重排序 {len(reordered.items)} 个上下文项")

        return reordered
