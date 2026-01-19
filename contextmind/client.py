"""
OpenAI 兼容模型客户端

提供适配任意 OpenAI Chat Completions 兼容模型的通用客户端封装。
支持 Qwen、DeepSeek 等多种模型。
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Optional, Sequence, Tuple

from openai import OpenAI

from .core import get_logger

logger = get_logger(__name__)

DEFAULT_MODEL = "Qwen3-32B"
DEFAULT_TEMPERATURE = 0.6


def _first_env(keys: Sequence[str], default: Optional[str] = None) -> Optional[str]:
    """按顺序读取环境变量，返回首个非空值。
    
    支持多个环境变量名，便于适配不同的部署环境（Qwen、DeepSeek、OpenAI等）。
    """
    for key in keys:
        if value := os.getenv(key):
            return value
    return default


@dataclass
class ClientConfig:
    """OpenAI 兼容端点的运行时配置。"""

    api_key: str
    model: str = DEFAULT_MODEL
    base_url: Optional[str] = None
    temperature: float = DEFAULT_TEMPERATURE
    access_key: Optional[str] = None
    top_k: int = 20
    max_tokens: int = 8192
    chat_template_kwargs: dict = None

    @classmethod
    def from_env(cls) -> "ClientConfig":
        """从环境变量加载配置。"""
        # 读取 API Key（必需）
        api_key = _first_env(
            [
                "QWEN3_API_KEY",
                "CONTEXTMIND_API_KEY",
                "LLM_API_KEY",
                "OPENAI_API_KEY",
                "DEEPSEEK_API_KEY",
                "QWEN_API_KEY",
            ]
        )
        if not api_key:
            raise ValueError(
                "Missing API key. Please set one of QWEN3_API_KEY / "
                "CONTEXTMIND_API_KEY / LLM_API_KEY / OPENAI_API_KEY / "
                "DEEPSEEK_API_KEY / QWEN_API_KEY."
            )

        # 读取 Base URL（可选）
        base_url = _first_env(
            [
                "QWEN3_BASE_URL",
                "CONTEXTMIND_BASE_URL",
                "LLM_BASE_URL",
                "OPENAI_BASE_URL",
                "DEEPSEEK_BASE_URL",
                "QWEN_BASE_URL",
            ]
        )

        # 读取模型名称（可选）
        model = _first_env(
            [
                "QWEN3_MODEL",
                "CONTEXTMIND_MODEL",
                "LLM_MODEL",
                "OPENAI_MODEL",
                "DEEPSEEK_MODEL",
                "QWEN_MODEL",
            ],
            default=DEFAULT_MODEL,
        )

        # 读取温度参数（可选）
        temperature_str = _first_env(
            [
                "CONTEXTMIND_TEMPERATURE",
                "LLM_TEMPERATURE",
                "OPENAI_TEMPERATURE",
                "DEEPSEEK_TEMPERATURE",
                "QWEN_TEMPERATURE",
            ]
        )
        temperature = (
            float(temperature_str) if temperature_str is not None else DEFAULT_TEMPERATURE
        )

        # 读取 Access Key（可选，某些网关需要）
        access_key = _first_env(
            [
                "QWEN3_ACCESS_KEY",
                "CONTEXTMIND_ACCESS_KEY",
                "LLM_ACCESS_KEY",
                "ACCESS_KEY",
                "DEEPSEEK_ACCESS_KEY",
                "QWEN_ACCESS_KEY",
            ]
        )

        # 读取 top_k 参数（可选）
        top_k_str = _first_env(["QWEN3_TOP_K", "LLM_TOP_K", "TOP_K"])
        top_k = int(top_k_str) if top_k_str else 20

        # 读取 max_tokens 参数（可选）
        max_tokens_str = _first_env(["QWEN3_MAX_TOKENS", "LLM_MAX_TOKENS", "MAX_TOKENS"])
        max_tokens = int(max_tokens_str) if max_tokens_str else 8192

        return cls(
            api_key=api_key,
            model=model,
            base_url=base_url,
            temperature=temperature,
            access_key=access_key,
            top_k=top_k,
            max_tokens=max_tokens,
        )


class Client:
    """面向多种服务的通用客户端封装。"""

    def __init__(self, config: Optional[ClientConfig] = None):
        """初始化客户端。"""
        self.config = config or ClientConfig.from_env()
        logger.info(f"Initializing client with model: {self.config.model}")

        # 构造 headers，如果需要 Access Key
        headers = {}
        if self.config.access_key:
            # 部分网关需要单独的 access key，统一放进 header
            headers["access-key"] = self.config.access_key

        # 使用标准的 OpenAI 兼容端点，不拼接 model 到 URL
        # model 将作为请求参数传递
        full_base_url = self.config.base_url

        # 创建 OpenAI 客户端
        self._client = OpenAI(
            api_key=self.config.api_key,
            base_url=full_base_url,
            default_headers=headers or None,
        )
        logger.debug(f"Client initialized with base_url: {full_base_url}")

    def generate(self, prompt: str) -> Tuple[str, str]:
        """基于单轮用户输入调用模型，返回推理与内容。
        
        注意：机器人回复时总是关闭思考过程显示，直接根据完整prompt回答。
        这确保用户看到的是最终答案，而非推理过程。
        """
        try:
            # 构造 extra_body 参数
            extra_body = {
                "top_k": self.config.top_k,
            }
            
            # 强制关闭思考过程（机器人回复不显示推理）
            # 这是ContextMind的设计原则：上下文工程处理可以思考，但最终回复必须直接
            extra_body["chat_template_kwargs"] = {"enable_thinking": False}
            
            # 如果用户在config中显式设置了chat_template_kwargs，也覆盖为关闭思考
            # 确保机器人回复始终不显示思考过程
            if self.config.chat_template_kwargs:
                logger.debug("User provided chat_template_kwargs, overriding enable_thinking to False")

            # 调用 OpenAI Chat Completions API
            response = self._client.chat.completions.create(
                model=self.config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                extra_body=extra_body,
            )
        except Exception as e:
            # 包装异常，提供更清晰的错误信息
            raise RuntimeError(
                f"Failed to call LLM API (model: {self.config.model}): {str(e)}"
            ) from e

        # 检查响应是否有效
        if not response.choices:
            raise ValueError(
                f"API returned empty choices (model: {self.config.model})"
            )

        # 提取消息内容
        choice = response.choices[0].message

        if not choice:
            raise ValueError(
                f"API returned invalid message (model: {self.config.model})"
            )

        # 提取推理链（某些模型支持，如 DeepSeek-R1）
        # 推理链和回复内容分开返回，便于后续处理
        reasoning_content = getattr(choice, "reasoning_content", "") or ""

        # 提取回复内容
        content = choice.content

        # 处理可能的列表格式（某些模型返回多模态内容）
        # 统一转换为字符串格式
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )

        # 确保返回字符串，处理 None 情况
        if content is None:
            final_text = ""
        elif isinstance(content, str):
            final_text = content
        else:
            final_text = str(content)

        return str(reasoning_content), final_text
