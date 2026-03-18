"""演示应用使用的轻量级 OpenAI 兼容 LLM 客户端，以及 Google ADK 本地部署客户端。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os
import re
from typing import Any, Optional, Sequence, Tuple

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
# 对话管理器（Dialogue Manager）使用此温度生成自然语言坐席话术。
# 0.3 在语言流畅度与输出稳定性之间取得平衡；动作解析器（Action Parser）
# 单独使用 PyTODTracker.AP_TEMPERATURE = 0.1，以确保代码生成的确定性。
DEFAULT_TEMPERATURE = 0.3


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

    def _call_openai_sync(
        self, messages: list, temperature: Optional[float] = None
    ) -> Tuple[str, str]:
        """真正执行 OpenAI 兼容 API 调用，返回 (reasoning_content, content)。

        这是所有公开接口（generate / chat / *_async）的唯一 HTTP 调用入口，
        消除代码重复，使错误处理和响应解析只需维护一份。

        Args:
            messages: OpenAI 兼容的消息列表。
            temperature: 采样温度；传入 ``None`` 时使用 ``LLMConfig.temperature``。

        Returns:
            ``(reasoning_content, content)``——``reasoning_content`` 仅在支持
            思维链的模型（如 DeepSeek-R1）中非空，``content`` 为最终回复文本。
        """
        temp = temperature if temperature is not None else self.config.temperature
        safe_max_tokens = self._calculate_safe_max_tokens(messages)
        extra_body = {
            "top_k": self.config.top_k,
            # 关闭响应内容中的思维链 token；
            # 否则 Qwen3、DeepSeek-R1 等推理模型会在 content 字段中
            # 输出 <think>…</think> 块。
            "chat_template_kwargs": {"enable_thinking": False},
        }
        try:
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

    def generate(self, prompt: str) -> Tuple[str, str]:
        """基于 Prompt 调用 LLM，返回 (reasoning_content, response_content)。

        Args:
            prompt: 完整的 Prompt

        Returns:
            (reasoning_content, response_content)，reasoning_content 仅部分模型（如 DeepSeek-R1）支持
        """
        messages = [{"role": "user", "content": prompt}]
        return self._call_openai_sync(messages)

    async def generate_async(self, prompt: str) -> Tuple[str, str]:
        """异步版本的 generate，在线程池中运行同步调用，不阻塞事件循环。

        Args:
            prompt: 完整的 Prompt

        Returns:
            (reasoning_content, response_content)
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self.generate(prompt))

    def chat(self, messages: list, temperature: float = None) -> str:
        """基于消息列表调用 LLM（同步版本）。

        Args:
            messages: 消息列表，格式为 [{"role": "system/user/assistant", "content": "..."}]
            temperature: 温度参数，默认使用配置值

        Returns:
            助手的回复内容
        """
        _, content = self._call_openai_sync(messages, temperature)
        return content

    async def chat_async(self, messages: list, temperature: float = None) -> str:
        """异步版本的 chat，在线程池中运行同步调用，不阻塞事件循环。

        Args:
            messages: 消息列表
            temperature: 温度参数，默认使用配置值

        Returns:
            助手的回复内容
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: self.chat(messages, temperature)
        )


# ---------------------------------------------------------------------------
# ADK 辅助函数：创建本地部署 LiteLlm 模型
# ---------------------------------------------------------------------------

def create_local_adk_model(config: Optional["LLMConfig"] = None) -> Any:
    """从 LLMConfig 创建 ADK LiteLlm 模型实例，接入本地 vLLM/OpenAI 兼容端点。

    将 ``.env`` 中的 ``QWEN3_BASE_URL`` / ``QWEN3_MODEL`` / ``QWEN3_API_KEY``
    等配置包装为 ADK 兼容的 ``LiteLlm`` 对象，供 ``LlmAgent`` / ``AdkFnCTODAgent``
    / ``AdkPyTODAgent`` 等直接使用。

    ADK 内部通过 LiteLLM 库将请求转发至 OpenAI 兼容端点，因此支持所有基于
    vLLM / Ollama / Qwen / DeepSeek 等本地部署的模型。

    参数:
        config: 本地 LLM 配置；若为 None 则调用 ``LLMConfig.from_env()``。

    返回:
        ``google.adk.models.lite_llm.LiteLlm`` 实例。

    示例::

        from contextmind.infra.llm_client import create_local_adk_model
        from google.adk.agents import LlmAgent

        adk_model = create_local_adk_model()
        agent = LlmAgent(model=adk_model, name="my_agent", instruction="你是助手。")
    """
    if config is None:
        config = LLMConfig.from_env()

    try:
        from google.adk.models.lite_llm import LiteLlm  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "google-adk 未安装或版本不支持 LiteLlm。\n"
            "请运行: pip install google-adk litellm"
        ) from exc

    # LiteLlm 使用 litellm 库的 model string 格式：
    # "openai/<model>" 表示 OpenAI 兼容端点（vLLM 默认协议）
    model_string = f"openai/{config.model}"
    return LiteLlm(
        model=model_string,
        api_base=config.base_url,
        api_key=config.api_key,
    )


# ---------------------------------------------------------------------------
# Google ADK 驱动的 LLM 客户端（本地部署版）
# ---------------------------------------------------------------------------

class AdkLLMClient:
    """Google ADK（Agent Development Kit）驱动的 LLM 客户端（本地部署版）。

    使用 ADK + LiteLlm 将请求转发至本地 vLLM / OpenAI 兼容端点，
    提供与 :class:`SimpleLLMClient` 完全相同的公共接口
    （``chat`` / ``chat_async`` / ``generate`` / ``generate_async``），
    因此可作为任意 Tracker 或 Application 中 ``llm_client=`` 参数的
    **直接替换品**，无需修改调用方代码。

    LLM 配置通过 ``.env`` 文件或 ``LLMConfig`` 实例统一管理，
    与 ``SimpleLLMClient`` 保持一致。

    与 ``SimpleLLMClient`` 的主要差异
    ------------------------------------
    * 底层使用 **Google ADK** + ``LlmAgent`` + ``InMemoryRunner``，
      所有请求都通过 ADK 的 session 管理和 event-streaming 机制完成。
    * 每次 ``chat()`` / ``generate()`` 调用均为**无状态**（Stateless）——
      消息历史由调用方传入；ADK session 在每次调用结束后丢弃。
    * 若需要在连续调用间保持有状态 session，请直接使用
      :class:`contextmind.modes.pytod.adk_bridge.AdkLlmClientBridge`。

    参数
    ----
    system_instruction : str
        传递给 LlmAgent 的系统指令；可在创建后通过 :attr:`system_instruction`
        属性动态替换。
    config : LLMConfig | None
        本地 LLM 配置；若为 None 则从 ``.env`` 环境变量自动加载。

    示例
    ----
    替换任意使用 ``SimpleLLMClient`` 的 Tracker::

        from contextmind.infra.llm_client import AdkLLMClient
        from contextmind.modes.dst import DialogueStateTracker

        llm = AdkLLMClient()
        tracker = DialogueStateTracker.from_scenario(llm, scenario_config)
        result = await tracker.process_turn("我想预约明天下午三点")
    """

    #: sync chat() 的最大等待秒数（可通过子类覆盖）
    SYNC_CALL_TIMEOUT: float = 120.0

    def __init__(
        self,
        system_instruction: str = "你是一个智能对话助手。",
        config: Optional[LLMConfig] = None,
    ) -> None:
        try:
            from google.adk.agents import LlmAgent  # type: ignore[import]
            from google.adk.runners import InMemoryRunner  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "google-adk 未安装，无法创建 AdkLLMClient。\n"
                "请运行: pip install google-adk litellm"
            ) from exc

        self._config = config or LLMConfig.from_env()
        self._adk_model = create_local_adk_model(self._config)
        self.system_instruction = system_instruction

        # 延迟创建 agent（system_instruction 可在调用前修改）
        self._LlmAgent = LlmAgent
        self._InMemoryRunner = InMemoryRunner

        logger.info(f"[AdkLLMClient] 初始化完成，model={self._config.model}")

    # ------------------------------------------------------------------ #
    # 内部辅助方法
    # ------------------------------------------------------------------ #

    def _build_user_content(self, messages: list) -> str:
        """将 OpenAI 消息列表拼合为单个用户消息字符串。

        ADK 的 ``runner.run()`` 接受单条用户消息；多轮历史以
        ``Human: … Assistant: …`` 格式嵌入，使模型感知上下文。
        """
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

        # 将额外的 system 内容追加到最后一条 user 消息前
        if system_parts and parts:
            system_text = "\n".join(system_parts)
            parts.insert(0, f"[System Instruction]\n{system_text}\n[/System Instruction]\n")

        return "\n".join(parts) if parts else ""

    async def _run_async(
        self,
        user_content: str,
        system_instruction: Optional[str] = None,
    ) -> str:
        """核心异步执行：创建一次性 ADK session 并返回最终文本响应。"""
        from google.adk.agents import LlmAgent  # type: ignore[import]
        from google.adk.runners import InMemoryRunner  # type: ignore[import]

        instruction = system_instruction or self.system_instruction
        agent = LlmAgent(
            name="adk_llm_client",
            model=self._adk_model,
            instruction=instruction,
        )
        runner = InMemoryRunner(agent=agent, app_name="contextmind_adk")
        session = await runner.session_service.create_session(
            app_name="contextmind_adk",
            user_id="default",
        )

        from google.genai import types as genai_types  # type: ignore[import]

        content = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=user_content)],
        )

        final_text = ""
        async for event in runner.run_async(
            user_id="default",
            session_id=session.id,
            new_message=content,
        ):
            if event.is_final_response() and event.content:
                for part in event.content.parts or []:
                    if hasattr(part, "text") and part.text:
                        final_text += part.text

        return final_text.strip()

    # ------------------------------------------------------------------ #
    # 公共接口（与 SimpleLLMClient 完全兼容）
    # ------------------------------------------------------------------ #

    async def chat_async(
        self,
        messages: list,
        temperature: Optional[float] = None,
    ) -> str:
        """异步多轮对话接口（与 SimpleLLMClient.chat_async 签名兼容）。

        Args:
            messages: OpenAI 格式消息列表（role/content 字典）。
            temperature: 保留参数，ADK 通过模型配置控制，此处忽略。

        Returns:
            助手的回复文本。
        """
        user_content = self._build_user_content(messages)
        return await self._run_async(user_content)

    def chat(
        self,
        messages: list,
        temperature: Optional[float] = None,
    ) -> str:
        """同步多轮对话接口（与 SimpleLLMClient.chat 签名兼容）。"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    asyncio.run,
                    self.chat_async(messages=messages, temperature=temperature),
                )
                return future.result(timeout=self.SYNC_CALL_TIMEOUT)
        else:
            return asyncio.run(
                self.chat_async(messages=messages, temperature=temperature)
            )

    async def generate_async(self, prompt: str) -> tuple[str, str]:
        """异步 prompt 生成接口（与 SimpleLLMClient.generate_async 签名兼容）。

        Returns:
            ``(reasoning_content, response_content)``——ADK 不暴露 CoT，
            ``reasoning_content`` 始终为空字符串。
        """
        messages = [{"role": "user", "content": prompt}]
        content = await self.chat_async(messages)
        return "", content

    def generate(self, prompt: str) -> tuple[str, str]:
        """同步 prompt 生成接口（与 SimpleLLMClient.generate 签名兼容）。"""
        messages = [{"role": "user", "content": prompt}]
        content = self.chat(messages)
        return "", content
