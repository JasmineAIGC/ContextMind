"""
DST 模式的 Agent 实现

基于 google-adk，使用 Qwen API（OpenAI 兼容接口）

Version: v0.4.1

## 核心思路

Qwen API 是 OpenAI 兼容接口，可以直接配置给 google-adk 的 OpenAI 模型！
通过设置 base_url，ADK 可以调用 Qwen API，获得 ADK 的完整功能。
"""

from typing import Dict, List, Optional
from google.adk import agents
from utils.adk_config import create_qwen_model, QwenADKConfig
from utils.logger import get_logger

logger = get_logger(__name__)


class DSTAgent:
    """DST 模式专用的 Agent
    
    基于 google.adk.agents.Agent，使用 Qwen API
    """
    
    def __init__(self, config: Optional[QwenADKConfig] = None):
        """初始化 DST Agent
        
        Args:
            config: Qwen 配置，默认从环境变量加载
        """
        self.config = config or QwenADKConfig.from_env()
        
        # 创建 ADK 的 OpenAI 模型（指向 Qwen API）
        self.model = create_qwen_model(self.config)
        
        # 创建 ADK Agent
        self.agent = agents.Agent(
            model=self.model,
            name="dst_agent",
            instruction="You are a dialog state tracking assistant. Extract slot values from conversations accurately."
        )
        
        logger.info(f"[DST Agent] 初始化成功（基于 google-adk），模型: {self.config.model}")
    
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
            # 构建 prompt
            prompt = self._build_prompt(messages)
            
            # 使用 ADK Agent
            result = await self.agent.run_async(prompt)
            
            # 提取内容
            if hasattr(result, 'content'):
                return result.content
            return str(result)
            
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
            prompt = self._build_prompt(messages)
            result = self.agent.run(prompt)
            
            if hasattr(result, 'content'):
                return result.content
            return str(result)
            
        except Exception as e:
            logger.error(f"DST Agent 调用失败: {e}")
            raise
    
    def _build_prompt(self, messages: List[Dict[str, str]]) -> str:
        """将消息列表转换为 prompt
        
        Args:
            messages: 消息列表
            
        Returns:
            组合后的 prompt
        """
        parts = []
        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            if role == 'system':
                parts.append(f"System: {content}")
            elif role == 'user':
                parts.append(f"User: {content}")
            elif role == 'assistant':
                parts.append(f"Assistant: {content}")
        return '\n\n'.join(parts)


# 向后兼容
DSTConfig = QwenADKConfig
