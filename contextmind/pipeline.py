"""
Pipeline Module - Unified Context Processing Pipeline

Merged from:
- processing/preprocessor.py (InputPreprocessor)
- processing/postprocessor.py (PostProcessor)
- processing/compressor.py (ContextCompressor)
- processing/reorderer.py (ContextReorderer)
"""

import re
from typing import List, Optional, Dict, Any
from abc import ABC, abstractmethod
import logging

from .models import (
    ContextResult,
    ProcessedContext,
    get_logger,
)
from .strategies.defaults import CompressionStrategy, RerankingStrategy

logger = get_logger(__name__)

# ============================================================================
# InputPreprocessor - Input Processing
# ============================================================================

class InputPreprocessor:
    """
    输入预处理器
    
    对用户输入进行标准化处理：
    - 去除多余空白
    - 验证有效性
    - 清洗特殊字符
    """
    
    def __init__(
        self,
        min_length: int = 1,
        max_length: int = 10000,
    ):
        """
        初始化预处理器
        
        Args:
            min_length: 最小输入长度
            max_length: 最大输入长度
        """
        self.min_length = min_length
        self.max_length = max_length
    
    async def process(self, user_input: str) -> str:
        """
        处理用户输入
        
        Args:
            user_input: 原始输入
            
        Returns:
            处理后的输入
            
        Raises:
            ValueError: 输入无效
        """
        # 去除首尾空白
        processed = user_input.strip()
        
        # 验证长度
        if len(processed) < self.min_length:
            raise ValueError(f"输入过短 (最小 {self.min_length} 字符)")
        
        if len(processed) > self.max_length:
            raise ValueError(f"输入过长 (最大 {self.max_length} 字符)")
        
        # 移除多余空白
        processed = re.sub(r'\s+', ' ', processed)
        
        logger.debug(f"预处理输入: '{processed[:50]}...'")
        
        return processed


# ============================================================================
# PostProcessor - Output Processing
# ============================================================================

class PostProcessorStrategy(ABC):
    """后处理策略基类"""
    
    @abstractmethod
    async def process(self, raw_output: str, context: Optional[ContextResult] = None) -> str:
        """
        处理 LLM 原始输出
        
        Args:
            raw_output: LLM 原始输出
            context: 上下文结果 (可选, 用于事实验证等)
            
        Returns:
            处理后的输出
        """
        pass


class RuleBasedPostProcessor(PostProcessorStrategy):
    """
    基于规则的后处理器
    
    使用正则表达式和规则进行格式修正、一致性检查
    轻量级, 适合大多数场景
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化规则后处理器
        
        Args:
            config: 配置字典, 可包含:
                - fix_markdown: 是否修复 Markdown 格式
                - remove_duplicates: 是否移除重复句子
                - max_length: 最大输出长度
                - strip_whitespace: 是否清理多余空白
        """
        self.config = config or {}
        self.fix_markdown = self.config.get('fix_markdown', True)
        self.remove_duplicates = self.config.get('remove_duplicates', True)
        self.max_length = self.config.get('max_length', None)
        self.strip_whitespace = self.config.get('strip_whitespace', True)
    
    async def process(self, raw_output: str, context: Optional[ContextResult] = None) -> str:
        """处理输出"""
        logger.debug("[PostProcessor] 开始基于规则的后处理")
        
        output = raw_output
        
        # 1. 清理多余空白
        if self.strip_whitespace:
            output = self._strip_excess_whitespace(output)
        
        # 2. 修复markdown格式
        if self.fix_markdown:
            output = self._fix_markdown(output)
        
        # 3. 移除重复句子
        if self.remove_duplicates:
            output = self._remove_duplicate_sentences(output)
        
        # 4. 长度限制
        if self.max_length and len(output) > self.max_length:
            output = output[:self.max_length] + "..."
            logger.debug(f"[PostProcessor] 输出被截断到 {self.max_length} 字符")
        
        logger.debug(f"[PostProcessor] 后处理完成 ({len(raw_output)} → {len(output)} 字符)")
        
        return output
    
    def _strip_excess_whitespace(self, text: str) -> str:
        """清理多余空白"""
        # 移除行首行尾空白
        text = '\n'.join(line.strip() for line in text.split('\n'))
        # 合并多个连续空行为一个
        text = re.sub(r'\n\n+', '\n\n', text)
        # 移除开头和结尾的空行
        text = text.strip()
        return text
    
    def _fix_markdown(self, text: str) -> str:
        """修复常见 Markdown 格式问题"""
        # 确保标题前后有空行
        text = re.sub(r'([^\n])(#{1,6} )', r'\1\n\n\2', text)
        text = re.sub(r'(#{1,6} [^\n]+)([^\n])', r'\1\n\n\2', text)
        
        # 确保列表项前有空行（如果不是第一项）
        text = re.sub(r'([^\n\-\*])\n([\-\*] )', r'\1\n\n\2', text)
        
        # 确保代码块前后有空行
        text = re.sub(r'([^\n])(\n```)', r'\1\n\2', text)
        text = re.sub(r'(```\n)([^\n])', r'\1\n\2', text)
        
        return text
    
    def _remove_duplicate_sentences(self, text: str) -> str:
        """移除重复的连续句子"""
        sentences = re.split(r'([。！？.!?])', text)
        
        # 重组句子（包含标点）
        full_sentences = []
        for i in range(0, len(sentences) - 1, 2):
            if i + 1 < len(sentences):
                full_sentences.append(sentences[i] + sentences[i + 1])
        
        # 移除连续重复
        deduplicated = []
        prev = None
        for sent in full_sentences:
            if sent.strip() != prev:
                deduplicated.append(sent)
                prev = sent.strip()
        
        return ''.join(deduplicated)


class PostProcessor:
    """
    后处理器主类
    
    协调不同的后处理策略，提供统一接口。
    """
    
    def __init__(self, strategy: Optional[PostProcessorStrategy] = None):
        """
        初始化后处理器
        
        Args:
            strategy: 后处理策略, 默认使用 RuleBasedPostProcessor
        """
        self.strategy = strategy or RuleBasedPostProcessor()
        logger.info(f"[PostProcessor] 初始化完成 - 策略: {self.strategy.__class__.__name__}")
    
    async def process(self, raw_output: str, context: Optional[ContextResult] = None) -> str:
        """
        处理 LLM 原始输出
        
        Args:
            raw_output: LLM 原始输出
            context: 上下文结果 (可选)
            
        Returns:
            处理后的输出
        """
        if not raw_output:
            logger.warning("[PostProcessor] 输入为空，跳过后处理")
            return raw_output
        
        logger.info("")
        logger.info("=" * 100)
        logger.info("[PostProcessor] ========== 开始输出后处理 ==========")
        logger.debug(f"[PostProcessor] 原始输出长度: {len(raw_output)} 字符")
        logger.info("=" * 100)
        logger.info("")
        
        processed = await self.strategy.process(raw_output, context)
        
        logger.info("")
        logger.info("-" * 100)
        logger.info(f"[PostProcessor] ✓ 后处理完成 ({len(raw_output)} → {len(processed)} 字符)")
        logger.info("-" * 100)
        logger.info("")
        
        return processed


# ============================================================================
# ContextCompressor - Context Compression
# ============================================================================

# 默认最大 Session 项数量 (用于向后兼容)
DEFAULT_MAX_SESSION_ITEMS = 10


class ContextCompressor:
    """
    上下文压缩器
    
    将收集到的上下文进行压缩以减少Token消耗：
    - 滑动窗口策略
    - 摘要生成
    - 智能过滤
    """
    
    def __init__(
        self,
        strategy: Optional[CompressionStrategy] = None,
        max_session_items: int = 10,
    ):
        """
        初始化压缩器
        
        Args:
            strategy: 压缩策略（可插拔）
            max_session_items: 最大会话条目数
        """
        self.strategy = strategy or CompressionStrategy(
            max_items=max_session_items
        )
    
    async def compress(
        self,
        context: ProcessedContext,
    ) -> ContextResult:
        """
        压缩上下文
        
        这是 pipeline 的最后一步，将 ProcessedContext 转换为 ContextResult。
        
        Args:
            context: 待压缩的上下文（ProcessedContext）
            
        Returns:
            压缩后的结果（ContextResult）
            
        Note:
            策略的 optimize() 方法已经负责转换为 ContextResult，
            这里直接返回策略的结果即可。
        """
        # 记录压缩前的信息
        input_items_count = len(context.items)
        
        # 委托给压缩策略 (策略会返回 ContextResult)
        result = await self.strategy.optimize(context)
        
        # 使用 ContextResult 的属性记录日志
        logger.debug(
            f"压缩上下文: "
            f"{input_items_count} 项 → "
            f"{len(result.recent_history)} 历史 + "
            f"{len(result.long_term_memory)} 记忆 + "
            f"{len(result.external_knowledge)} 知识"
        )
        
        return result


# ============================================================================
# ContextReorderer - Context Reordering
# ============================================================================

class ContextReorderer:
    """
    上下文重排序器
    
    对上下文进行重排序以突出关键信息:
    - 按时间戳排序
    - 按来源优先级排序
    - 按相关性评分排序 (预留)
    """
    
    def __init__(
        self,
        strategy: Optional[RerankingStrategy] = None,
    ):
        """
        初始化重排序器
        
        Args:
            strategy: 重排序策略 (可插拔)
        """
        self.strategy = strategy or RerankingStrategy()
    
    async def reorder(
        self,
        context: ProcessedContext,
    ) -> ProcessedContext:
        """
        重排序上下文
        
        Args:
            context: 待重排序的上下文
            
        Returns:
            重排序后的上下文
        """
        # 委托给重排序策略
        reordered = await self.strategy.optimize(context)
        
        logger.debug(f"重排序 {len(reordered.items)} 个上下文项")
        
        return reordered
