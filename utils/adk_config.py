"""
Google ADK 配置模块

配置基于 google-adk BaseLlm 的 OpenAI 兼容模型（如 Qwen API）

架构说明：
- 使用 google-adk 的 BaseLlm 作为基类
- 通过自定义 OpenAILlm 适配器支持 OpenAI 兼容接口
- 提供统一的 ADK 接口，易于切换模型提供商

Version: v0.4.1
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class QwenADKConfig:
    """Qwen API 配置（用于 ADK OpenAILlm 适配器）"""
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
    
    基于 google-adk 的设计理念，通过 OpenAILlm 适配器使用 OpenAI 兼容接口。
    
    优势：
    - 统一的 ADK BaseLlm 接口
    - 易于切换到其他 LLM 提供商（如 Gemini）
    - 保持对现有 Qwen API 的兼容
    
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
