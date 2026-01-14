"""
BaseAdapter - 对话系统适配器基类

定义了将 ContextMind 集成到对话系统的标准接口。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime

from ..data_models import Message, ContextResult


@dataclass
class DialogMessage:
    """
    标准化的对话消息格式
    
    兼容多种对话系统的消息格式
    """
    role: str  # "user", "assistant", "system"
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[datetime] = None
    
    # 多模态支持
    images: Optional[List[str]] = None  # 图片 URL 或 base64
    files: Optional[List[str]] = None   # 文件路径
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        result = {
            'role': self.role,
            'content': self.content,
            'metadata': self.metadata,
        }
        if self.timestamp:
            result['timestamp'] = self.timestamp.isoformat()
        if self.images:
            result['images'] = self.images
        if self.files:
            result['files'] = self.files
        return result


@dataclass
class DialogContext:
    """
    对话上下文容器
    
    封装了对话历史、系统提示和其他元数据
    """
    messages: List[DialogMessage] = field(default_factory=list)
    system_prompt: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_message(self, message: DialogMessage):
        """添加消息到上下文"""
        self.messages.append(message)
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            'messages': [msg.to_dict() for msg in self.messages],
            'system_prompt': self.system_prompt,
            'metadata': self.metadata,
        }


class BaseAdapter(ABC):
    """
    对话系统适配器基类
    
    定义了集成 ContextMind 到任意对话系统的标准接口。
    
    主要功能：
    1. 消息格式转换
    2. 上下文注入
    3. 响应处理
    4. 会话管理
    """
    
    def __init__(self, engine=None, **config):
        """
        初始化适配器
        
        Args:
            engine: ContextEngine 实例
            **config: 适配器配置
        """
        self.engine = engine
        self.config = config
        self._hooks = {
            'before_optimize': [],
            'after_optimize': [],
            'before_generate': [],
            'after_generate': [],
        }
    
    @abstractmethod
    async def process(
        self,
        user_input: str,
        context: Optional[DialogContext] = None,
        **kwargs
    ) -> DialogMessage:
        """
        处理用户输入并生成响应
        
        Args:
            user_input: 用户输入
            context: 对话上下文
            **kwargs: 其他参数
            
        Returns:
            对话消息
        """
        pass
    
    @abstractmethod
    def convert_to_standard(self, external_message: Any) -> DialogMessage:
        """
        将外部对话系统的消息格式转换为标准格式
        
        Args:
            external_message: 外部系统的消息对象
            
        Returns:
            标准化的对话消息
        """
        pass
    
    @abstractmethod
    def convert_from_standard(self, message: DialogMessage) -> Any:
        """
        将标准格式转换为外部对话系统的消息格式
        
        Args:
            message: 标准化的对话消息
            
        Returns:
            外部系统的消息对象
        """
        pass
    
    def register_hook(self, event: str, callback: Callable):
        """
        注册钩子函数
        
        Args:
            event: 事件名称 (before_optimize, after_optimize, before_generate, after_generate)
            callback: 回调函数
        """
        if event in self._hooks:
            self._hooks[event].append(callback)
    
    async def _run_hooks(self, event: str, *args, **kwargs):
        """运行钩子函数"""
        for callback in self._hooks.get(event, []):
            if callable(callback):
                result = callback(*args, **kwargs)
                # 支持异步钩子
                if hasattr(result, '__await__'):
                    await result
    
    async def inject_context(
        self,
        user_input: str,
        base_context: Optional[DialogContext] = None
    ) -> DialogContext:
        """
        注入优化后的上下文
        
        Args:
            user_input: 用户输入
            base_context: 基础上下文
            
        Returns:
            增强后的对话上下文
        """
        if not self.engine:
            # 如果没有引擎，返回原始上下文
            return base_context or DialogContext()
        
        # 运行前置钩子
        await self._run_hooks('before_optimize', user_input, base_context)
        
        # 优化上下文
        context_result = await self.engine.optimize(
            user_input=user_input,
            include_session=True,
            include_memory=True,
        )
        
        # 运行后置钩子
        await self._run_hooks('after_optimize', context_result)
        
        # 转换为对话上下文
        dialog_context = base_context or DialogContext()
        
        # 添加历史消息
        for msg in context_result.recent_history:
            dialog_context.add_message(DialogMessage(
                role=msg.role.value,
                content=msg.content,
                timestamp=msg.timestamp,
                metadata=msg.metadata
            ))
        
        # 添加长期记忆到元数据
        if context_result.long_term_memory:
            dialog_context.metadata['long_term_memory'] = [
                item.to_dict() for item in context_result.long_term_memory
            ]
        
        # 添加外部知识到元数据
        if context_result.external_knowledge:
            dialog_context.metadata['external_knowledge'] = [
                item.to_dict() for item in context_result.external_knowledge
            ]
        
        return dialog_context
