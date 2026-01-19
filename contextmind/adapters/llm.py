"""
LLM Adapters - Unified LLM integration adapters

Merged from openai_adapter.py, langchain_adapter.py, and custom_adapter.py.
Provides adapters for different LLM frameworks and custom integrations.
"""

from typing import Optional, List, Dict, Any, Callable
from .base import BaseAdapter, DialogContext, DialogMessage
from ..core import Message, MessageRole, get_logger
from ..utils import ContextTextBuilder

logger = get_logger(__name__)


class OpenAIAdapter(BaseAdapter):
    """
    OpenAI 对话系统适配器
    
    支持标准的 OpenAI Chat Completions API 格式。
    
    v3.2 更新：
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
        enhanced_context = await self.inject_context(user_input, context)
        
        messages = []
        
        enhanced_system_prompt = enhanced_context.get_enhanced_system_prompt()
        if enhanced_system_prompt:
            messages.append({
                'role': 'system',
                'content': enhanced_system_prompt
            })
        
        for msg in enhanced_context.messages:
            messages.append({
                'role': msg.role,
                'content': msg.content
            })
        
        messages.append({
            'role': 'user',
            'content': user_input
        })
        
        response_content = await self._call_llm(messages, **kwargs)
        
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
        def messages_to_prompt(msgs: List[Dict[str, str]]) -> str:
            parts = []
            for msg in msgs:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                parts.append(f"{role}: {content}")
            return "\n".join(parts)
        
        prompt = messages_to_prompt(messages)
        
        if self.llm_client:
            try:
                _, response = self.llm_client.generate(prompt)
                return response
            except Exception as e:
                logger.warning(f"LLM call failed: {e}, using fallback")
        
        if self.engine and self.engine.llm_client:
            try:
                _, response = self.engine.llm_client.generate(prompt)
                return response
            except Exception as e:
                logger.warning(f"Engine LLM call failed: {e}, using fallback")
        
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
        
        if message.images:
            result['images'] = message.images
        
        return result


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
        enhanced_context = await self.inject_context(user_input, context)
        
        langchain_context = self._build_langchain_context(enhanced_context)
        
        response_content = f"LangChain 处理: {user_input}"
        
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
        if isinstance(external_message, str):
            return DialogMessage(
                role='user',
                content=external_message,
                metadata={}
            )
        
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
        return message.content
    
    def _build_langchain_context(self, context: DialogContext) -> str:
        """
        构建 LangChain 兼容的上下文字符串
        
        使用 ContextTextBuilder 统一格式化。
        
        Args:
            context: 对话上下文
            
        Returns:
            上下文字符串
        """
        parts = []
        
        if context.system_prompt:
            parts.append(f"System: {context.system_prompt}")
        
        if context.messages:
            messages = [
                Message(
                    role=MessageRole(msg.role),
                    content=msg.content,
                    timestamp=msg.timestamp
                )
                for msg in context.messages
            ]
            parts.append(ContextTextBuilder.build_messages_text(messages, format_style="langchain"))
        
        return "\n".join(parts)


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
        if self.processor:
            result = self.processor(user_input, context, **kwargs)
            if hasattr(result, '__await__'):
                result = await result
            return result
        
        enhanced_context = await self.inject_context(user_input, context)
        
        response_content = f"Custom 处理: {user_input}"
        
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
        
        return message.to_dict()
