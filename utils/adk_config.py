"""
Google ADK 配置模块

配置 Qwen API（OpenAI 兼容接口）

注意：google-adk 主要支持 Gemini，不直接支持 OpenAI。
我们使用 openai SDK 调用 Qwen API，然后在 Agent 层手动集成。

Version: v0.4.1
"""

import os
from dataclasses import dataclass
from typing import Optional


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


def create_qwen_config(config: Optional[QwenADKConfig] = None) -> QwenADKConfig:
    """
    创建 Qwen 配置
    
    注意：由于 google-adk 不直接支持 OpenAI 兼容接口，
    我们保持使用 openai SDK，但可以在 Agent 层使用 ADK 的其他功能
    （如 Session, Memory）。
    
    Args:
        config: Qwen 配置，如果为 None 则从环境变量加载
        
    Returns:
        Qwen 配置对象
    """
    if config is None:
        config = QwenADKConfig.from_env()
    
    return config


# 便捷导出
__all__ = ["QwenADKConfig", "create_qwen_config"]
