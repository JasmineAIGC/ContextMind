"""
Google ADK 配置模块

配置 google-adk 使用 Qwen API（通过 OpenAI 兼容接口）

Version: v0.4.1
"""

import os
from dataclasses import dataclass
from typing import Optional
from google.adk.models.openai import OpenAI


@dataclass
class QwenADKConfig:
    """Qwen API 配置（用于 ADK）"""
    api_key: str
    base_url: str
    model: str = "Qwen2.5-7B-Instruct"
    max_tokens: int = 8192
    temperature: float = 0.7

    @classmethod
    def from_env(cls) -> "QwenADKConfig":
        """从环境变量加载配置"""
        return cls(
            api_key=os.getenv("QWEN3_API_KEY", ""),
            base_url=os.getenv("QWEN3_BASE_URL", ""),
            model=os.getenv("QWEN3_MODEL", "Qwen2.5-7B-Instruct"),
            max_tokens=int(os.getenv("QWEN3_MAX_TOKENS", "8192")),
            temperature=float(os.getenv("QWEN3_TEMPERATURE", "0.7"))
        )


def create_qwen_model(config: Optional[QwenADKConfig] = None) -> OpenAI:
    """
    创建配置为 Qwen API 的 ADK OpenAI 模型
    
    这是关键：Qwen API 是 OpenAI 兼容的，所以可以直接使用
    google.adk.models.openai.OpenAI，只需要指定 base_url 到 Qwen API。
    
    Args:
        config: Qwen 配置，如果为 None 则从环境变量加载
        
    Returns:
        配置好的 ADK OpenAI 模型（实际调用 Qwen API）
        
    Example:
        >>> model = create_qwen_model()
        >>> # 这个 model 可以直接用于 google.adk.agents.Agent
    """
    if config is None:
        config = QwenADKConfig.from_env()
    
    # 使用 ADK 的 OpenAI 模型，但指向 Qwen API
    return OpenAI(
        model=config.model,
        api_key=config.api_key,
        base_url=config.base_url,
        # 其他参数可以在调用时指定
    )


# 便捷导出
__all__ = ["QwenADKConfig", "create_qwen_model"]
