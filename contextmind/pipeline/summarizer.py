"""
ConversationSummarizer - 对话摘要模块

从对话历史中提取和生成摘要，用于压缩上下文、快速理解对话内容。
支持规则-based和LLM-based两种摘要策略。

摘要类型：
- 短期摘要：最近N轮对话的总结
- 长期摘要：整个对话session的总结
- 增量摘要：随对话进行动态更新
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from contextmind.core.data_models import Message, MessageRole

logger = logging.getLogger(__name__)


class SummarizerStrategy(ABC):
    """摘要策略基类"""
    
    @abstractmethod
    async def summarize(
        self,
        messages: List[Message],
        existing_summary: Optional[str] = None
    ) -> str:
        """
        生成摘要
        
        Args:
            messages: 消息列表
            existing_summary: 已有摘要（用于增量更新）
            
        Returns:
            摘要文本
        """
        pass


class RuleBasedSummarizer(SummarizerStrategy):
    """
    基于规则的摘要器
    
    使用统计信息和关键词提取生成摘要。
    轻量级，适合快速摘要。
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化规则摘要器
        
        Args:
            config: 配置字典，可包含：
                - max_topics: 最多提取的话题数
                - topic_length: 每个话题的最大长度
                - include_stats: 是否包含统计信息
        """
        self.config = config or {}
        self.max_topics = self.config.get('max_topics', 5)
        self.topic_length = self.config.get('topic_length', 50)
        self.include_stats = self.config.get('include_stats', True)
    
    async def summarize(
        self,
        messages: List[Message],
        existing_summary: Optional[str] = None
    ) -> str:
        """生成规则-based摘要"""
        if not messages:
            return "暂无对话历史"
        
        summary_parts = []
        
        # 统计信息
        if self.include_stats:
            user_msgs = [m for m in messages if m.role == MessageRole.USER]
            assistant_msgs = [m for m in messages if m.role == MessageRole.ASSISTANT]
            
            summary_parts.append(f"对话轮次: {len(messages) // 2} 轮")
            summary_parts.append(f"用户消息: {len(user_msgs)} 条")
            summary_parts.append(f"助手回复: {len(assistant_msgs)} 条")
        
        # 提取关键话题（基于用户消息）
        user_msgs = [m for m in messages if m.role == MessageRole.USER]
        if user_msgs:
            recent_topics = []
            for msg in user_msgs[-self.max_topics:]:
                if len(msg.content) > 0:
                    topic = msg.content[:self.topic_length]
                    if len(msg.content) > self.topic_length:
                        topic += "..."
                    recent_topics.append(topic)
            
            if recent_topics:
                summary_parts.append(f"\n主要话题:")
                for i, topic in enumerate(recent_topics, 1):
                    summary_parts.append(f"  {i}. {topic}")
        
        # 合并已有摘要（如果是增量更新）
        if existing_summary:
            summary_parts.append(f"\n[历史摘要]: {existing_summary}")
        
        return "\n".join(summary_parts)


class ConversationSummarizer:
    """
    对话摘要器主类
    
    提供对话摘要功能，支持短期和长期摘要。
    """
    
    def __init__(
        self,
        strategy: Optional[SummarizerStrategy] = None,
        window_size: int = 10
    ):
        """
        初始化摘要器
        
        Args:
            strategy: 摘要策略，默认使用RuleBasedSummarizer
            window_size: 摘要窗口大小（消息条数）
        """
        self.strategy = strategy or RuleBasedSummarizer()
        self.window_size = window_size
        
        # 存储摘要
        self.current_summary: Optional[str] = None
        self.last_update: Optional[datetime] = None
        
        logger.info(f"[Summarizer] 初始化完成 - 策略: {self.strategy.__class__.__name__}, 窗口: {window_size}")
    
    async def generate_summary(
        self,
        messages: List[Message],
        incremental: bool = False
    ) -> str:
        """
        生成对话摘要
        
        Args:
            messages: 消息列表
            incremental: 是否增量更新（基于已有摘要）
            
        Returns:
            摘要文本
        """
        if not messages:
            logger.warning("[Summarizer] 消息列表为空")
            return "暂无对话历史"
        
        logger.info("")
        logger.info("=" * 100)
        logger.info("[Summarizer] ========== 开始生成对话摘要 ==========")
        logger.info(f"[Summarizer] 消息数: {len(messages)}, 增量模式: {incremental}")
        logger.info("=" * 100)
        logger.info("")
        
        # 选择要摘要的消息
        messages_to_summarize = messages[-self.window_size:] if len(messages) > self.window_size else messages
        
        # 生成摘要
        existing = self.current_summary if incremental else None
        summary = await self.strategy.summarize(messages_to_summarize, existing)
        
        # 更新存储的摘要
        self.current_summary = summary
        self.last_update = datetime.now()
        
        logger.info("[Summarizer] ✓ 摘要生成完成:")
        for line in summary.split('\n'):
            logger.info(f"  {line}")
        
        logger.info("")
        logger.info("-" * 100)
        logger.info("[Summarizer] ========== 摘要生成结束 ==========")
        logger.info("")
        
        return summary
    
    def get_current_summary(self) -> Optional[str]:
        """获取当前摘要"""
        return self.current_summary
    
    def clear_summary(self):
        """清空摘要"""
        logger.info("[Summarizer] 清空摘要")
        self.current_summary = None
        self.last_update = None
