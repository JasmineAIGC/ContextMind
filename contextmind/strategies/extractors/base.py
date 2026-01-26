"""
Base Extractor Interface

Defines the abstract base class for all knowledge extractors.
"""

from abc import ABC, abstractmethod
from typing import List

from ...core.models import Message
from ...core.types import Knowledge


class BaseExtractor(ABC):
    """
    Memory Extractor 基类接口
    
    Extractor 分析对话并识别值得存储到长期记忆的信息
    (事实、偏好、事件等)
    """
    
    @abstractmethod
    async def extract(self, messages: List[Message]) -> List[Knowledge]:
        """
        从消息中提取知识
        
        Args:
            messages: 对话消息列表
            
        Returns:
            提取的知识项列表
        """
        pass
