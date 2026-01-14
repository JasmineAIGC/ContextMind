"""
LangChainAdapter - LangChain 对话系统适配器

支持与 LangChain 框架的集成。
"""

from typing import Optional, List, Any
from .base import BaseAdapter, DialogContext, DialogMessage


class LangChainAdapter(BaseAdapter):
    """
    LangChain 对话系统适配器
    
    支持 LangChain 的 ConversationChain 和其他对话组件。
    """
    
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
        # 注入优化后的上下文
        enhanced_context = await self.inject_context(user_input, context)
        
        # 构建 LangChain 兼容的上下文
        langchain_context = self._build_langchain_context(enhanced_context)
        
        # 这里应该调用 LangChain 的对话链
        # 作为示例，我们返回一个模拟响应
        response_content = f"LangChain 处理: {user_input}"
        
        # 更新引擎状态
        if self.engine:
            await self.engine.update(user_input, response_content)
        
        return DialogMessage(
            role='assistant',
            content=response_content,
            metadata={'framework': 'langchain'}
        )
    
    def convert_to_standard(self, external_message: Any) -> DialogMessage:
        """
        将 LangChain 消息格式转换为标准格式
        
        Args:
            external_message: LangChain 的消息对象
            
        Returns:
            标准化的对话消息
        """
        # LangChain 的消息可能是字符串或对象
        if isinstance(external_message, str):
            return DialogMessage(
                role='user',
                content=external_message,
                metadata={}
            )
        
        # 处理 LangChain 的消息对象
        role = getattr(external_message, 'role', 'user')
        content = getattr(external_message, 'content', str(external_message))
        
        return DialogMessage(
            role=role,
            content=content,
            metadata={}
        )
    
    def convert_from_standard(self, message: DialogMessage) -> str:
        """
        将标准格式转换为 LangChain 消息格式
        
        Args:
            message: 标准化的对话消息
            
        Returns:
            LangChain 格式的消息
        """
        # LangChain 通常使用字符串格式
        return message.content
    
    def _build_langchain_context(self, context: DialogContext) -> str:
        """
        构建 LangChain 兼容的上下文字符串
        
        Args:
            context: 对话上下文
            
        Returns:
            上下文字符串
        """
        parts = []
        
        if context.system_prompt:
            parts.append(f"System: {context.system_prompt}")
        
        for msg in context.messages:
            parts.append(f"{msg.role.capitalize()}: {msg.content}")
        
        return "\n".join(parts)
