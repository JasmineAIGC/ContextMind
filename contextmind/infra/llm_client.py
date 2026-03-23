"""基于 Google ADK 的 LLM 客户端，通过 LiteLlm 接入本地 vLLM/OpenAI 兼容端点。"""

from __future__ import annotations

import asyncio
import os
import re
import warnings
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from google.adk.agents import LlmAgent  # type: ignore[import]  # noqa: F401 — kept for create_local_adk_model / external callers
    from google.adk.models.lite_llm import LiteLlm  # type: ignore[import]
    from google.adk.runners import InMemoryRunner  # type: ignore[import]  # noqa: F401 — kept for external callers
    _ADK_AVAILABLE = True
except ImportError:
    _ADK_AVAILABLE = False

from .logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# LiteLLM 全局噪音抑制
# ---------------------------------------------------------------------------
# 问题1: LiteLLM 日志后台线程在 event loop 关闭后尝试调度异步回调，产生
#        "coroutine 'Logging.async_success_handler' was never awaited" RuntimeWarning。
#        通过 warnings 过滤器屏蔽该特定警告，同时禁用 LiteLLM 的遥测/成功回调。
# 问题2: LiteLLM 每次请求都尝试查本地自托管模型的价格，因未在价格表中而打印
#        大量 DEBUG 日志。通过注册零价格条目消除这些日志。
warnings.filterwarnings(
    "ignore",
    message="coroutine 'Logging.async_success_handler' was never awaited",
    category=RuntimeWarning,
)

def _configure_litellm_for_local_model(model_name: str) -> None:
    """配置 LiteLLM 全局状态以减少本地部署模型的噪音日志。

    - 禁用遥测和成功/失败回调，避免 async_success_handler 未等待的 RuntimeWarning。
    - 注册零价格条目，避免"model not in cost map"的 DEBUG 日志。
    - 禁用 LiteLLM 自有 logger 向根 logger 的传播，避免每条 LiteLLM INFO
      日志在控制台出现两次（一次来自 LiteLLM 自带 handler，一次来自根 logger）。

    仅在 litellm 可导入时生效；导入失败时静默跳过。
    """
    # 阻止 LiteLLM logger 向根 logger 传播（解决双重日志问题）
    import logging as _logging
    _logging.getLogger("LiteLLM").propagate = False

    try:
        import litellm  # type: ignore[import]

        # 禁用回调（问题1）
        litellm.success_callback = []
        litellm.failure_callback = []
        litellm.callbacks = []

        # 注册零价格条目（问题2），覆盖 `openai/<model>` 和裸 model 两种键。
        # 使用 litellm.register_model()（官方 API）而非直接操作 model_cost dict，
        # 确保 get_model_info() 内部的所有查找路径均能命中该条目。
        _zero_cost: dict = {
            "max_tokens": 32768,
            "max_input_tokens": 32768,
            "max_output_tokens": 32768,
            "input_cost_per_token": 0.0,
            "output_cost_per_token": 0.0,
            "litellm_provider": "openai",
            "mode": "chat",
        }
        model_registry = {key: _zero_cost for key in (model_name, f"openai/{model_name}")}
        try:
            litellm.register_model(model_registry)
        except Exception:
            # Fallback: 直接写入 model_cost dict（兼容旧版 litellm）
            for key, val in model_registry.items():
                litellm.model_cost.setdefault(key, val)
    except Exception as exc:
        logger.debug(f"[AdkLLMClient] litellm 配置失败（非致命）: {exc}")


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


_THINKING_MODELS = ("qwen3", "qwen-3", "deepseek-r1", "deepseek_r1")
"""模型名称片段列表（小写），对应需要禁用思考模式的推理模型。"""


def _is_thinking_model(model: str) -> bool:
    """如果模型名称表明它是推理型模型，返回 True。"""
    lower = model.lower()
    return any(fragment in lower for fragment in _THINKING_MODELS)


@dataclass
class LLMConfig:
    """OpenAI 兼容端点的运行时配置。"""

    api_key: str
    model: str = DEFAULT_MODEL
    base_url: Optional[str] = None
    temperature: float = DEFAULT_TEMPERATURE
    top_k: int = 20
    max_tokens: int = 4096
    enable_thinking: Optional[bool] = None
    """控制推理模型（如 Qwen3）的思考模式。
    ``False`` 通过 ``extra_body`` 禁用链式推理输出，防止思考内容出现在回复中。
    ``None``（默认）：对已知推理模型自动设为 ``False``，其他模型不传此参数。
    ``True``：强制启用思考模式（通常用于调试）。
    """

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

        # 解析 ENABLE_THINKING 环境变量；若未设置则由 enable_thinking=None 触发自动检测
        enable_thinking_str = _first_env([
            "CONTEXTMIND_ENABLE_THINKING", "LLM_ENABLE_THINKING", "ENABLE_THINKING",
        ])
        if enable_thinking_str is not None:
            enable_thinking: Optional[bool] = enable_thinking_str.lower() not in ("false", "0", "no", "off")
        else:
            enable_thinking = None

        return cls(
            api_key=api_key,
            model=model,
            base_url=base_url,
            temperature=temperature,
            top_k=top_k,
            max_tokens=max_tokens,
            enable_thinking=enable_thinking,
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

    # 决定是否通过 extra_body 控制推理模型的思考模式。
    # enable_thinking=None（默认）→ 已知推理模型（Qwen3、DeepSeek-R1 等）自动禁用；
    # enable_thinking=False   → 强制禁用；enable_thinking=True → 强制启用。
    resolved_thinking: Optional[bool] = config.enable_thinking
    if resolved_thinking is None and _is_thinking_model(config.model):
        resolved_thinking = False

    # ADK 的 LiteLlm.__init__ 将所有 **kwargs 存入 _additional_args，并在每次
    # generate_content_async 调用时直接展开传给 litellm.acompletion()。
    # 因此须将 extra_body 作为顶层 kwarg 传入，而非嵌套在 model_kwargs 里。
    # vLLM 的 Qwen3 chat template 要求 enable_thinking 必须嵌套在 chat_template_kwargs 下：
    #   extra_body={"chat_template_kwargs": {"enable_thinking": False}}
    # 若只传 extra_body={"enable_thinking": False}，vLLM 会忽略该字段，
    # 导致 Qwen3 默认以思考模式运行，生成大量 <think> token，响应时间暴增。
    extra_kwargs: dict = {}
    if resolved_thinking is not None:
        extra_kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": resolved_thinking}}

    return LiteLlm(
        model=f"openai/{config.model}",
        api_base=config.base_url,
        api_key=config.api_key,
        **extra_kwargs,
    )


class AdkLLMClient:
    """基于 Google ADK（LiteLLM）的无状态 LLM 客户端。

    使用 ADK 配套的 LiteLLM 库直接调用 vLLM / OpenAI 兼容端点，
    每次 ``chat_async`` 调用恰好发起一次 LLM API 请求。

    与旧版差异：
    - 不再通过 ``InMemoryRunner + LlmAgent`` 发起请求。
      ADK 的 Agent 框架在单次无工具调用场景下会产生额外的内部 LLM 请求
      （如 pre-flight 检查、grounding 等），导致每次逻辑调用实际产生两次 API 请求。
    - 现使用 ``litellm.acompletion()`` 直接发起单次异步请求，
      保持与 OpenAI messages 格式完全兼容，同时保留 ADK LiteLLM 的所有配置能力。

    参数
    ----
    config : LLMConfig | None
        本地 LLM 配置；若为 None 则从 ``.env`` 自动加载。

    示例::

        from contextmind.infra.llm_client import AdkLLMClient
        llm = AdkLLMClient()
        reply = await llm.chat_async([{"role": "user", "content": "你好"}])
    """

    def __init__(
        self,
        system_instruction: str = "你是一个智能对话助手。",  # noqa: ARG002 — 保持旧接口兼容
        config: Optional[LLMConfig] = None,
    ) -> None:
        if not _ADK_AVAILABLE:
            raise ImportError(_ADK_INSTALL_MSG)

        # 在初始化时导入 litellm，确保依赖缺失时立即报错（fail-fast），
        # 同时避免每次 chat_async 调用都重复执行模块查找。
        try:
            import litellm as _litellm  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "litellm 未安装，无法调用 LLM。\n请运行: pip install litellm"
            ) from exc
        self._litellm = _litellm

        self._config = config or LLMConfig.from_env()
        _configure_litellm_for_local_model(self._config.model)

        # 预先解析思考模式，避免每次 chat_async 重复计算
        resolved_thinking: Optional[bool] = self._config.enable_thinking
        if resolved_thinking is None and _is_thinking_model(self._config.model):
            resolved_thinking = False
        self._resolved_thinking = resolved_thinking

        logger.info(f"[AdkLLMClient] 初始化完成，model={self._config.model}")

    async def chat_async(
        self,
        messages: List[dict],
        temperature: Optional[float] = None,
    ) -> str:
        """异步多轮对话。每次调用恰好发起一次 LLM API 请求。

        Args:
            messages: OpenAI 格式消息列表（role/content 字典）。
            temperature: 覆盖默认温度；为 None 时使用 LLMConfig 中的值。

        Returns:
            助手的回复文本（已剥除推理模型的 <think>…</think> 块）。
        """
        _litellm = self._litellm
        temp = temperature if temperature is not None else self._config.temperature

        extra_kwargs: dict = {}
        if self._resolved_thinking is not None:
            extra_kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": self._resolved_thinking}}

        response = await _litellm.acompletion(
            model=f"openai/{self._config.model}",
            messages=messages,
            api_base=self._config.base_url,
            api_key=self._config.api_key,
            temperature=temp,
            max_tokens=self._config.max_tokens,
            **extra_kwargs,
        )
        final_text: str = (response.choices[0].message.content or "").strip()
        # 剥除推理模型（Qwen3、DeepSeek-R1 等）输出的思考块
        final_text = re.sub(r"<think>.*?</think>", "", final_text, flags=re.DOTALL)
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



