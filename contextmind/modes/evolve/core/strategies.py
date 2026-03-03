"""策略基类 - 定义了所有策略的抽象基类接口和默认实现。"""

from abc import ABC, abstractmethod
from typing import List, Optional

from .data_models import ContextItem, ProcessedContext, ContextResult, Message, Knowledge
from contextmind.infra.logger import get_logger

logger = get_logger(__name__)


class RetrievalStrategy(ABC):
    """从长期记忆或外部知识库检索相关信息的接口。"""
    
    @abstractmethod
    async def retrieve(self, query: str, memory_cache: List[ContextItem] = None, limit: int = 5, **kwargs) -> List[ContextItem]:
        """检索相关上下文，返回最多 limit 个上下文条目。"""
        pass


class IntegrationStrategy(ABC):
    """整合多个来源上下文的接口。"""
    
    @abstractmethod
    async def integrate(self, context: ProcessedContext) -> ProcessedContext:
        """整合上下文。"""
        pass


class OptimizationStrategy(ABC):
    """
    优化上下文以适应模型输入限制的接口。

    返回类型取决于策略用途：中间优化返回 ProcessedContext，最终优化返回 ContextResult。
    """
    
    @abstractmethod
    async def optimize(self, context: ProcessedContext):
        pass


class ExtractionStrategy(ABC):
    """从对话中提取结构化知识的接口。"""
    
    @abstractmethod
    async def extract(self, messages: List[Message]) -> List[Knowledge]:
        pass


class UpdateStrategy(ABC):
    """将新知识添加到记忆库的接口，包括去重、合并等逻辑。"""
    
    @abstractmethod
    async def update(self, memory_cache: List[ContextItem], new_knowledge: List[Knowledge]) -> List[ContextItem]:
        pass


class SummarizerStrategy(ABC):
    """对话摘要的接口。"""
    
    @abstractmethod
    async def summarize(self, messages: List[Message], existing_summary: Optional[str] = None) -> str:
        pass



class CompressionStrategy(OptimizationStrategy):
    """
    默认压缩策略
    
    简单的滑动窗口策略，保留最近的N个条目。
    """
    
    def __init__(self, max_items: int = 10):
        self.max_items = max_items
    
    async def optimize(self, context: ProcessedContext) -> ContextResult:
        """保留最近的 max_items 个条目。"""
        if len(context.items) > self.max_items:
            logger.debug(f"[CompressionStrategy] 压缩前: {len(context.items)} 项")
            context.items = context.items[-self.max_items:]
            logger.debug(f"[CompressionStrategy] 压缩后: {len(context.items)} 项")
        return context.to_context_result()


class RerankingStrategy(OptimizationStrategy):
    """
    默认重排序策略
    
    按时间戳和来源重新排序上下文条目。
    """
    
    async def optimize(self, context: ProcessedContext) -> ProcessedContext:
        """重排序上下文（当前保持原有顺序）。"""
        logger.debug(f"[RerankingStrategy] 重排序 {len(context.items)} 项")
        return context


__all__ = [
    'ExtractionStrategy',
    'RetrievalStrategy',
    'IntegrationStrategy',
    'OptimizationStrategy',
    'UpdateStrategy',
    'SummarizerStrategy',
    'CompressionStrategy',
    'RerankingStrategy',
]
