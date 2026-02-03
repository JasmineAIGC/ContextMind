"""
Evolution 模式的 Agent 实现

使用 openai SDK 调用 Qwen API，同时使用 google-adk 的 Session 和 Memory 服务。

Version: v0.4.1

## 架构说明

- LLM 调用: 使用 openai SDK（Qwen API 兼容）
- Session 管理: 使用 google-adk.sessions
- Memory 管理: 使用 google-adk.memory
"""

from typing import Dict, List, Optional
from openai import AsyncOpenAI, OpenAI
from utils.adk_config import create_qwen_config, QwenADKConfig
from utils.logger import get_logger

logger = get_logger(__name__)


class EvolutionAgent:
    """Evolution 模式专用的 Agent
    
    LLM 层使用 openai SDK，Session/Memory 使用 google-adk
    """
    
    def __init__(self, config: Optional[QwenADKConfig] = None):
        """初始化 Evolution Agent
        
        Args:
            config: Qwen 配置，默认从环境变量加载
        """
        self.config = config or create_qwen_config()
        
        # 使用 openai SDK 创建客户端（Qwen API 兼容）
        self.async_client = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url
        )
        
        self.sync_client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url
        )
        
        logger.info(f"[Evolution Agent] 初始化成功，模型: {self.config.model}")
    
    async def chat_async(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        **kwargs
    ) -> str:
        """异步聊天调用
        
        Args:
            messages: 消息列表 [{"role": "user/assistant/system", "content": "..."}]
            temperature: 温度参数
            **kwargs: 其他参数
            
        Returns:
            LLM 响应文本
        """
        try:
            # 使用 openai SDK 调用 Qwen API
            response = await self.async_client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=temperature or self.config.temperature,
                max_tokens=self.config.max_tokens,
                **kwargs
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Evolution Agent 调用失败: {e}")
            raise
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        **kwargs
    ) -> str:
        """同步聊天调用
        
        Args:
            messages: 消息列表 [{"role": "user/assistant/system", "content": "..."}]
            temperature: 温度参数
            **kwargs: 其他参数
            
        Returns:
            LLM 响应文本
        """
        try:
            # 使用 openai SDK 调用 Qwen API
            response = self.sync_client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=temperature or self.config.temperature,
                max_tokens=self.config.max_tokens,
                **kwargs
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Evolution Agent 调用失败: {e}")
            raise
    
    async def generate_async(self, prompt: str, **kwargs) -> tuple:
        """异步生成
        
        Args:
            prompt: 提示词
            **kwargs: 其他参数
            
        Returns:
            元组 (reasoning, response)，reasoning 为 None
        """
        response = await self.chat_async([{"role": "user", "content": prompt}], **kwargs)
        return (None, response)  # 返回元组以保持兼容性
    
    def generate(self, prompt: str, **kwargs) -> tuple:
        """同步生成
        
        Args:
            prompt: 提示词
            **kwargs: 其他参数
            
        Returns:
            元组 (reasoning, response)，reasoning 为 None（ADK 不提供推理过程）
        """
        response = self.chat([{"role": "user", "content": prompt}], **kwargs)
        return (None, response)  # 返回元组以保持兼容性


# 向后兼容
EvolutionConfig = QwenADKConfig
