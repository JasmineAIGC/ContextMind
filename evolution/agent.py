"""
Evolution 模式的 ADK Agent 实现

直接使用 google-adk，不经过封装层。
Evolution 模式专注于基于进化的上下文工程和记忆优化。

版本: v0.4.1
"""

import os
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 直接使用 ADK
try:
    from google.adk.agents import Agent
    from google.adk.models.lite_llm import LiteLlm
    ADK_AVAILABLE = True
except ImportError:
    ADK_AVAILABLE = False
    Agent = None
    LiteLlm = None
    print("警告: 未安装 google-adk。请运行: pip install google-adk litellm")

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class EvolutionConfig:
    """Evolution 模式配置"""
    model: str = "gemini-2.0-flash-exp"
    temperature: float = 0.7
    max_tokens: int = 8192
    
    @classmethod
    def from_env(cls) -> "EvolutionConfig":
        """从环境变量加载配置"""
        model = os.getenv("MODEL", "gemini-2.0-flash-exp")
        temperature = float(os.getenv("TEMPERATURE", "0.7"))
        max_tokens = int(os.getenv("MAX_TOKENS", "8192"))
        
        return cls(model=model, temperature=temperature, max_tokens=max_tokens)


class EvolutionAgent:
    """Evolution 模式专用的 ADK Agent
    
    直接使用 google.adk.agents.Agent，用于基于进化的上下文工程和记忆优化。
    """
    
    def __init__(self, config: Optional[EvolutionConfig] = None):
        """初始化 Evolution Agent"""
        if not ADK_AVAILABLE:
            raise RuntimeError("google-adk 未安装。请运行: pip install google-adk litellm")
        
        self.config = config or EvolutionConfig.from_env()
        
        # 创建模型
        if self.config.model.startswith("gemini"):
            model = self.config.model
        else:
            model = LiteLlm(self.config.model)
        
        # 直接创建 ADK Agent
        self.agent = Agent(
            model=model,
            name="evolution_agent"
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
        # 转换消息为 prompt
        prompt = self._convert_messages_to_prompt(messages)
        
        # 直接调用 ADK Agent
        try:
            response = await self.agent.run(prompt)
            return response.text if hasattr(response, 'text') else str(response)
        except Exception as e:
            logger.error(f"Evolution Agent 调用失败: {e}")
            raise
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        **kwargs
    ) -> str:
        """同步聊天调用"""
        import asyncio
        return asyncio.run(self.chat_async(messages, temperature, **kwargs))
    
    async def generate_async(self, prompt: str, **kwargs) -> str:
        """异步生成"""
        return await self.chat_async([{"role": "user", "content": prompt}], **kwargs)
    
    def generate(self, prompt: str, **kwargs) -> str:
        """同步生成"""
        import asyncio
        return asyncio.run(self.generate_async(prompt, **kwargs))
    
    def _convert_messages_to_prompt(self, messages: List[Dict[str, str]]) -> str:
        """将消息列表转换为 prompt"""
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "system":
                parts.append(f"System: {content}")
            elif role == "user":
                parts.append(f"User: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
        
        return "\n\n".join(parts)
