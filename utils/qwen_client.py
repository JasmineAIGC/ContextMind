"""
Qwen LLM 客户端

使用 OpenAI 兼容接口调用 Qwen 模型。
配置从 .env 文件读取：QWEN3_API_KEY, QWEN3_BASE_URL, QWEN3_MODEL

版本: v0.4.1

## 为什么使用 openai 包而不是 google-adk？

Qwen API 提供 OpenAI 兼容接口，使用 openai Python 包是最直接的调用方式。
google-adk 主要支持 Google Gemini 模型，不提供 OpenAI 兼容接口。

参见: docs/ADK_INTEGRATION_ANALYSIS.md
"""

import os
from typing import Dict, List, Optional
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from openai import AsyncOpenAI, OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    AsyncOpenAI = None
    OpenAI = None
    print("警告: 未安装 openai。请运行: pip install openai")

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class QwenConfig:
    """Qwen 客户端配置"""
    api_key: str
    base_url: str
    model: str
    temperature: float = 0.7
    max_tokens: int = 8192
    top_k: int = 20
    
    @classmethod
    def from_env(cls) -> "QwenConfig":
        """从环境变量加载配置"""
        api_key = os.getenv("QWEN3_API_KEY", "")
        base_url = os.getenv("QWEN3_BASE_URL", "")
        model = os.getenv("QWEN3_MODEL", "Qwen2.5-7B-Instruct")
        temperature = float(os.getenv("QWEN3_TEMPERATURE", os.getenv("TEMPERATURE", "0.7")))
        max_tokens = int(os.getenv("QWEN3_MAX_TOKENS", "8192"))
        top_k = int(os.getenv("QWEN3_TOP_K", "20"))
        
        if not api_key or not base_url:
            raise ValueError(
                "请在 .env 文件中配置 QWEN3_API_KEY 和 QWEN3_BASE_URL\n"
                "例如:\n"
                "QWEN3_API_KEY=sk-xxx\n"
                "QWEN3_BASE_URL=http://your-endpoint/v1"
            )
        
        return cls(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            top_k=top_k
        )


class QwenClient:
    """Qwen LLM 客户端
    
    使用 OpenAI 兼容接口调用 Qwen 模型。
    支持同步和异步调用。
    """
    
    def __init__(self, config: Optional[QwenConfig] = None):
        """初始化 Qwen 客户端"""
        if not OPENAI_AVAILABLE:
            raise RuntimeError("openai 未安装。请运行: pip install openai")
        
        self.config = config or QwenConfig.from_env()
        
        # 创建异步客户端
        self.async_client = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url
        )
        
        # 创建同步客户端
        self.sync_client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url
        )
        
        logger.info(f"[Qwen Client] 初始化成功，模型: {self.config.model}, endpoint: {self.config.base_url}")
    
    async def chat_async(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """异步聊天调用
        
        Args:
            messages: 消息列表 [{"role": "user/assistant/system", "content": "..."}]
            temperature: 温度参数
            max_tokens: 最大token数
            **kwargs: 其他参数
            
        Returns:
            LLM 响应文本
        """
        try:
            response = await self.async_client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=temperature or self.config.temperature,
                max_tokens=max_tokens or self.config.max_tokens,
                **kwargs
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Qwen API 调用失败: {e}")
            raise
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """同步聊天调用
        
        Args:
            messages: 消息列表 [{"role": "user/assistant/system", "content": "..."}]
            temperature: 温度参数
            max_tokens: 最大token数
            **kwargs: 其他参数
            
        Returns:
            LLM 响应文本
        """
        try:
            response = self.sync_client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=temperature or self.config.temperature,
                max_tokens=max_tokens or self.config.max_tokens,
                **kwargs
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Qwen API 调用失败: {e}")
            raise
    
    async def generate_async(self, prompt: str, **kwargs) -> str:
        """异步生成"""
        return await self.chat_async([{"role": "user", "content": prompt}], **kwargs)
    
    def generate(self, prompt: str, **kwargs) -> str:
        """同步生成"""
        return self.chat([{"role": "user", "content": prompt}], **kwargs)
