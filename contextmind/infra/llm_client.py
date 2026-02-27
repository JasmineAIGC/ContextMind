"""
Evolve v0.2.1 演示用的简单 LLM 客户端

为演示应用提供轻量级的 OpenAI 兼容 LLM 客户端。
基于 v6.0 客户端但为演示目的进行了简化。

注意: 在 v0.2.1 中，LLM 调用在 Evolve 框架外部。
此客户端仅用于演示应用，不是核心框架的一部分。
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Optional, Sequence, Tuple

# 加载.env文件中的环境变量
try:
    from dotenv import load_dotenv
    load_dotenv()  # 自动从当前目录或父目录查找.env文件并加载
except ImportError:
    # 如果没有安装python-dotenv，继续使用系统环境变量
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
    top_k: int = 20
    max_tokens: int = 4096  # 降低默认值以避免超出上下文限制

    @classmethod
    def from_env(cls) -> "LLMConfig":
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
                "缺少 API key。请在 .env 文件中设置以下变量之一: QWEN3_API_KEY, "
                "LLM_API_KEY, OPENAI_API_KEY 等"
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
            ]
        )

        # 读取 top_k 参数（可选）
        top_k_str = _first_env(["QWEN3_TOP_K", "LLM_TOP_K", "TOP_K"])
        top_k = int(top_k_str) if top_k_str else 20

        # 读取 max_tokens 参数（可选）
        max_tokens_str = _first_env(["QWEN3_MAX_TOKENS", "LLM_MAX_TOKENS", "MAX_TOKENS"])
        max_tokens = int(max_tokens_str) if max_tokens_str else 4096  # 降低默认值

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
    """演示应用的简单 LLM 客户端 (v0.2.1)。
    
    注意: 这不是 Evolve 核心框架的一部分。
    在 v0.2.1 中，LLM 调用是外部的。此客户端仅用于演示。
    """
    
    # 常见模型的上下文限制（tokens）
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
        """初始化客户端。"""
        if not OPENAI_AVAILABLE:
            raise RuntimeError(
                "未安装 OpenAI 包。"
                "请使用以下命令安装: pip install openai\n"
                "或使用 --no-llm 标志运行而不需要真实的 LLM 调用。"
            )
        
        self.config = config or LLMConfig.from_env()
        logger.info(f"[LLM Client] 正在初始化，model: {self.config.model}")

        # 构造 headers，如果需要 Access Key
        headers = {}
        if self.config.access_key:
            headers["access-key"] = self.config.access_key

        # 创建 OpenAI 客户端
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
        # <think>...</think> (Qwen3 style)
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        # <|think|>...<|/think|> (DeepSeek token style)
        text = re.sub(r"<\|think\|>.*?<\|/think\|>", "", text, flags=re.DOTALL)
        return text.strip()

    def _estimate_tokens(self, text: str) -> int:
        """
        估算文本的token数量
        
        使用简单的启发式方法：
        - 中文：1个字符约等于1个token
        - 英文：1个单词约等于1.3个token
        
        Args:
            text: 要估算的文本
            
        Returns:
            估算的token数量
        """
        # 简单估算：中文字符 + 英文单词的token数
        # 这是一个粗略估计，实际token数可能有所不同
        import re
        
        # 统计中文字符（包括标点）
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        
        # 统计英文单词
        english_words = len(re.findall(r'\b[a-zA-Z]+\b', text))
        
        # 估算：中文1字=1token, 英文1词≈1.3token
        estimated_tokens = chinese_chars + int(english_words * 1.3)
        
        # 加上一些额外的空间用于标点和格式
        estimated_tokens = int(estimated_tokens * 1.1)
        
        return max(estimated_tokens, len(text) // 4)  # 至少按4字符=1token估算
    
    def _get_model_context_limit(self) -> int:
        """
        获取当前模型的上下文限制
        
        Returns:
            上下文限制（tokens）
        """
        model = self.config.model
        
        # 检查完全匹配
        if model in self.MODEL_CONTEXT_LIMITS:
            return self.MODEL_CONTEXT_LIMITS[model]
        
        # 检查部分匹配（例如 "Qwen2.5-7B" 匹配 "Qwen2.5"）
        for known_model, limit in self.MODEL_CONTEXT_LIMITS.items():
            if known_model.lower() in model.lower() or model.lower() in known_model.lower():
                return limit
        
        # 默认使用保守的限制
        logger.warning(f"未知模型 {model}，使用默认上下文限制 4096 tokens")
        return 4096
    
    def _calculate_safe_max_tokens(self, messages: list) -> int:
        """
        根据输入消息计算安全的max_tokens值
        
        Args:
            messages: 消息列表
            
        Returns:
            安全的max_tokens值
        """
        # 估算输入的token数
        input_text = ""
        for msg in messages:
            if isinstance(msg, dict) and "content" in msg:
                input_text += msg["content"] + " "
        
        estimated_input_tokens = self._estimate_tokens(input_text)
        
        # 获取模型的上下文限制
        context_limit = self._get_model_context_limit()
        
        # 计算可用的token空间（保留10%的安全边际）
        available_tokens = int((context_limit - estimated_input_tokens) * 0.9)
        
        # 取配置的max_tokens和可用空间的较小值
        safe_max_tokens = min(self.config.max_tokens, max(available_tokens, 512))
        
        # 如果调整了max_tokens，记录日志
        if safe_max_tokens < self.config.max_tokens:
            logger.info(
                f"动态调整max_tokens: {self.config.max_tokens} -> {safe_max_tokens} "
                f"(输入≈{estimated_input_tokens} tokens, 上下文限制={context_limit})"
            )
        
        return safe_max_tokens

    def generate(self, prompt: str) -> Tuple[str, str]:
        """基于 Prompt 调用 LLM，返回 (reasoning, content)。
        
        Args:
            prompt: 完整的 Prompt（已包含系统提示、历史、当前输入等）
            
        Returns:
            (reasoning_content, response_content) - 推理链和回复内容
            
        注意:
            - reasoning_content: 某些模型支持（如 DeepSeek-R1）
            - response_content: 实际的回复内容
        """
        messages = [{"role": "user", "content": prompt}]
        
        try:
            # 动态计算安全的max_tokens
            safe_max_tokens = self._calculate_safe_max_tokens(messages)
            
            # 构造 extra_body 参数
            extra_body = {
                "top_k": self.config.top_k,
            }
            
            # 关闭思考过程显示（机器人回复不显示推理）
            extra_body["chat_template_kwargs"] = {"enable_thinking": False}

            # 调用 OpenAI Chat Completions API
            response = self._client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=safe_max_tokens,  # 使用动态计算的值
                stream=False,  # 显式禁用流式传输
                extra_body=extra_body,
            )
        except Exception as e:
            # 包装异常，提供更清晰的错误信息
            logger.error(f"LLM API调用失败: {str(e)}", exc_info=True)
            raise RuntimeError(
                f"调用 LLM API 失败 (model: {self.config.model}): {str(e)}"
            ) from e

        # 检查响应是否有效
        if not response.choices:
            raise ValueError(
                f"API 返回空的 choices (model: {self.config.model})"
            )

        # 提取消息内容
        choice = response.choices[0].message

        if not choice:
            raise ValueError(
                f"API 返回无效的 message (model: {self.config.model})"
            )

        # 提取推理链（某些模型支持）
        reasoning_content = getattr(choice, "reasoning_content", "") or ""

        # 提取回复内容
        content = choice.content

        # 处理可能的列表格式（某些模型返回多模态内容）
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )

        # 确保返回字符串
        if content is None:
            final_text = ""
        elif isinstance(content, str):
            final_text = self._strip_thinking(content)
        else:
            final_text = self._strip_thinking(str(content))

        return str(reasoning_content), final_text

    async def generate_async(self, prompt: str) -> Tuple[str, str]:
        """异步版本的 generate（当前简单封装同步版本）。
        
        注意: 实际生产环境应使用 AsyncOpenAI
        """
        return self.generate(prompt)
    
    def chat(self, messages: list, temperature: float = None) -> str:
        """基于消息列表调用 LLM（同步版本）。
        
        Args:
            messages: 消息列表，格式为 [{"role": "system/user/assistant", "content": "..."}]
            temperature: 温度参数（可选，默认使用配置值）
            
        Returns:
            助手的回复内容
        """
        try:
            # 使用配置的温度或传入的温度
            temp = temperature if temperature is not None else self.config.temperature
            
            # 动态计算安全的max_tokens
            safe_max_tokens = self._calculate_safe_max_tokens(messages)
            
            # 构造 extra_body 参数
            extra_body = {
                "top_k": self.config.top_k,
            }
            
            # 关闭思考过程显示
            extra_body["chat_template_kwargs"] = {"enable_thinking": False}

            # 调用 OpenAI Chat Completions API
            response = self._client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=temp,
                max_tokens=safe_max_tokens,  # 使用动态计算的值
                stream=False,  # 显式禁用流式传输
                extra_body=extra_body,
            )
        except Exception as e:
            logger.error(f"LLM API调用失败: {str(e)}", exc_info=True)
            raise RuntimeError(
                f"调用 LLM API 失败 (model: {self.config.model}): {str(e)}"
            ) from e

        # 检查响应是否有效
        if not response.choices:
            raise ValueError(
                f"API 返回空的 choices (model: {self.config.model})"
            )

        # 提取消息内容
        choice = response.choices[0].message
        
        if not choice:
            raise ValueError(
                f"API 返回无效的 message (model: {self.config.model})"
            )

        # 提取回复内容
        content = choice.content

        # 处理可能的列表格式
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )

        # 确保返回字符串
        if content is None:
            return ""
        elif isinstance(content, str):
            return self._strip_thinking(content)
        else:
            return self._strip_thinking(str(content))
    
    async def chat_async(self, messages: list, temperature: float = None) -> str:
        """基于消息列表调用 LLM（异步版本）。
        
        Args:
            messages: 消息列表，格式为 [{"role": "system/user/assistant", "content": "..."}]
            temperature: 温度参数（可选，默认使用配置值）
            
        Returns:
            助手的回复内容
            
        注意: 当前简单封装同步版本，实际生产环境应使用 AsyncOpenAI
        """
        return self.chat(messages, temperature)
