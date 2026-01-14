"""
TokenizerService - 统一的Token计数服务

这是整个框架最关键的基础组件，确保：
1. Token计数的准确性（避免上下文溢出）
2. 所有截断操作基于Token ID而非字符数
3. 支持多种tokenizer（tiktoken, HuggingFace等）

Reference: https://github.com/openai/tiktoken
"""

from __future__ import annotations

from typing import Optional, List
from enum import Enum
import re

from ..logger import get_logger

logger = get_logger(__name__)


class TokenizerType(Enum):
    """Tokenizer类型"""
    TIKTOKEN_GPT35 = "gpt-3.5-turbo"
    TIKTOKEN_GPT4 = "gpt-4"
    TIKTOKEN_CL100K = "cl100k_base"
    HUGGINGFACE = "huggingface"
    SIMPLE = "simple"  # 简单的空格分词（用于测试）


class TokenizerService:
    """
    统一的Token计数服务
    
    核心功能：
    1. 准确的token计数
    2. 基于token的截断（而非字符）
    3. 支持多种tokenizer后端
    
    使用示例：
        ```python
        tokenizer = TokenizerService(model_name="gpt-3.5-turbo")
        
        # 计数
        count = tokenizer.count_tokens("Hello, world!")
        
        # 截断
        truncated = tokenizer.truncate("Long text...", max_tokens=100)
        
        # 编码/解码
        tokens = tokenizer.encode("Hello")
        text = tokenizer.decode(tokens)
        ```
    
    重要：所有的Pipeline组件都应该使用同一个TokenizerService实例，
          以确保token计数的一致性。
    """
    
    def __init__(
        self,
        model_name: str = "gpt-3.5-turbo",
        tokenizer_type: Optional[TokenizerType] = None,
    ):
        """
        初始化TokenizerService
        
        Args:
            model_name: 模型名称（用于tiktoken）
            tokenizer_type: Tokenizer类型（可选，自动推断）
        """
        self.model_name = model_name
        self.tokenizer_type = tokenizer_type or self._infer_type(model_name)
        self._tokenizer = None
        
        # 延迟初始化tokenizer
        self._initialize()
    
    def _infer_type(self, model_name: str) -> TokenizerType:
        """根据模型名称推断tokenizer类型"""
        if "gpt-4" in model_name.lower():
            return TokenizerType.TIKTOKEN_GPT4
        elif "gpt-3.5" in model_name.lower() or "gpt-35" in model_name.lower():
            return TokenizerType.TIKTOKEN_GPT35
        else:
            # 默认使用简单分词器
            return TokenizerType.SIMPLE
    
    def _initialize(self):
        """初始化底层tokenizer"""
        if self.tokenizer_type in [
            TokenizerType.TIKTOKEN_GPT35,
            TokenizerType.TIKTOKEN_GPT4,
            TokenizerType.TIKTOKEN_CL100K,
        ]:
            try:
                import tiktoken
                if self.tokenizer_type == TokenizerType.TIKTOKEN_CL100K:
                    self._tokenizer = tiktoken.get_encoding("cl100k_base")
                else:
                    self._tokenizer = tiktoken.encoding_for_model(self.model_name)
                logger.debug(f"Initialized tiktoken for {self.model_name}")
            except ImportError:
                logger.warning("tiktoken not installed, falling back to simple tokenizer")
                self.tokenizer_type = TokenizerType.SIMPLE
                self._tokenizer = None
            except Exception as e:
                logger.warning(f"Failed to initialize tiktoken: {e}, falling back to simple tokenizer")
                self.tokenizer_type = TokenizerType.SIMPLE
                self._tokenizer = None
        
        elif self.tokenizer_type == TokenizerType.HUGGINGFACE:
            try:
                from transformers import AutoTokenizer
                self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                logger.debug(f"Initialized HuggingFace tokenizer for {self.model_name}")
            except ImportError:
                logger.warning("transformers not installed, falling back to simple tokenizer")
                self.tokenizer_type = TokenizerType.SIMPLE
                self._tokenizer = None
            except Exception as e:
                logger.warning(f"Failed to initialize HuggingFace tokenizer: {e}, falling back to simple tokenizer")
                self.tokenizer_type = TokenizerType.SIMPLE
                self._tokenizer = None
        
        # Simple tokenizer不需要初始化
        if self.tokenizer_type == TokenizerType.SIMPLE:
            logger.debug("Using simple whitespace tokenizer")
    
    def encode(self, text: str) -> List[int]:
        """
        编码文本为token IDs
        
        Args:
            text: 输入文本
            
        Returns:
            Token IDs列表
        """
        if not text:
            return []
        
        if self.tokenizer_type == TokenizerType.SIMPLE:
            # 简单分词：按空格分割
            return list(range(len(text.split())))
        
        if self._tokenizer is None:
            # Fallback
            return list(range(len(text.split())))
        
        try:
            if self.tokenizer_type in [
                TokenizerType.TIKTOKEN_GPT35,
                TokenizerType.TIKTOKEN_GPT4,
                TokenizerType.TIKTOKEN_CL100K,
            ]:
                return self._tokenizer.encode(text)
            elif self.tokenizer_type == TokenizerType.HUGGINGFACE:
                return self._tokenizer.encode(text, add_special_tokens=False)
        except Exception as e:
            logger.error(f"Encoding failed: {e}, using fallback")
            return list(range(len(text.split())))
        
        return []
    
    def decode(self, tokens: List[int]) -> str:
        """
        解码token IDs为文本
        
        Args:
            tokens: Token IDs列表
            
        Returns:
            解码后的文本
        """
        if not tokens:
            return ""
        
        if self.tokenizer_type == TokenizerType.SIMPLE:
            # Simple tokenizer无法准确解码，返回占位符
            return f"<{len(tokens)} tokens>"
        
        if self._tokenizer is None:
            return f"<{len(tokens)} tokens>"
        
        try:
            if self.tokenizer_type in [
                TokenizerType.TIKTOKEN_GPT35,
                TokenizerType.TIKTOKEN_GPT4,
                TokenizerType.TIKTOKEN_CL100K,
            ]:
                return self._tokenizer.decode(tokens)
            elif self.tokenizer_type == TokenizerType.HUGGINGFACE:
                return self._tokenizer.decode(tokens, skip_special_tokens=True)
        except Exception as e:
            logger.error(f"Decoding failed: {e}, using fallback")
            return f"<{len(tokens)} tokens>"
        
        return ""
    
    def count_tokens(self, text: str) -> int:
        """
        计算文本的token数量
        
        这是最常用的方法，确保准确的token计数。
        
        Args:
            text: 输入文本
            
        Returns:
            Token数量
        """
        if not text:
            return 0
        
        return len(self.encode(text))
    
    def truncate(
        self,
        text: str,
        max_tokens: int,
        add_ellipsis: bool = True,
    ) -> str:
        """
        基于token数截断文本（核心方法）
        
        重要：这是正确的截断方式！
        错误做法：text[:max_chars]  # 字符截断，不准确
        正确做法：tokenizer.truncate(text, max_tokens)  # Token截断
        
        Args:
            text: 输入文本
            max_tokens: 最大token数
            add_ellipsis: 是否添加省略号
            
        Returns:
            截断后的文本
        """
        if not text:
            return ""
        
        tokens = self.encode(text)
        
        if len(tokens) <= max_tokens:
            return text
        
        # 截断到max_tokens
        truncated_tokens = tokens[:max_tokens]
        truncated_text = self.decode(truncated_tokens)
        
        if add_ellipsis:
            truncated_text += "..."
        
        logger.debug(f"Truncated from {len(tokens)} to {max_tokens} tokens")
        
        return truncated_text
    
    def batch_count_tokens(self, texts: List[str]) -> List[int]:
        """
        批量计算token数量
        
        Args:
            texts: 文本列表
            
        Returns:
            Token数量列表
        """
        return [self.count_tokens(text) for text in texts]
    
    def estimate_tokens(self, text: str) -> int:
        """
        快速估算token数（近似值）
        
        用于不需要精确计数的场景，性能更高。
        规则：英文约4个字符=1 token，中文约1.5个字符=1 token
        
        Args:
            text: 输入文本
            
        Returns:
            估算的token数量
        """
        if not text:
            return 0
        
        # 简单的估算方法
        # 英文: ~4 chars per token
        # 中文: ~1.5 chars per token
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        other_chars = len(text) - chinese_chars
        
        estimated = chinese_chars / 1.5 + other_chars / 4
        return int(estimated)
