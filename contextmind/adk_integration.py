"""
ContextMind ADK 集成层

使用 Google ADK-Python 提供统一的 LLM 和 Agent 接口。
版本: v0.4.1
"""

from __future__ import annotations

import os
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ADK imports
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
class LLMConfig:
    """LLM 配置"""
    model: str = "gemini-2.0-flash-exp"
    temperature: float = 0.7
    max_tokens: int = 8192
    
    @classmethod
    def from_env(cls) -> "LLMConfig":
        """从环境变量加载配置"""
        model = os.getenv("MODEL", "gemini-2.0-flash-exp")
        temperature = float(os.getenv("TEMPERATURE", "0.7"))
        max_tokens = int(os.getenv("MAX_TOKENS", "8192"))
        
        return cls(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens
        )


class ADKLLMClient:
    """ADK LLM 客户端封装
    
    提供统一的 LLM 调用接口，支持多种模型提供商。
    """
    
    def __init__(self, config: Optional[LLMConfig] = None):
        """初始化 LLM 客户端"""
        if not ADK_AVAILABLE:
            raise RuntimeError("google-adk 未安装。请运行: pip install google-adk litellm")
        
        self.config = config or LLMConfig.from_env()
        self.model = self._create_model()
        
        logger.info(f"[ADK LLM] 初始化成功，模型: {self.config.model}")
    
    def _create_model(self):
        """创建模型实例"""
        model_name = self.config.model
        
        # 如果是 Gemini 模型，直接使用
        if model_name.startswith("gemini"):
            return model_name
        
        # 其他模型通过 LiteLLM
        return LiteLlm(model_name)
    
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
        # 创建临时 Agent 进行对话
        temp_agent = Agent(
            model=self.model,
            name="temp_llm_client"
        )
        
        # 转换消息格式
        prompt = self._convert_messages_to_prompt(messages)
        
        # 调用 Agent
        try:
            response = await temp_agent.run(prompt)
            return response.text if hasattr(response, 'text') else str(response)
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            raise
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        **kwargs
    ) -> str:
        """同步聊天调用（简单封装异步版本）"""
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


class ContextMindAgent:
    """ContextMind Agent 封装
    
    集成 ADK Agent 与 ContextMind 的上下文工程算法。
    """
    
    def __init__(
        self,
        app_name: str,
        user_id: str,
        model: Optional[str] = None,
        tools: Optional[List[Callable]] = None
    ):
        """初始化 ContextMind Agent
        
        Args:
            app_name: 应用名称
            user_id: 用户 ID
            model: 模型名称
            tools: 工具列表
        """
        if not ADK_AVAILABLE:
            raise RuntimeError("google-adk 未安装")
        
        self.app_name = app_name
        self.user_id = user_id
        
        config = LLMConfig.from_env()
        model_name = model or config.model
        
        # 创建模型
        if model_name.startswith("gemini"):
            agent_model = model_name
        else:
            agent_model = LiteLlm(model_name)
        
        # 创建 ADK Agent
        self.agent = Agent(
            model=agent_model,
            name=f"{app_name}_{user_id}_agent",
            tools=tools or []
        )
        
        logger.info(f"[ContextMind Agent] 初始化成功: {app_name}/{user_id}")
    
    async def run(self, input_text: str, **kwargs) -> Any:
        """运行 Agent"""
        return await self.agent.run(input_text, **kwargs)


# 向后兼容的别名
SimpleLLMClient = ADKLLMClient
UnifiedLLMClient = ADKLLMClient
