"""
BaseProcessor - 处理器基类

定义了处理流水线中所有处理器的基础接口。
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseProcessor(ABC):
    """
    处理器基类
    
    所有处理流水线组件的基类，定义了处理器的基本接口。
    """
    
    @abstractmethod
    async def process(self, input_data: Any) -> Any:
        """
        处理输入数据
        
        Args:
            input_data: 输入数据，类型由具体处理器定义
            
        Returns:
            处理后的数据，类型由具体处理器定义
        """
        pass
