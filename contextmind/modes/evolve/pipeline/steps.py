"""
管道处理步骤（Pipeline Steps）

将四个单职责的管道步骤合并为一个模块，减少文件碎片：

  InputPreprocessor   — 步骤1：输入预处理与标准化
  ContextRetriever    — 步骤2：外部上下文检索（占位符，实际检索由 MemoryBank 处理）
  ContextCompressor   — 步骤3：上下文压缩，减少 Token 消耗
  ContextReorderer    — 步骤4：上下文重排序，使最相关内容靠近查询位置
"""

import re
from typing import Optional, List, Any

from ..core.data_models import ProcessedContext, ContextResult, ContextItem
from ..core.strategies import CompressionStrategy, RerankingStrategy
from contextmind.infra.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 步骤1：输入预处理
# ---------------------------------------------------------------------------

class InputPreprocessor:
    """
    输入预处理器，对用户输入进行标准化处理（去空白、验证、清洗）。

    先验证边界再规范化，确保下游组件拿到干净且长度可预期的字符串。
    """

    def __init__(
        self,
        min_length: int = 1,
        max_length: int = 10000,  # 约等于 ~7500 tokens，防止超出常见 LLM 上下文窗口
    ):
        self.min_length = min_length
        self.max_length = max_length

    async def process(self, user_input: str) -> str:
        """
        处理用户输入。

        Args:
            user_input: 原始输入

        Returns:
            处理后的输入

        Raises:
            ValueError: 输入无效
        """
        processed = user_input.strip()

        if len(processed) < self.min_length:
            raise ValueError(f"输入过短 (最小 {self.min_length} 字符)")

        if len(processed) > self.max_length:
            raise ValueError(f"输入过长 (最大 {self.max_length} 字符)")

        processed = re.sub(r'\s+', ' ', processed)  # 将换行、Tab、多余空格统一为单个空格

        logger.debug(f"[InputPreprocessor] 输出: '{processed}'")

        return processed


# ---------------------------------------------------------------------------
# 步骤2：外部上下文检索
# ---------------------------------------------------------------------------

class ContextRetriever:
    """
    从外部知识库检索相关信息。

    当前检索功能主要由 MemoryBank 实现，此模块为架构完整性保留，
    未来可接入向量数据库、搜索引擎等外部知识源。
    """

    def __init__(self, knowledge_base: Optional[Any] = None):
        self.knowledge_base = knowledge_base
        logger.debug("[ContextRetriever] 初始化完成")

    async def retrieve(self, query: str, top_k: int = 5) -> List[ContextItem]:
        """
        检索相关上下文。

        top_k=5 是经验值：在相关性覆盖和 Token 开销之间的平衡点。
        """
        if not self.knowledge_base:
            logger.debug("[ContextRetriever] 无外部知识库配置")
            return []

        # 可扩展：调用向量数据库、搜索引擎等
        result = []
        logger.debug(f"[ContextRetriever] 输出: {len(result)} 个外部知识项")
        return result


# ---------------------------------------------------------------------------
# 步骤3：上下文压缩
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 步骤4：上下文重排序
# ---------------------------------------------------------------------------

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


__all__ = [
    "InputPreprocessor",
    "ContextRetriever",
    "ContextCompressor",
    "ContextReorderer",
    "DEFAULT_MAX_SESSION_ITEMS",
]
