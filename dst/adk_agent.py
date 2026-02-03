"""
DST 模式的 Agent 实现

基于 google-adk 的 BaseLlm，使用自定义 OpenAILlm 适配器调用 Qwen API。

Version: v0.4.1

## 架构说明

- LLM 调用: 基于 google-adk.models.BaseLlm（通过 OpenAILlm 适配器）
- Session 管理: 可以使用 google-adk.sessions（如果需要）
- 优势: 统一的 ADK 接口，易于切换模型
"""

from typing import Dict, List, Optional
from utils.adk_config import create_qwen_config, QwenADKConfig
from utils.adk_openai_model import OpenAILlm
from utils.logger import get_logger

logger = get_logger(__name__)


class DSTAgent:
    """DST 模式专用的 Agent
    
    基于 google-adk 的 BaseLlm，使用 OpenAILlm 适配器
    """
    
    def __init__(self, config: Optional[QwenADKConfig] = None):
        """初始化 DST Agent
        
        Args:
            config: Qwen 配置，默认从环境变量加载
        """
        self.config = config or create_qwen_config()
        
        # 使用 ADK 兼容的 OpenAILlm（基于 BaseLlm）
        self.llm = OpenAILlm(
            model=self.config.model,
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens
        )
        
        logger.info(f"[DST Agent] 初始化成功（基于 ADK），模型: {self.config.model}")
    
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
            # 使用 ADK 兼容的 OpenAILlm
            return await self.llm.chat_async(messages, temperature, **kwargs)
            
        except Exception as e:
            logger.error(f"DST Agent 调用失败: {e}")
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
            # 使用 ADK 兼容的 OpenAILlm
            return self.llm.chat(messages, temperature, **kwargs)
            
        except Exception as e:
            logger.error(f"DST Agent 调用失败: {e}")
            raise


# 向后兼容
DSTConfig = QwenADKConfig
