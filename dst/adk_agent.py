"""
DST 模式的 LLM Agent 实现

使用 Qwen API（OpenAI 兼容接口）。
DST 模式专注于对话状态追踪，槽位提取等自研逻辑。

版本: v0.4.1

## 架构说明

- **LLM 层**: 使用 openai 包调用 Qwen API（OpenAI 兼容）
- **Agent 层**: 轻量封装，提供统一接口
- **自研层**: DST 槽位提取、Prompt 工程、状态追踪算法

注：未使用 google-adk.agents.Agent，因为：
1. 我们的 Agent 更简单，只是 LLM 调用的封装
2. google-adk.agents 设计更复杂，适合多 Agent 编排
3. 保持代码简洁可维护

参见: docs/ADK_INTEGRATION_ANALYSIS.md
"""

from typing import Dict, List, Optional

from utils.qwen_client import QwenClient, QwenConfig
from utils.logger import get_logger

logger = get_logger(__name__)


class DSTAgent:
    """DST 模式专用的 LLM Agent
    
    使用 Qwen API 进行槽位提取和对话状态追踪。
    """
    
    def __init__(self, config: Optional[QwenConfig] = None):
        """初始化 DST Agent
        
        Args:
            config: Qwen 配置，默认从环境变量加载
        """
        self.client = QwenClient(config)
        logger.info(f"[DST Agent] 初始化成功")
    
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
            return self.client.chat(messages, temperature, **kwargs)
        except Exception as e:
            logger.error(f"DST Agent 调用失败: {e}")
            raise
