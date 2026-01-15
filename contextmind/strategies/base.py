"""
Strategy Base Classes - 策略基类

定义了所有策略的抽象基类接口。
"""

from abc import ABC, abstractmethod
from typing import List

from ..data_models import ContextItem, ProcessedContext, Message, Knowledge


class RetrievalStrategy(ABC):
    """
    检索策略基类
    
    定义了从长期记忆或外部知识库检索相关信息的接口。
    """
    
    @abstractmethod
    async def retrieve(self, query: str, limit: int = 5, **kwargs) -> List[ContextItem]:
        """
        检索相关上下文
        
        Args:
            query: 查询字符串
            limit: 返回的最大结果数
            **kwargs: 其他参数
            
        Returns:
            上下文条目列表
        """
        pass


class IntegrationStrategy(ABC):
    """
    整合策略基类
    
    定义了整合多个来源上下文的接口。
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
    
    定义了优化上下文以适应模型输入限制的接口。
    """
    
    @abstractmethod
    async def optimize(self, context: ProcessedContext) -> ProcessedContext:
        """
        优化上下文
        
        Args:
            context: 待优化的上下文
            
        Returns:
            优化后的上下文
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
