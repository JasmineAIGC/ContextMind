"""
OpenAIAdapter - OpenAI 对话系统适配器

支持与 OpenAI API 格式兼容的对话系统集成。

v3.3 更新：
- 真正调用 LLM API 生成响应
- 使用增强后的 system prompt（包含长期记忆和外部知识）
"""

from typing import Optional, List, Dict, Any
from .base import BaseAdapter, DialogContext, DialogMessage


class OpenAIAdapter(BaseAdapter):
    """
    OpenAI 对话系统适配器
    
    支持标准的 OpenAI Chat Completions API 格式。
    
    v3.3 更新：
    - 真正调用 LLM 客户端生成响应
    - 使用 get_enhanced_system_prompt() 整合长期记忆
    """
    
    async def process(
        self,
        user_input: str,
        context: Optional[DialogContext] = None,
        **kwargs
    ) -> DialogMessage:
        """
        处理用户输入并生成响应
        
        流程：
        1. 调用 inject_context() 获取优化后的上下文
        2. 使用 get_enhanced_system_prompt() 获取包含长期记忆的 system prompt
        3. 调用 LLM 客户端生成响应
        4. 更新引擎状态
        
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
        
        # ===== v3.3 关键改进：使用增强后的 system prompt =====
        # 这会将长期记忆和外部知识整合到 system prompt 中
        enhanced_system_prompt = enhanced_context.get_enhanced_system_prompt()
        if enhanced_system_prompt:
            messages.append({
                'role': 'system',
                'content': enhanced_system_prompt
            })
        
        # 添加历史对话消息
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
        
        # ===== v3.3 关键改进：真正调用 LLM API =====
        response_content = await self._call_llm(messages, **kwargs)
        
        # 更新引擎状态
        if self.engine:
            await self.engine.update(user_input, response_content)
        
        return DialogMessage(
            role='assistant',
            content=response_content,
            metadata={
                'model': 'openai-compatible',
                'context_enhanced': True,
                'memory_injected': bool(enhanced_context.long_term_memory_text),
            }
        )
    
    async def _call_llm(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """
        调用 LLM API 生成响应
        
        Args:
            messages: OpenAI 格式的消息列表
            **kwargs: LLM 参数（temperature, max_tokens等）
            
        Returns:
            生成的响应文本
        """
        # 如果有 LLM 客户端，使用它
        if self.llm_client:
            try:
                # 使用 Client.chat() 方法
                response, _ = self.llm_client.chat(
                    messages=messages,
                    temperature=kwargs.get('temperature'),
                    max_tokens=kwargs.get('max_tokens'),
                )
                return response
            except Exception as e:
                # 记录错误但继续（降级处理）
                import logging
                logging.warning(f"LLM call failed: {e}, using fallback")
        
        # 如果引擎有 LLM 客户端，使用它
        if self.engine and self.engine.llm_client:
            try:
                response, _ = self.engine.llm_client.chat(
                    messages=messages,
                    temperature=kwargs.get('temperature'),
                    max_tokens=kwargs.get('max_tokens'),
                )
                return response
            except Exception as e:
                import logging
                logging.warning(f"Engine LLM call failed: {e}, using fallback")
        
        # 降级：返回提示信息（仅用于测试/开发）
        return f"[LLM未配置] 请设置 llm_client 参数。收到消息: {messages[-1]['content']}"
    
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
