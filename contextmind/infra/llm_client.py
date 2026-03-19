"""基于 Google ADK 的 LLM 客户端，通过 LiteLlm 接入本地 vLLM/OpenAI 兼容端点。"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from google.adk.agents import LlmAgent  # type: ignore[import]
    from google.adk.models.lite_llm import LiteLlm  # type: ignore[import]
    from google.adk.runners import InMemoryRunner  # type: ignore[import]
    from google.genai import types as genai_types  # type: ignore[import]
    _ADK_AVAILABLE = True
except ImportError:
    _ADK_AVAILABLE = False

from .logger import get_logger

logger = get_logger(__name__)

DEFAULT_MODEL = "Qwen3-32B"
DEFAULT_TEMPERATURE = 0.3

_ADK_INSTALL_MSG = (
    "google-adk 未安装，无法创建 AdkLLMClient。\n"
    "请运行: pip install google-adk litellm"
)


def _first_env(keys: Sequence[str], default: Optional[str] = None) -> Optional[str]:
    """按顺序读取环境变量，返回首个非空值。"""
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
    top_k: int = 20
    max_tokens: int = 4096

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """从环境变量加载配置。"""
        api_key = _first_env([
            "QWEN3_API_KEY", "CONTEXTMIND_API_KEY", "LLM_API_KEY",
            "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "QWEN_API_KEY",
        ])
        if not api_key:
            raise ValueError(
                "缺少 API key。请在 .env 文件中设置以下变量之一: "
                "QWEN3_API_KEY, LLM_API_KEY, OPENAI_API_KEY 等"
            )

        base_url = _first_env([
            "QWEN3_BASE_URL", "CONTEXTMIND_BASE_URL", "LLM_BASE_URL",
            "OPENAI_BASE_URL", "DEEPSEEK_BASE_URL", "QWEN_BASE_URL",
        ])
        model = _first_env([
            "QWEN3_MODEL", "CONTEXTMIND_MODEL", "LLM_MODEL",
            "OPENAI_MODEL", "DEEPSEEK_MODEL", "QWEN_MODEL",
        ], default=DEFAULT_MODEL)
        temperature_str = _first_env([
            "CONTEXTMIND_TEMPERATURE", "LLM_TEMPERATURE", "OPENAI_TEMPERATURE",
        ])
        temperature = float(temperature_str) if temperature_str else DEFAULT_TEMPERATURE
        top_k = int(v) if (v := _first_env(["QWEN3_TOP_K", "LLM_TOP_K", "TOP_K"])) else 20
        max_tokens = int(v) if (v := _first_env(["QWEN3_MAX_TOKENS", "LLM_MAX_TOKENS", "MAX_TOKENS"])) else 4096

        return cls(
            api_key=api_key,
            model=model,
            base_url=base_url,
            temperature=temperature,
            top_k=top_k,
            max_tokens=max_tokens,
        )


def create_local_adk_model(config: Optional[LLMConfig] = None) -> Any:
    """从 LLMConfig 创建 ADK LiteLlm 模型实例，接入本地 vLLM/OpenAI 兼容端点。

    示例::

        from contextmind.infra.llm_client import create_local_adk_model
        from google.adk.agents import LlmAgent

        model = create_local_adk_model()
        agent = LlmAgent(model=model, name="my_agent", instruction="你是助手。")
    """
    if not _ADK_AVAILABLE:
        raise ImportError(_ADK_INSTALL_MSG)
    if config is None:
        config = LLMConfig.from_env()

    return LiteLlm(
        model=f"openai/{config.model}",
        api_base=config.base_url,
        api_key=config.api_key,
    )


class AdkLLMClient:
    """基于 Google ADK 的无状态 LLM 客户端。

    通过 ADK + LiteLlm 将请求转发至本地 vLLM / OpenAI 兼容端点。
    每次调用创建一次性 session，适合无状态的单次 LLM 调用场景。
    有状态多轮对话请直接使用 ADK 的 LlmAgent + InMemoryRunner。

    参数
    ----
    system_instruction : str
        传递给 LlmAgent 的系统指令。
    config : LLMConfig | None
        本地 LLM 配置；若为 None 则从 ``.env`` 自动加载。

    示例::

        from contextmind.infra.llm_client import AdkLLMClient
        llm = AdkLLMClient()
        reply = await llm.chat_async([{"role": "user", "content": "你好"}])
    """

    def __init__(
        self,
        system_instruction: str = "你是一个智能对话助手。",
        config: Optional[LLMConfig] = None,
    ) -> None:
        if not _ADK_AVAILABLE:
            raise ImportError(_ADK_INSTALL_MSG)

        self._config = config or LLMConfig.from_env()
        self._adk_model = create_local_adk_model(self._config)
        self.system_instruction = system_instruction
        logger.info(f"[AdkLLMClient] 初始化完成，model={self._config.model}")

    def _build_user_content(self, messages: List[dict]) -> str:
        """将 OpenAI messages 列表拼合为 ADK 单条用户消息字符串。"""
        parts: list[str] = []
        system_parts: list[str] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_parts.append(content)
            elif role == "user":
                parts.append(f"Human: {content}")
            elif role in ("assistant", "model"):
                parts.append(f"Assistant: {content}")
        if system_parts and parts:
            parts.insert(0, f"[System]\n{chr(10).join(system_parts)}\n[/System]\n")
        return "\n".join(parts) if parts else ""

    async def chat_async(
        self,
        messages: List[dict],
        temperature: Optional[float] = None,  # noqa: ARG002 – ADK 由模型配置控制
    ) -> str:
        """异步多轮对话。

        Args:
            messages: OpenAI 格式消息列表（role/content 字典）。

        Returns:
            助手的回复文本。
        """
        agent = LlmAgent(
            name="adk_llm_client",
            model=self._adk_model,
            instruction=self.system_instruction,
        )
        runner = InMemoryRunner(agent=agent, app_name="contextmind_adk")
        session = await runner.session_service.create_session(
            app_name="contextmind_adk", user_id="default",
        )
        content = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=self._build_user_content(messages))],
        )
        final_text = ""
        async for event in runner.run_async(
            user_id="default", session_id=session.id, new_message=content,
        ):
            if event.is_final_response() and event.content:
                for part in event.content.parts or []:
                    if hasattr(part, "text") and part.text:
                        final_text += part.text
        return final_text.strip()

    async def generate_async(self, prompt: str) -> tuple[str, str]:
        """异步 prompt 生成，返回 ``("", response_text)``。"""
        return "", await self.chat_async([{"role": "user", "content": prompt}])

    def generate(self, prompt: str) -> tuple[str, str]:
        """同步 prompt 生成，返回 ``(reasoning, response_text)`` 元组。

        ``reasoning`` 始终为空字符串（仅 DeepSeek-R1 等 CoT 模型会有非空值）。

        若当前线程已有运行中的 event loop（如 Jupyter Notebook），
        则在独立线程的新 loop 中执行，避免 "cannot run nested event loop" 报错。
        """
        import asyncio
        import concurrent.futures

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            # 已在异步上下文中（Jupyter / async 测试框架）——在新线程中执行
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, self.generate_async(prompt))
                return future.result()
        else:
            return asyncio.run(self.generate_async(prompt))



