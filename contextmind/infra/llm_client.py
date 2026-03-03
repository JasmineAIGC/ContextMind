"""演示应用使用的轻量级 OpenAI 兼容 LLM 客户端。"""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Optional, Sequence, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None  # type: ignore
    print("警告: 未安装 OpenAI 包。真实的 LLM 调用将无法工作。")
    print("安装方法: pip install openai")

from .logger import get_logger

logger = get_logger(__name__)

DEFAULT_MODEL = "Qwen3-32B"
# 0.6 在确定性与多样性之间取得平衡；更低的值输出更稳定但可能过于重复，
# 更高的值增加幻觉风险。
DEFAULT_TEMPERATURE = 0.6


def _first_env(keys: Sequence[str], default: Optional[str] = None) -> Optional[str]:
    """按顺序读取环境变量，返回首个非空值。
    
    支持多个环境变量名，便于适配不同的部署环境（Qwen、DeepSeek、OpenAI 等）。
    """
    for key in keys:
        if value := os.getenv(key):
            return value
    return default


@dataclass
class LLMConfig:
    """OpenAI 兼容端点的运行时配置。"""

    api_key: str
    model: str = DEFAULT_MODEL
    base_url: Optional[str] = None
    temperature: float = DEFAULT_TEMPERATURE
    access_key: Optional[str] = None
    top_k: int = 20  # vLLM/Qwen top-k 采样参数；20 是合理的初始值
    max_tokens: int = 4096  # 保守上限；输入过长时每次请求会动态缩减

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """从环境变量加载配置。"""
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
                "缺少 API key。请在 .env 文件中设置以下变量之一: QWEN3_API_KEY, "
                "LLM_API_KEY, OPENAI_API_KEY 等"
            )

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

        temperature_str = _first_env(
            [
                "CONTEXTMIND_TEMPERATURE",
                "LLM_TEMPERATURE",
                "OPENAI_TEMPERATURE",
            ]
        )
        temperature = (
            float(temperature_str) if temperature_str is not None else DEFAULT_TEMPERATURE
        )

        access_key = _first_env(
            [
                "QWEN3_ACCESS_KEY",
                "CONTEXTMIND_ACCESS_KEY",
                "LLM_ACCESS_KEY",
                "ACCESS_KEY",
            ]
        )

        top_k_str = _first_env(["QWEN3_TOP_K", "LLM_TOP_K", "TOP_K"])
        top_k = int(top_k_str) if top_k_str else 20

        max_tokens_str = _first_env(["QWEN3_MAX_TOKENS", "LLM_MAX_TOKENS", "MAX_TOKENS"])
        max_tokens = int(max_tokens_str) if max_tokens_str else 4096

        return cls(
            api_key=api_key,
            model=model,
            base_url=base_url,
            temperature=temperature,
            access_key=access_key,
            top_k=top_k,
            max_tokens=max_tokens,
        )


class SimpleLLMClient:
    """演示应用的简单 LLM 客户端（非 Evolve 框架核心，仅用于演示）。"""

    MODEL_CONTEXT_LIMITS = {
        "gpt-3.5-turbo": 4096,
        "gpt-3.5-turbo-16k": 16384,
        "gpt-4": 8192,
        "gpt-4-32k": 32768,
        "gpt-4-turbo": 128000,
        "gpt-4o": 128000,
        "Qwen2.5-7B-Instruct": 32768,
        "Qwen2.5-14B-Instruct": 32768,
        "Qwen2.5-32B-Instruct": 32768,
        "Qwen2.5-72B-Instruct": 32768,
        "Qwen3-32B": 32768,
        "Qwen3-235B": 131072,
        "deepseek-chat": 32768,
        "deepseek-r1": 64000,
    }

    def __init__(self, config: Optional[LLMConfig] = None):
        """初始化 LLM 客户端。

        Args:
            config: LLM 配置，若为 None 则从环境变量加载
        """
        if not OPENAI_AVAILABLE:
            raise RuntimeError(
                "未安装 OpenAI 包。"
                "请使用以下命令安装: pip install openai\n"
                "或使用 --no-llm 标志运行而不需要真实的 LLM 调用。"
            )

        self.config = config or LLMConfig.from_env()
        logger.info(f"[LLM Client] 正在初始化，model: {self.config.model}")

        headers = {}
        if self.config.access_key:
            headers["access-key"] = self.config.access_key

        self._client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            default_headers=headers or None,
        )
        logger.info(f"[LLM Client] 初始化成功")

    @staticmethod
    def _strip_thinking(text: str) -> str:
        """去除模型输出中的思考过程标签（<think>…</think>）。

        部分推理模型（如 Qwen3 / DeepSeek-R1）即使在 API 层面禁用了
        enable_thinking，仍可能在 content 字段内嵌入 <think>…</think>
        或 <|think|>…<|/think|> 块。此方法在返回给调用方之前统一剥离这些标签。
        """
        # <think>...</think>（Qwen3 格式）
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        # <|think|>...<|/think|>（DeepSeek token 格式）
        text = re.sub(r"<\|think\|>.*?<\|/think\|>", "", text, flags=re.DOTALL)
        return text.strip()

    def _estimate_tokens(self, text: str) -> int:
        """估算文本的 token 数量（启发式：中文 1 字≈1 token，英文 1 词≈1.3 token）。

        Args:
            text: 要估算的文本

        Returns:
            估算的 token 数量
        """
        import re

        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_words = len(re.findall(r'\b[a-zA-Z]+\b', text))
        estimated_tokens = int((chinese_chars + int(english_words * 1.3)) * 1.1)
        return max(estimated_tokens, len(text) // 4)
    
    def _get_model_context_limit(self) -> int:
        """返回当前模型的上下文 token 限制。"""
        model = self.config.model

        if model in self.MODEL_CONTEXT_LIMITS:
            return self.MODEL_CONTEXT_LIMITS[model]

        for known_model, limit in self.MODEL_CONTEXT_LIMITS.items():
            if known_model.lower() in model.lower() or model.lower() in known_model.lower():
                return limit

        logger.warning(f"未知模型 {model}，使用默认上下文限制 4096 tokens")
        return 4096

    def _calculate_safe_max_tokens(self, messages: list) -> int:
        """根据输入消息动态计算安全的 max_tokens 值。

        Args:
            messages: 消息列表

        Returns:
            安全的 max_tokens 值
        """
        input_text = ""
        for msg in messages:
            if isinstance(msg, dict) and "content" in msg:
                input_text += msg["content"] + " "

        estimated_input_tokens = self._estimate_tokens(input_text)
        context_limit = self._get_model_context_limit()
        # 预留 10% 冗余量以应对分词误差；至少保留 512 个 token，
        # 确保模型始终有足够空间生成有意义的响应。
        available_tokens = int((context_limit - estimated_input_tokens) * 0.9)
        safe_max_tokens = min(self.config.max_tokens, max(available_tokens, 512))

        if safe_max_tokens < self.config.max_tokens:
            logger.info(
                f"动态调整max_tokens: {self.config.max_tokens} -> {safe_max_tokens} "
                f"(输入≈{estimated_input_tokens} tokens, 上下文限制={context_limit})"
            )

        return safe_max_tokens

    def generate(self, prompt: str) -> Tuple[str, str]:
        """基于 Prompt 调用 LLM，返回 (reasoning_content, response_content)。

        Args:
            prompt: 完整的 Prompt

        Returns:
            (reasoning_content, response_content)，reasoning_content 仅部分模型（如 DeepSeek-R1）支持
        """
        messages = [{"role": "user", "content": prompt}]

        try:
            safe_max_tokens = self._calculate_safe_max_tokens(messages)
            extra_body = {
                "top_k": self.config.top_k,
                # 关闭响应内容中的思维链 token；
                # 否则 Qwen3、DeepSeek-R1 等推理模型会在 content 字段中
                # 输出 <think>…</think> 块。
                "chat_template_kwargs": {"enable_thinking": False},
            }
            response = self._client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=safe_max_tokens,
                stream=False,
                extra_body=extra_body,
            )
        except Exception as e:
            logger.error(f"LLM API调用失败: {str(e)}", exc_info=True)
            raise RuntimeError(
                f"调用 LLM API 失败 (model: {self.config.model}): {str(e)}"
            ) from e

        if not response.choices:
            raise ValueError(f"API 返回空的 choices (model: {self.config.model})")

        choice = response.choices[0].message

        if not choice:
            raise ValueError(f"API 返回无效的 message (model: {self.config.model})")

        reasoning_content = getattr(choice, "reasoning_content", "") or ""
        content = choice.content

        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )

        if content is None:
            final_text = ""
        elif isinstance(content, str):
            final_text = self._strip_thinking(content)
        else:
            final_text = self._strip_thinking(str(content))

        return str(reasoning_content), final_text

    async def generate_async(self, prompt: str) -> Tuple[str, str]:
        """异步版本的 generate（当前封装同步版本，生产环境应使用 AsyncOpenAI）。

        Wraps the synchronous call to satisfy async callers without blocking the
        event loop correctly.  Replace with ``AsyncOpenAI`` for production use.
        """
        return self.generate(prompt)

    def chat(self, messages: list, temperature: float = None) -> str:
        """基于消息列表调用 LLM（同步版本）。

        Args:
            messages: 消息列表，格式为 [{"role": "system/user/assistant", "content": "..."}]
            temperature: 温度参数，默认使用配置值

        Returns:
            助手的回复内容
        """
        try:
            temp = temperature if temperature is not None else self.config.temperature
            safe_max_tokens = self._calculate_safe_max_tokens(messages)
            extra_body = {
                "top_k": self.config.top_k,
                "chat_template_kwargs": {"enable_thinking": False},
            }
            response = self._client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=temp,
                max_tokens=safe_max_tokens,
                stream=False,
                extra_body=extra_body,
            )
        except Exception as e:
            logger.error(f"LLM API调用失败: {str(e)}", exc_info=True)
            raise RuntimeError(
                f"调用 LLM API 失败 (model: {self.config.model}): {str(e)}"
            ) from e

        if not response.choices:
            raise ValueError(f"API 返回空的 choices (model: {self.config.model})")

        choice = response.choices[0].message

        if not choice:
            raise ValueError(f"API 返回无效的 message (model: {self.config.model})")

        content = choice.content

        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )

        if content is None:
            return ""
        elif isinstance(content, str):
            return self._strip_thinking(content)
        else:
            return self._strip_thinking(str(content))

    async def chat_async(self, messages: list, temperature: float = None) -> str:
        """异步版本的 chat（当前封装同步版本，生产环境应使用 AsyncOpenAI）。

        Args:
            messages: 消息列表
            temperature: 温度参数，默认使用配置值

        Returns:
            助手的回复内容
        """
        return self.chat(messages, temperature)
