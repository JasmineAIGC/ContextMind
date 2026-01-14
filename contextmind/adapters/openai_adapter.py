"""
OpenAIAdapter - OpenAI 对话系统适配器

支持与 OpenAI API 格式兼容的对话系统集成。
"""

from typing import Optional, List, Dict, Any
from .base import BaseAdapter, DialogContext, DialogMessage


class OpenAIAdapter(BaseAdapter):
    """
    OpenAI 对话系统适配器
    
    支持标准的 OpenAI Chat Completions API 格式。
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
            **kwargs: 其他参数（temperature, max_tokens等）
            
        Returns:
            对话消息
        """
        # 注入优化后的上下文
        enhanced_context = await self.inject_context(user_input, context)
        
        # 构建 OpenAI 格式的消息列表
        messages = []
        
        # 添加系统提示
        if enhanced_context.system_prompt:
            messages.append({
                'role': 'system',
                'content': enhanced_context.system_prompt
            })
        
        # 添加上下文消息
        for msg in enhanced_context.messages:
            messages.append({
                'role': msg.role,
                'content': msg.content
            })
        
        # 添加当前用户输入
        messages.append({
            'role': 'user',
            'content': user_input
        })
        
        # 这里应该调用实际的 LLM API
        # 作为示例，我们返回一个模拟响应
        response_content = f"处理完成: {user_input}"
        
        # 更新引擎状态
        if self.engine:
            await self.engine.update(user_input, response_content)
        
        return DialogMessage(
            role='assistant',
            content=response_content,
            metadata={'model': 'openai-compatible'}
        )
    
    def convert_to_standard(self, external_message: Dict[str, Any]) -> DialogMessage:
        """
        将 OpenAI 消息格式转换为标准格式
        
        Args:
            external_message: OpenAI 格式的消息 {'role': '...', 'content': '...'}
            
        Returns:
            标准化的对话消息
        """
        return DialogMessage(
            role=external_message.get('role', 'user'),
            content=external_message.get('content', ''),
            metadata={}
        )
    
    def convert_from_standard(self, message: DialogMessage) -> Dict[str, Any]:
        """
        将标准格式转换为 OpenAI 消息格式
        
        Args:
            message: 标准化的对话消息
            
        Returns:
            OpenAI 格式的消息字典
        """
        result = {
            'role': message.role,
            'content': message.content,
        }
        
        # 如果有图片（多模态）
        if message.images:
            result['images'] = message.images
        
        return result
