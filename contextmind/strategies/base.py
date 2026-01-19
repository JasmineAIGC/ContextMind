"""
Strategy Base Classes - 策略基类

定义了所有策略的抽象基类接口。
"""

from abc import ABC, abstractmethod
from typing import List

from ..data_models import ContextItem, ProcessedContext, ContextResult, Message, Knowledge


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
    
    **重要：返回类型变更**
    - 输入：ProcessedContext（包含 items 列表）
    - 输出：ContextResult（包含 recent_history, long_term_memory, external_knowledge）
    
    优化策略应该：
    1. 处理 ProcessedContext.items（压缩、重排、过滤等）
    2. 调用 context.to_context_result() 转换为 ContextResult
    3. 返回 ContextResult
    
    这样可以确保类型安全，避免在 pipeline 中混用 ProcessedContext 和 ContextResult。
    """
    
    @abstractmethod
    async def optimize(self, context: ProcessedContext) -> 'ContextResult':
        """
        优化上下文
        
        Args:
            context: 待优化的上下文（ProcessedContext）
            
        Returns:
            优化后的上下文结果（ContextResult）
            
        Note:
            实现时应该先处理 context.items，然后调用 context.to_context_result() 
            将 ProcessedContext 转换为 ContextResult 后返回。
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
