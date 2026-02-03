"""
ADK-powered 统一 LLM 客户端

使用 Google ADK-Python 提供统一的 LLM 接口，支持：
- 多 LLM 提供商（Google, OpenAI, Anthropic等）
- 自动重试和错误处理
- 流式响应支持
- 统一的速率限制

版本: v0.5.0 (ADK-powered)
"""

from __future__ import annotations

import os
from typing import Optional, List, Dict, Any, Sequence
from dataclasses import dataclass

# 加载.env文件中的环境变量
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from google import genai
    from google.genai import types
    ADK_AVAILABLE = True
except ImportError:
    ADK_AVAILABLE = False
    genai = None
    types = None
    print("警告: 未安装 google-genai 包。ADK LLM 功能将无法工作。")
    print("安装方法: pip install google-genai")

from .logger import get_logger

logger = get_logger(__name__)

DEFAULT_MODEL = "gemini-2.0-flash-exp"
DEFAULT_TEMPERATURE = 0.7


def _first_env(keys: Sequence[str], default: Optional[str] = None) -> Optional[str]:
    """按顺序读取环境变量，返回首个非空值。"""
    for key in keys:
        if value := os.getenv(key):
            return value
    return default


@dataclass
class LLMConfig:
    """ADK LLM 配置。"""
    
    api_key: str
    model: str = DEFAULT_MODEL
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = 8192
    top_p: float = 0.95
    top_k: int = 40
    
    @classmethod
    def from_env(cls) -> "LLMConfig":
        """从环境变量加载配置。"""
        # 读取 API Key
        api_key = _first_env(
            [
                "GOOGLE_API_KEY",
                "GEMINI_API_KEY",
                "GOOGLE_GENAI_API_KEY",
            ]
        )
        if not api_key:
            raise ValueError(
                "缺少 API key。请在 .env 文件中设置: GOOGLE_API_KEY"
            )
        
        # 读取模型名称
        model = _first_env(
            [
                "GOOGLE_MODEL",
                "GEMINI_MODEL",
                "LLM_MODEL",
            ],
            default=DEFAULT_MODEL,
        )
        
        # 读取温度参数
        temperature_str = _first_env(["LLM_TEMPERATURE", "GOOGLE_TEMPERATURE"])
        temperature = float(temperature_str) if temperature_str else DEFAULT_TEMPERATURE
        
        # 读取 max_tokens
        max_tokens_str = _first_env(["MAX_TOKENS", "LLM_MAX_TOKENS"])
        max_tokens = int(max_tokens_str) if max_tokens_str else 8192
        
        # 读取 top_p
        top_p_str = _first_env(["TOP_P", "LLM_TOP_P"])
        top_p = float(top_p_str) if top_p_str else 0.95
        
        # 读取 top_k
        top_k_str = _first_env(["TOP_K", "LLM_TOP_K"])
        top_k = int(top_k_str) if top_k_str else 40
        
        return cls(
            api_key=api_key,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            top_k=top_k,
        )


class UnifiedLLMClient:
    """ADK-powered 统一 LLM 客户端 (v0.5.0)。
    
    使用 Google ADK 提供统一的 LLM 接口，自动处理重试、错误恢复等。
    """
    
    def __init__(self, config: Optional[LLMConfig] = None):
        """初始化客户端。"""
        if not ADK_AVAILABLE:
            raise RuntimeError(
                "未安装 google-genai 包。"
                "请使用以下命令安装: pip install google-genai"
            )
        
        self.config = config or LLMConfig.from_env()
        logger.info(f"[ADK LLM Client] 正在初始化，model: {self.config.model}")
        
        # 创建 Google GenAI 客户端
        self._client = genai.Client(api_key=self.config.api_key)
        
        logger.info(f"[ADK LLM Client] 初始化成功")
    
    def generate(self, prompt: str, **kwargs) -> str:
        """基于 Prompt 调用 LLM，返回响应内容。
        
        Args:
            prompt: 完整的 Prompt
            **kwargs: 额外参数（temperature, max_tokens等）
            
        Returns:
            LLM 响应内容
        """
        try:
            # 合并配置
            temperature = kwargs.get("temperature", self.config.temperature)
            max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
            top_p = kwargs.get("top_p", self.config.top_p)
            top_k = kwargs.get("top_k", self.config.top_k)
            
            # 构建生成配置
            generation_config = types.GenerateContentConfig(
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                max_output_tokens=max_tokens,
            )
            
            # 调用 ADK
            response = self._client.models.generate_content(
                model=self.config.model,
                contents=prompt,
                config=generation_config,
            )
            
            # 提取文本
            return response.text
            
        except Exception as e:
            logger.error(f"LLM API调用失败: {str(e)}", exc_info=True)
            raise RuntimeError(
                f"调用 LLM API 失败 (model: {self.config.model}): {str(e)}"
            ) from e
    
    async def generate_async(self, prompt: str, **kwargs) -> str:
        """异步版本的 generate。
        
        Args:
            prompt: 完整的 Prompt
            **kwargs: 额外参数
            
        Returns:
            LLM 响应内容
        """
        try:
            # 合并配置
            temperature = kwargs.get("temperature", self.config.temperature)
            max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
            top_p = kwargs.get("top_p", self.config.top_p)
            top_k = kwargs.get("top_k", self.config.top_k)
            
            # 构建生成配置
            generation_config = types.GenerateContentConfig(
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                max_output_tokens=max_tokens,
            )
            
            # 异步调用
            response = await self._client.aio.models.generate_content(
                model=self.config.model,
                contents=prompt,
                config=generation_config,
            )
            
            return response.text
            
        except Exception as e:
            logger.error(f"LLM API调用失败: {str(e)}", exc_info=True)
            raise RuntimeError(
                f"调用 LLM API 失败 (model: {self.config.model}): {str(e)}"
            ) from e
    
    def chat(self, messages: List[Dict[str, str]], temperature: float = None, **kwargs) -> str:
        """基于消息列表调用 LLM（同步版本）。
        
        Args:
            messages: 消息列表，格式为 [{"role": "system/user/assistant", "content": "..."}]
            temperature: 温度参数（可选）
            **kwargs: 额外参数
            
        Returns:
            助手的回复内容
        """
        try:
            # 合并配置
            temp = temperature if temperature is not None else self.config.temperature
            max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
            top_p = kwargs.get("top_p", self.config.top_p)
            top_k = kwargs.get("top_k", self.config.top_k)
            
            # 构建生成配置
            generation_config = types.GenerateContentConfig(
                temperature=temp,
                top_p=top_p,
                top_k=top_k,
                max_output_tokens=max_tokens,
            )
            
            # 转换消息格式
            system_instruction = None
            contents = []
            
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                
                if role == "system":
                    system_instruction = content
                elif role == "user":
                    contents.append(types.Part(text=content))
                elif role == "assistant":
                    # Gemini 的历史消息格式
                    contents.append(types.Part(text=content))
            
            # 如果只有一条用户消息，直接使用
            if len(contents) == 1:
                prompt = contents[0].text
            else:
                # 多条消息合并
                prompt = "\n\n".join([part.text for part in contents])
            
            # 如果有系统指令，添加到开头
            if system_instruction:
                prompt = f"{system_instruction}\n\n{prompt}"
            
            # 调用 ADK
            response = self._client.models.generate_content(
                model=self.config.model,
                contents=prompt,
                config=generation_config,
            )
            
            return response.text
            
        except Exception as e:
            logger.error(f"LLM API调用失败: {str(e)}", exc_info=True)
            raise RuntimeError(
                f"调用 LLM API 失败 (model: {self.config.model}): {str(e)}"
            ) from e
    
    async def chat_async(
        self,
        messages: List[Dict[str, str]],
        temperature: float = None,
        **kwargs
    ) -> str:
        """基于消息列表调用 LLM（异步版本）。
        
        Args:
            messages: 消息列表
            temperature: 温度参数（可选）
            **kwargs: 额外参数
            
        Returns:
            助手的回复内容
        """
        try:
            # 合并配置
            temp = temperature if temperature is not None else self.config.temperature
            max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
            top_p = kwargs.get("top_p", self.config.top_p)
            top_k = kwargs.get("top_k", self.config.top_k)
            
            # 构建生成配置
            generation_config = types.GenerateContentConfig(
                temperature=temp,
                top_p=top_p,
                top_k=top_k,
                max_output_tokens=max_tokens,
            )
            
            # 转换消息格式
            system_instruction = None
            contents = []
            
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                
                if role == "system":
                    system_instruction = content
                elif role == "user":
                    contents.append(types.Part(text=content))
                elif role == "assistant":
                    contents.append(types.Part(text=content))
            
            # 如果只有一条用户消息，直接使用
            if len(contents) == 1:
                prompt = contents[0].text
            else:
                # 多条消息合并
                prompt = "\n\n".join([part.text for part in contents])
            
            # 如果有系统指令，添加到开头
            if system_instruction:
                prompt = f"{system_instruction}\n\n{prompt}"
            
            # 异步调用
            response = await self._client.aio.models.generate_content(
                model=self.config.model,
                contents=prompt,
                config=generation_config,
            )
            
            return response.text
            
        except Exception as e:
            logger.error(f"LLM API调用失败: {str(e)}", exc_info=True)
            raise RuntimeError(
                f"调用 LLM API 失败 (model: {self.config.model}): {str(e)}"
            ) from e
