"""
Strategy Base Classes - 策略基类

定义了所有策略的抽象基类接口和默认实现
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from .models import ContextItem, ProcessedContext, ContextResult, Message, Knowledge, get_logger

logger = get_logger(__name__)


class RetrievalStrategy(ABC):
    """
    检索策略基类
    
    定义了从长期记忆或外部知识库检索相关信息的接口
    """
    
    @abstractmethod
    async def retrieve(self, query: str, memory_cache: List[ContextItem] = None, limit: int = 5, **kwargs) -> List[ContextItem]:
        """
        检索相关上下文
        
        Args:
            query: 查询字符串
            memory_cache: 可用的记忆库（用于内存检索）
            limit: 返回的最大结果数
            **kwargs: 其他参数
            
        Returns:
            上下文条目列表
        """
        pass


class IntegrationStrategy(ABC):
    """
    整合策略基类
    
    定义了整合多个来源上下文的接口
    """
    
    @abstractmethod
    async def integrate(self, context: ProcessedContext) -> ProcessedContext:
        """
        整合上下文
        
        Args:
            context: 待整合的上下文
            
        Returns:
            整合后的上下文
        """
        pass


class OptimizationStrategy(ABC):
    """
    优化策略基类
    
    定义了优化上下文以适应模型输入限制的接口
    
    **重要: 返回类型说明**
    - 输入: ProcessedContext (包含 items 列表)
    - 输出: 可以是 ProcessedContext (中间步骤) 或 ContextResult (最终步骤)
    
    优化策略分为两类:
    1. **中间优化** (如 RerankingStrategy): 返回 ProcessedContext, 用于 Pipeline 中间步骤
    2. **最终优化** (如 CompressionStrategy): 返回 ContextResult, 调用 context.to_context_result() 转换
    
    这样可以确保类型安全, 同时保持 Pipeline 的灵活性
    """
    
    @abstractmethod
    async def optimize(self, context: ProcessedContext):
        """
        优化上下文
        
        Args:
            context: 待优化的上下文 (ProcessedContext)
            
        Returns:
            ProcessedContext 或 ContextResult，取决于策略的用途
            
        Note:
            - 中间优化步骤：返回 ProcessedContext
            - 最终优化步骤：调用 context.to_context_result() 并返回 ContextResult
        """
        pass


class ExtractionStrategy(ABC):
    """
    提取策略基类
    
    定义了从对话中提取结构化知识的接口。
    """
    
    @abstractmethod
    async def extract(self, messages: List[Message]) -> List[Knowledge]:
        """
        提取知识
        
        Args:
            messages: 消息列表
            
        Returns:
            提取的知识列表
        """
        pass


class UpdateStrategy(ABC):
    """
    更新策略基类
    
    定义了如何将新知识添加到记忆库的接口，包括去重、合并等逻辑。
    """
    
    @abstractmethod
    async def update(self, memory_cache: List[ContextItem], new_knowledge: List[Knowledge]) -> List[ContextItem]:
        """
        更新记忆库
        
        Args:
            memory_cache: 当前记忆库条目
            new_knowledge: 新提取的知识列表
            
        Returns:
            更新后的记忆库条目列表
        """
        pass


class SummarizerStrategy(ABC):
    """
    摘要策略基类
    
    定义了对话摘要的接口。
    """
    
    @abstractmethod
    async def summarize(self, messages: List[Message], existing_summary: Optional[str] = None) -> str:
        """
        生成对话摘要
        
        Args:
            messages: 消息列表
            existing_summary: 已有摘要（用于增量更新）
            
        Returns:
            摘要文本
        """
        pass


# Alias for backwards compatibility
BaseStrategy = ExtractionStrategy
BaseExtractor = ExtractionStrategy
BaseRetriever = RetrievalStrategy
BaseUpdater = UpdateStrategy


# Default Implementations

class CompressionStrategy(OptimizationStrategy):
    """
    默认压缩策略
    
    简单的滑动窗口策略，保留最近的N个条目。
    """
    
    def __init__(self, max_items: int = 10):
        """
        初始化压缩策略
        
        Args:
            max_items: 最大保留条目数
        """
        self.max_items = max_items
    
    async def optimize(self, context: ProcessedContext) -> ContextResult:
        """
        压缩上下文
        
        保留最近的max_items个条目。
        
        Args:
            context: 待压缩的上下文
            
        Returns:
            压缩后的上下文结果
        """
        # 简单滑动窗口策略：保留最近的条目
        if len(context.items) > self.max_items:
            logger.debug(f"[CompressionStrategy] 压缩前: {len(context.items)} 项")
            context.items = context.items[-self.max_items:]
            logger.debug(f"[CompressionStrategy] 压缩后: {len(context.items)} 项")
        
        # 转换为ContextResult
        return context.to_context_result()


class RerankingStrategy(OptimizationStrategy):
    """
    默认重排序策略
    
    按时间戳和来源重新排序上下文条目。
    """
    
    async def optimize(self, context: ProcessedContext) -> ProcessedContext:
        """
        重排序上下文
        
        Args:
            context: 待重排序的上下文
            
        Returns:
            重排序后的上下文
        """
        # 简单实现：按时间戳排序（保持原有顺序）
        # 更复杂的实现可以按相关性、重要性等进行排序
        logger.debug(f"[RerankingStrategy] 重排序 {len(context.items)} 项")
        
        # 这里可以添加更复杂的排序逻辑
        # 目前保持原有顺序
        return context


__all__ = [
    # Base strategy interfaces
    'ExtractionStrategy',
    'RetrievalStrategy',
    'IntegrationStrategy',
    'OptimizationStrategy',
    'UpdateStrategy',
    'SummarizerStrategy',
    # Backward compatibility aliases
    'BaseStrategy',
    'BaseExtractor',
    'BaseRetriever',
    'BaseUpdater',
    # Default strategies
    'CompressionStrategy',
    'RerankingStrategy',
]
