"""
工具基类

定义 ContextMind 工具的基础接口。
"""

from typing import Any, Dict, List, Optional
from abc import ABC, abstractmethod


class BaseTool(ABC):
    """工具基类。"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称。"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述。"""
        pass
    
    @abstractmethod
    async def execute(self, *args, **kwargs) -> Any:
        """执行工具。"""
        pass


class ContextMindTools:
    """ContextMind 工具集合。
    
    Args:
        engine: ContextEngine 实例，需要提供 memory_bank 和 session_manager 属性
    """
    
    def __init__(self, engine):
        """初始化工具集。
        
        Args:
            engine: ContextEngine 实例
        """
        self.engine = engine
        # 显式检查必需的属性
        try:
            self.memory_bank = engine.memory_bank
            self.session_manager = engine.session_manager
        except AttributeError as e:
            # 如果 engine 没有这些属性，设置为 None
            self.memory_bank = None
            self.session_manager = None
    
    def get_all_tools(self) -> List[BaseTool]:
        """获取所有工具。"""
        from .memory_tools import MemoryTools
        from .context_tools import ContextTools
        
        tools = []
        
        if self.memory_bank:
            memory_tools = MemoryTools(self.memory_bank)
            tools.extend(memory_tools.get_tools())
        
        if self.engine:
            context_tools = ContextTools(self.engine)
            tools.extend(context_tools.get_tools())
        
        return tools
