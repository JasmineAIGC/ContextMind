"""
ADK OpenAI Model Adapter

基于 google-adk 的 BaseLlm 实现 OpenAI 兼容模型（如 Qwen）
这样可以统一使用 ADK 的接口，同时支持 OpenAI 兼容的 API。

Version: v0.4.1
"""

from typing import AsyncGenerator, Optional, List, Dict, Any
from google.adk.models import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from openai import AsyncOpenAI, OpenAI
from pydantic import Field, PrivateAttr
from utils.logger import get_logger

logger = get_logger(__name__)


class OpenAILlm(BaseLlm):
    """
    ADK 兼容的 OpenAI LLM 实现
    
    继承自 google.adk.models.BaseLlm，使用 OpenAI SDK 作为底层实现。
    这样可以在使用 Qwen 等 OpenAI 兼容 API 的同时，享受 ADK 的统一接口。
    
    特性:
    - 完全兼容 ADK 的 BaseLlm 接口
    - 支持异步调用
    - 支持流式输出（可选）
    - 内部使用 openai SDK
    """
    
    # Pydantic fields
    api_key: str = Field(description="API 密钥")
    base_url: str = Field(description="API 基础 URL")
    temperature: float = Field(default=0.7, description="温度参数")
    max_tokens: int = Field(default=8192, description="最大 token 数")
    
    # Private attributes (不会被 Pydantic 序列化)
    _async_client: Any = PrivateAttr(default=None)
    _sync_client: Any = PrivateAttr(default=None)
    
    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        **kwargs
    ):
        """
        初始化 OpenAI LLM
        
        Args:
            model: 模型名称（如 "Qwen2.5-7B-Instruct"）
            api_key: API 密钥
            base_url: API 基础 URL
            temperature: 温度参数，默认 0.7
            max_tokens: 最大 token 数，默认 8192
            **kwargs: 其他参数
        """
        super().__init__(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        
        # 创建 OpenAI 客户端（使用私有属性）
        self._async_client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url
        )
        
        self._sync_client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        
        logger.info(f"[ADK OpenAI LLM] 初始化成功 - model: {model}, base_url: {base_url}")
    
    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        """
        异步生成内容（ADK 标准接口）
        
        Args:
            llm_request: ADK 的 LLM 请求对象
            stream: 是否流式输出
            
        Yields:
            LlmResponse: ADK 的 LLM 响应对象
        """
        try:
            # 转换 ADK 请求为 OpenAI 格式
            messages = self._convert_request_to_openai_messages(llm_request)
            
            if stream:
                # 流式输出
                stream_response = await self._async_client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    stream=True
                )
                
                async for chunk in stream_response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield LlmResponse(
                            text=chunk.choices[0].delta.content,
                            finish_reason=chunk.choices[0].finish_reason
                        )
            else:
                # 非流式输出
                response = await self._async_client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    stream=False
                )
                
                yield LlmResponse(
                    text=response.choices[0].message.content,
                    finish_reason=response.choices[0].finish_reason
                )
                
        except Exception as e:
            logger.error(f"[ADK OpenAI LLM] 生成失败: {e}")
            raise
    
    def generate_content_sync(
        self,
        llm_request: LlmRequest,
        **kwargs
    ) -> LlmResponse:
        """
        同步生成内容（便捷方法）
        
        Args:
            llm_request: ADK 的 LLM 请求对象
            **kwargs: 其他参数
            
        Returns:
            LlmResponse: ADK 的 LLM 响应对象
        """
        try:
            # 转换 ADK 请求为 OpenAI 格式
            messages = self._convert_request_to_openai_messages(llm_request)
            
            response = self._sync_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                **kwargs
            )
            
            return LlmResponse(
                text=response.choices[0].message.content,
                finish_reason=response.choices[0].finish_reason
            )
            
        except Exception as e:
            logger.error(f"[ADK OpenAI LLM] 同步生成失败: {e}")
            raise
    
    def _convert_request_to_openai_messages(self, llm_request: LlmRequest) -> List[Dict[str, str]]:
        """
        转换 ADK LlmRequest 为 OpenAI messages 格式
        
        Args:
            llm_request: ADK 的 LLM 请求对象
            
        Returns:
            OpenAI 格式的消息列表
        """
        messages = []
        
        # 添加系统消息（如果有）
        if hasattr(llm_request, 'system_instruction') and llm_request.system_instruction:
            messages.append({
                "role": "system",
                "content": llm_request.system_instruction
            })
        
        # 添加用户消息（主要内容）
        if hasattr(llm_request, 'prompt') and llm_request.prompt:
            messages.append({
                "role": "user",
                "content": llm_request.prompt
            })
        elif hasattr(llm_request, 'messages') and llm_request.messages:
            # 如果请求中包含完整的消息列表
            for msg in llm_request.messages:
                if isinstance(msg, dict):
                    messages.append(msg)
                elif hasattr(msg, 'role') and hasattr(msg, 'content'):
                    messages.append({
                        "role": msg.role,
                        "content": msg.content
                    })
        
        return messages
    
    async def chat_async(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        **kwargs
    ) -> str:
        """
        便捷的异步聊天方法（兼容旧接口）
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            **kwargs: 其他参数
            
        Returns:
            LLM 响应文本
        """
        try:
            response = await self._async_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                max_tokens=self.max_tokens,
                **kwargs
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"[ADK OpenAI LLM] 聊天失败: {e}")
            raise
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        **kwargs
    ) -> str:
        """
        便捷的同步聊天方法（兼容旧接口）
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            **kwargs: 其他参数
            
        Returns:
            LLM 响应文本
        """
        try:
            response = self._sync_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                max_tokens=self.max_tokens,
                **kwargs
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"[ADK OpenAI LLM] 聊天失败: {e}")
            raise


def create_openai_llm(
    model: str,
    api_key: str,
    base_url: str,
    **kwargs
) -> OpenAILlm:
    """
    创建 OpenAI LLM 实例（工厂方法）
    
    Args:
        model: 模型名称
        api_key: API 密钥
        base_url: API 基础 URL
        **kwargs: 其他参数
        
    Returns:
        OpenAILlm 实例
    """
    return OpenAILlm(
        model=model,
        api_key=api_key,
        base_url=base_url,
        **kwargs
    )


# 便捷导出
__all__ = ["OpenAILlm", "create_openai_llm"]
