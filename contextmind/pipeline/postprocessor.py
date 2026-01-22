"""
PostProcessor - 输出后处理模块

对 LLM 生成的原始输出进行精炼、一致性检查和修正
保障响应格式正确、事实可靠、自洽, 提升用户体验

常用方法:
- 基于规则: 格式修正、正则检查
- 高端版: Self-Refine (LLM 自洽性精炼)、事实验证
- 其他: Citation 生成 (RAG 来源标注)
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import re
import logging

from contextmind.models import ContextResult

logger = logging.getLogger(__name__)


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
