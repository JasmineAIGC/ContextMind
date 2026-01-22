"""
ConversationSummarizer - 对话摘要模块

从对话历史中提取和生成摘要, 用于压缩上下文、快速理解对话内容
支持基于规则和基于 LLM 两种摘要策略

摘要类型:
- 短期摘要: 最近 N 轮对话的总结
- 长期摘要: 整个对话 Session 的总结
- 增量摘要: 随对话进行动态更新
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from dataclasses import dataclass
import logging

from contextmind.models import Message, MessageRole, ContextItem, get_logger

logger = get_logger(__name__)


@dataclass
class SummarizationConfig:
    """对话摘要配置"""
    
    # 触发条件
    summarize_threshold: int = 15  # 触发摘要的对话轮数阈值
    keep_recent_turns: int = 5  # 摘要后保留的最近对话轮数
    
    # 摘要方式
    method: str = "rule"  # 'rule' 或 'llm'
    
    # 规则摘要配置
    max_summary_length: int = 200  # 最大摘要长度（字符）
    extract_key_points: bool = True  # 是否提取关键点
    max_topics: int = 5  # 最多提取的话题数
    topic_length: int = 50  # 每个话题的最大长度
    include_stats: bool = True  # 是否包含统计信息
    
    # LLM摘要配置（如果使用LLM）
    llm_max_tokens: int = 150  # LLM摘要最大token数
    llm_temperature: float = 0.3  # LLM温度（越低越稳定）


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
            existing_summary: 已有摘要 (用于增量更新)
            
        Returns:
            摘要文本
        """
        pass


class RuleBasedSummarizer(SummarizerStrategy):
    """
    基于规则的摘要器
    
    使用统计信息和关键词提取生成摘要
    轻量级, 适合快速摘要
    """
    
    def __init__(self, config: Optional[Any] = None):
        """
        初始化规则摘要器
        
        Args:
            config: 配置，可以是 SummarizationConfig 或字典，可包含:
                - max_topics: 最多提取的话题数
                - topic_length: 每个话题的最大长度
                - include_stats: 是否包含统计信息
        """
        # 支持 SummarizationConfig 或 dict
        if isinstance(config, SummarizationConfig):
            self.max_topics = config.max_topics
            self.topic_length = config.topic_length
            self.include_stats = config.include_stats
            self.max_summary_length = config.max_summary_length
            self.extract_key_points = config.extract_key_points
        else:
            self.config = config or {}
            self.max_topics = self.config.get('max_topics', 5)
            self.topic_length = self.config.get('topic_length', 50)
            self.include_stats = self.config.get('include_stats', True)
            self.max_summary_length = self.config.get('max_summary_length', 200)
            self.extract_key_points = self.config.get('extract_key_points', True)
    
    async def summarize(
        self,
        messages: List[Message],
        existing_summary: Optional[str] = None
    ) -> str:
        """生成基于规则的摘要"""
        if not messages:
            return "暂无对话历史"
        
        summary_parts = []
        
        # 统计信息
        if self.include_stats:
            user_msgs = [m for m in messages if m.role == MessageRole.USER]
            assistant_msgs = [m for m in messages if m.role == MessageRole.ASSISTANT]
            
            summary_parts.append(f"对话轮次: {len(messages) // 2} 轮")
        
        # 提取关键点（如果启用）
        if self.extract_key_points:
            key_points = []
            user_msgs = [m for m in messages if m.role == MessageRole.USER]
            
            for msg in user_msgs:
                content = msg.content
                
                # 跳过太短的对话
                if len(content) < 10:
                    continue
                
                # 自我介绍相关
                if any(keyword in content for keyword in ["我是", "我叫", "我的", "我在"]):
                    key_points.append(content.strip())
                
                # 偏好相关
                elif any(keyword in content for keyword in ["喜欢", "不喜欢", "偏好", "想要", "需要", "希望"]):
                    key_points.append(content.strip())
                
                # 事实陈述
                elif any(keyword in content for keyword in ["是", "有", "没有", "已经", "正在"]):
                    key_points.append(content.strip())
            
            # 去重并限制数量
            seen = set()
            unique_points = []
            for point in key_points:
                # 简单的去重：检查前30个字符
                key = point[:30]
                if key not in seen:
                    seen.add(key)
                    unique_points.append(point)
            
            # 添加关键点
            if unique_points:
                for i, point in enumerate(unique_points[:8], 1):  # 最多8个要点
                    if len(point) > 50:
                        point = point[:50] + "..."
                    summary_parts.append(f"{i}. {point}")
        
        # 提取最近话题（原有逻辑）
        if not self.extract_key_points:
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
        
        # 合并已有摘要 (如果是增量更新)
        if existing_summary:
            summary_parts.append(f"\n[历史摘要]: {existing_summary}")
        
        summary = "\n".join(summary_parts) if summary_parts else "暂无对话历史"
        
        # 截断过长的摘要
        if len(summary) > self.max_summary_length:
            summary = summary[:self.max_summary_length] + "..."
        
        return summary


class ConversationSummarizer:
    """
    对话摘要器主类
    
    提供对话摘要功能, 支持短期和长期摘要
    支持增量摘要模式，避免信息丢失
    """
    
    def __init__(
        self,
        strategy: Optional[SummarizerStrategy] = None,
        config: Optional[SummarizationConfig] = None,
        window_size: int = 10,
        llm_client = None
    ):
        """
        初始化摘要器
        
        Args:
            strategy: 摘要策略, 默认使用 RuleBasedSummarizer
            config: 摘要配置（SummarizationConfig），优先级高于 strategy
            window_size: 摘要窗口大小 (消息条数)
            llm_client: LLM客户端（仅当使用LLM摘要时需要）
        """
        self.config = config or SummarizationConfig()
        self.llm_client = llm_client
        
        # 如果提供了config，根据method选择strategy
        if config:
            if config.method == "llm" and llm_client:
                # TODO: 实现LLM策略
                logger.warning("[Summarizer] LLM摘要策略未实现，使用规则摘要")
                self.strategy = RuleBasedSummarizer(config)
            else:
                self.strategy = RuleBasedSummarizer(config)
        else:
            self.strategy = strategy or RuleBasedSummarizer()
        
        self.window_size = window_size
        
        # 增量摘要存储
        self.base_summary: Optional[str] = None  # 基础摘要（最早的对话）
        self.incremental_summaries: List[str] = []  # 增量摘要列表
        self.last_summarized_turn: int = 0  # 上次摘要到的轮数
        self.last_update: Optional[datetime] = None
        
        # 增量摘要配置
        self.increment_interval: int = 5  # 每5轮生成一次增量摘要
        self.consolidate_threshold: int = 3  # 有3个增量摘要时合并到基础摘要
        
        logger.info(f"[Summarizer] 初始化完成 - 策略: {self.strategy.__class__.__name__}, 窗口: {window_size}, 增量模式启用")
    
    def should_summarize(self, history_length: int) -> bool:
        """判断是否需要生成摘要
        
        Args:
            history_length: 对话历史长度（轮数）
            
        Returns:
            是否需要摘要
        """
        return history_length > self.config.summarize_threshold
    
    def should_create_incremental_summary(self, current_turn: int) -> bool:
        """判断是否需要生成增量摘要
        
        Args:
            current_turn: 当前轮数
            
        Returns:
            是否需要生成增量摘要
        """
        # 如果还没有基础摘要，不生成增量
        if self.base_summary is None:
            return False
        
        # 检查是否到达增量间隔
        turns_since_last = current_turn - self.last_summarized_turn
        return turns_since_last >= self.increment_interval
    
    async def generate_summary(
        self,
        messages: List[Message],
        incremental: bool = False
    ) -> str:
        """
        生成对话摘要
        
        Args:
            messages: 消息列表
            incremental: 是否增量更新 (基于已有摘要)
            
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
        existing = self.get_combined_summary() if incremental else None
        summary = await self.strategy.summarize(messages_to_summarize, existing)
        
        # 更新存储的摘要（兼容旧代码）
        self.last_update = datetime.now()
        
        logger.info("[Summarizer] ✓ 摘要生成完成:")
        for line in summary.split('\n'):
            logger.info(f"  {line}")
        
        logger.info("")
        logger.info("-" * 100)
        logger.info("[Summarizer] ========== 摘要生成结束 ==========")
        logger.info("")
        
        return summary
    
    async def create_base_summary(self, messages: List[Message], turns: int):
        """创建基础摘要
        
        Args:
            messages: 要摘要的消息列表
            turns: 摘要覆盖的轮数
        """
        logger.info(f"[Summarizer] 创建基础摘要 (轮数: {turns})")
        self.base_summary = await self.generate_summary(messages, incremental=False)
        self.last_summarized_turn = turns
        logger.info(f"[Summarizer] ✓ 基础摘要已创建，覆盖到第{turns}轮")
    
    async def create_incremental_summary(self, messages: List[Message], turns: int):
        """创建增量摘要
        
        Args:
            messages: 新的消息列表
            turns: 当前轮数
        """
        logger.info(f"[Summarizer] 创建增量摘要 (轮数: {self.last_summarized_turn}→{turns})")
        increment = await self.generate_summary(messages, incremental=False)
        self.incremental_summaries.append(increment)
        self.last_summarized_turn = turns
        
        logger.info(f"[Summarizer] ✓ 增量摘要已添加 (共{len(self.incremental_summaries)}个增量)")
        
        # 检查是否需要合并
        if len(self.incremental_summaries) >= self.consolidate_threshold:
            await self.consolidate_summaries()
    
    async def consolidate_summaries(self):
        """合并所有增量摘要到基础摘要"""
        if not self.incremental_summaries:
            return
        
        logger.info(f"[Summarizer] 🔄 合并摘要: 基础摘要 + {len(self.incremental_summaries)}个增量")
        
        # 创建合并后的摘要文本
        all_parts = [self.base_summary] + self.incremental_summaries
        combined_text = "\n\n".join(f"[阶段{i+1}] {part}" for i, part in enumerate(all_parts))
        
        # 使用策略重新生成更紧凑的摘要
        # 创建临时消息列表（用于模拟）
        temp_messages = [Message(role=MessageRole.ASSISTANT, content=combined_text)]
        new_base = await self.strategy.summarize(temp_messages, None)
        
        # 更新基础摘要，清空增量列表
        self.base_summary = new_base
        self.incremental_summaries = []
        
        logger.info("[Summarizer] ✓ 摘要合并完成，增量列表已清空")
    
    def get_combined_summary(self) -> Optional[str]:
        """获取合并后的完整摘要
        
        Returns:
            合并了基础摘要和所有增量的完整摘要
        """
        if self.base_summary is None:
            return None
        
        if not self.incremental_summaries:
            return self.base_summary
        
        # 返回格式化的组合摘要
        parts = [f"[基础] {self.base_summary}"]
        for i, inc in enumerate(self.incremental_summaries, 1):
            parts.append(f"[增量{i}] {inc}")
        
        return "\n\n".join(parts)
    
    def get_current_summary(self) -> Optional[str]:
        """获取当前摘要（兼容旧接口）"""
        return self.get_combined_summary()
    
    def clear_summary(self):
        """清空所有摘要"""
        logger.info("[Summarizer] 清空所有摘要")
        self.base_summary = None
        self.incremental_summaries = []
        self.last_summarized_turn = 0
        self.last_update = None
    
    async def get_summary_and_recent(
        self, 
        all_history: List[ContextItem],
        current_turn: int = None
    ) -> Tuple[Optional[str], List[ContextItem]]:
        """获取摘要和最近对话（使用增量摘要）
        
        根据配置自动判断是否需要摘要，并返回摘要和最近对话。
        支持增量摘要模式，避免信息丢失。
        
        Args:
            all_history: 所有对话历史（ContextItem列表）
            current_turn: 当前轮数（如果提供，用于增量判断）
            
        Returns:
            (摘要文本, 最近对话列表)
            - 如果不需要摘要：返回 (None, all_history)
            - 如果需要摘要：返回 (合并的摘要文本, 最近N轮对话)
        """
        total_turns = len(all_history)
        if current_turn is None:
            current_turn = total_turns
        
        # 第一步：检查是否需要开始摘要
        if not self.should_summarize(total_turns):
            # 不需要摘要，返回所有历史
            return None, all_history
        
        # 第二步：处理基础摘要
        if self.base_summary is None:
            # 首次创建基础摘要
            summary_turns = total_turns - self.config.keep_recent_turns
            if summary_turns > 0:
                messages_to_summarize = []
                for item in all_history[:summary_turns]:
                    messages_to_summarize.append(self._contextitem_to_message(item))
                
                await self.create_base_summary(messages_to_summarize, summary_turns)
                logger.info(f"[Summarizer] 📝 基础摘要已创建，覆盖第1-{summary_turns}轮")
        
        # 第三步：检查是否需要增量摘要
        elif self.should_create_incremental_summary(current_turn):
            # 创建增量摘要：从上次摘要位置到保留轮次之前
            start_turn = self.last_summarized_turn
            end_turn = total_turns - self.config.keep_recent_turns
            
            if end_turn > start_turn:
                messages_for_increment = []
                for item in all_history[start_turn:end_turn]:
                    messages_for_increment.append(self._contextitem_to_message(item))
                
                await self.create_incremental_summary(messages_for_increment, end_turn)
                logger.info(f"[Summarizer] 📝 增量摘要已创建，覆盖第{start_turn+1}-{end_turn}轮")
        
        # 第四步：返回组合摘要和最近对话
        combined_summary = self.get_combined_summary()
        recent_history = all_history[-self.config.keep_recent_turns:]
        
        logger.info(
            f"[Summarizer] 对话分层: "
            f"基础摘要(第1-{self.last_summarized_turn if self.base_summary else 0}轮) + "
            f"{len(self.incremental_summaries)}个增量 + "
            f"最近{len(recent_history)}轮原始对话"
        )
        
        return combined_summary, recent_history
    
    def _contextitem_to_message(self, item: ContextItem) -> Message:
        """将 ContextItem 转换为 Message（内部辅助方法）"""
        content = item.content
        
        # 解析content，提取role和内容
        if "user:" in content.lower():
            role = MessageRole.USER
            content = content.split(":", 1)[1].strip() if ":" in content else content
        elif "assistant:" in content.lower():
            role = MessageRole.ASSISTANT
            content = content.split(":", 1)[1].strip() if ":" in content else content
        else:
            # 默认为用户消息
            role = MessageRole.USER
        
        return Message(role=role, content=content)
