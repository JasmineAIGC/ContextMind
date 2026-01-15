"""
CustomAdapter - 自定义对话系统适配器

提供灵活的适配器实现，支持完全自定义的集成逻辑。
"""

from typing import Optional, Any, Callable
from .base import BaseAdapter, DialogContext, DialogMessage


class CustomAdapter(BaseAdapter):
    """
    自定义对话系统适配器
    
    允许用户完全自定义消息转换和处理逻辑。
    
    使用示例：
        ```python
        def my_converter(msg):
            return DialogMessage(role=msg['role'], content=msg['text'])
        
        adapter = CustomAdapter(
            engine=engine,
            to_standard_converter=my_converter,
            from_standard_converter=lambda msg: {'role': msg.role, 'text': msg.content}
        )
        ```
    """
    
    def __init__(
        self,
        engine=None,
        to_standard_converter: Optional[Callable] = None,
        from_standard_converter: Optional[Callable] = None,
        processor: Optional[Callable] = None,
        **config
    ):
        """
        初始化自定义适配器
        
        Args:
            engine: ContextEngine 实例
            to_standard_converter: 外部格式到标准格式的转换函数
            from_standard_converter: 标准格式到外部格式的转换函数
            processor: 自定义处理函数
            **config: 其他配置
        """
        super().__init__(engine, **config)
        self.to_standard_converter = to_standard_converter
        self.from_standard_converter = from_standard_converter
        self.processor = processor
    
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
        # 如果提供了自定义处理器，使用它
        if self.processor:
            result = self.processor(user_input, context, **kwargs)
            # 支持异步处理器
            if hasattr(result, '__await__'):
                result = await result
            return result
        
        # 默认处理流程
        enhanced_context = await self.inject_context(user_input, context)
        
        # 这里可以添加自定义逻辑
        response_content = f"Custom 处理: {user_input}"
        
        # 更新引擎状态
        if self.engine:
            await self.engine.update(user_input, response_content)
        
        return DialogMessage(
            role='assistant',
            content=response_content,
            metadata={'adapter': 'custom'}
        )
    
    def convert_to_standard(self, external_message: Any) -> DialogMessage:
        """
        将外部消息格式转换为标准格式
        
        Args:
            external_message: 外部系统的消息对象
            
        Returns:
            标准化的对话消息
        """
        if self.to_standard_converter:
            return self.to_standard_converter(external_message)
        
        # 默认处理：假设是字典或字符串
        if isinstance(external_message, dict):
            return DialogMessage(
                role=external_message.get('role', 'user'),
                content=external_message.get('content', ''),
                metadata=external_message.get('metadata', {})
            )
        elif isinstance(external_message, str):
            return DialogMessage(
                role='user',
                content=external_message,
                metadata={}
            )
        else:
            raise ValueError(f"Unsupported message type: {type(external_message)}")
    
    def convert_from_standard(self, message: DialogMessage) -> Any:
        """
        将标准格式转换为外部消息格式
        
        Args:
            message: 标准化的对话消息
            
        Returns:
            外部系统的消息对象
        """
        if self.from_standard_converter:
            return self.from_standard_converter(message)
        
        # 默认返回字典格式
        return message.to_dict()
