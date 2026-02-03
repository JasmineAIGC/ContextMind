"""
Evolution 模式的 LLM Agent 实现

使用 Qwen API（OpenAI 兼容接口）。
Evolution 模式专注于基于进化的上下文工程和记忆优化。

版本: v0.4.1
"""

from typing import Dict, List, Optional

from utils.qwen_client import QwenClient, QwenConfig
from utils.logger import get_logger

logger = get_logger(__name__)


class EvolutionAgent:
    """Evolution 模式专用的 LLM Agent
    
    使用 Qwen API 进行基于进化的上下文工程和记忆优化。
    """
    
    def __init__(self, config: Optional[QwenConfig] = None):
        """初始化 Evolution Agent
        
        Args:
            config: Qwen 配置，默认从环境变量加载
        """
        self.client = QwenClient(config)
        logger.info(f"[Evolution Agent] 初始化成功")
    
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
            return await self.client.chat_async(messages, temperature, **kwargs)
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
            return self.client.chat(messages, temperature, **kwargs)
        except Exception as e:
            logger.error(f"Evolution Agent 调用失败: {e}")
            raise
    
    async def generate_async(self, prompt: str, **kwargs) -> str:
        """异步生成
        
        Args:
            prompt: 提示词
            **kwargs: 其他参数
            
        Returns:
            生成的文本
        """
        return await self.chat_async([{"role": "user", "content": prompt}], **kwargs)
    
    def generate(self, prompt: str, **kwargs) -> str:
        """同步生成
        
        Args:
            prompt: 提示词
            **kwargs: 其他参数
            
        Returns:
            生成的文本
        """
        return self.chat([{"role": "user", "content": prompt}], **kwargs)
