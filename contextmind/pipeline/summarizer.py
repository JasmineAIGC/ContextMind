"""
Summarizer 模块 - 统一的对话摘要

合并自:
- processing/summarizer/base.py (SummarizerStrategy, ConversationSummarizer)
- processing/summarizer/rule.py (RuleBasedSummarizer)
- processing/summarizer/llm.py (LLMBasedSummarizer)
"""

from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from dataclasses import dataclass

from ..core.data_models import Message, ContextItem
from ..core.types import MessageRole
from ..utils.logger import get_logger
from ..core.strategies import SummarizerStrategy  # 使用核心基类

logger = get_logger(__name__)

# ============================================================================
# 配置
# ============================================================================

@dataclass
class SummarizationConfig:
    """对话摘要配置"""
    
    # 触发条件
    summarize_threshold: int = 5  # 触发摘要的对话轮数阈值（已从15降低到5）
    keep_recent_turns: int = 3  # 摘要后保留的最近对话轮数（已从5降低到3）
    
    # 摘要方式
    method: str = "llm"  # 'rule' 或 'llm'（推荐使用llm以获得更好质量）
    
    # 规则摘要配置
    max_summary_length: int = 200  # 最大摘要长度（字符）
    extract_key_points: bool = True  # 是否提取关键点
    max_topics: int = 5  # 最多提取的话题数
    topic_length: int = 50  # 每个话题的最大长度
    include_stats: bool = True  # 是否包含统计信息
    
    # LLM摘要配置（如果使用LLM）
    llm_max_tokens: int = 150  # LLM摘要最大token数
    llm_temperature: float = 0.3  # LLM温度（越低越稳定）


# ============================================================================
# RuleBasedSummarizer - 基于规则的摘要
# ============================================================================

class RuleBasedSummarizer(SummarizerStrategy):
    """
    基于规则的摘要器
    
    使用统计信息和关键词提取生成摘要
    轻量级, 适合快速摘要
    
    ⚠️ 已弃用：推荐使用 LLMBasedSummarizer 以获得更好的摘要质量
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


# ============================================================================
# LLMBasedSummarizer - 基于LLM的摘要
# ============================================================================

class LLMBasedSummarizer(SummarizerStrategy):
    """
    基于LLM的摘要器（推荐使用）
    
    ✨ 使用LLM的语义理解能力生成高质量摘要
    📊 能够智能提取关键信息和主题
    
    相比规则摘要（RuleBasedSummarizer），LLM摘要器能够：
    1. ✅ 理解对话的语义和上下文
    2. ✅ 识别隐含的主题和意图
    3. ✅ 生成流畅自然的摘要文本
    4. ✅ 自动提取关键点和要点
    5. ✅ 更高的准确性和可读性
    """
    
    def __init__(
        self,
        llm_client: Optional[any] = None,
        config: Optional[Any] = None
    ):
        """
        初始化LLM摘要器
        
        Args:
            llm_client: LLM客户端（需要有generate方法）
            config: 配置，可以是 SummarizationConfig 或字典
        """
        self.llm_client = llm_client
        
        # 支持 SummarizationConfig 或 dict
        if isinstance(config, SummarizationConfig):
            self.max_summary_length = config.max_summary_length
            self.llm_max_tokens = config.llm_max_tokens
            self.llm_temperature = config.llm_temperature
        else:
            self.config = config or {}
            self.max_summary_length = self.config.get('max_summary_length', 200)
            self.llm_max_tokens = self.config.get('llm_max_tokens', 150)
            self.llm_temperature = self.config.get('llm_temperature', 0.3)
        
        if llm_client:
            logger.info("[LLMBasedSummarizer] 初始化完成 - 使用LLM智能摘要")
        else:
            logger.warning("[LLMBasedSummarizer] 未提供LLM客户端 - 将回退到规则摘要")
    
    async def summarize(
        self,
        messages: List[Message],
        existing_summary: Optional[str] = None
    ) -> str:
        """
        使用LLM生成摘要
        
        Args:
            messages: 消息列表
            existing_summary: 已有摘要 (用于增量更新)
            
        Returns:
            摘要文本
        """
        # 如果没有LLM客户端，返回简单的统计信息
        if not self.llm_client:
            logger.warning("[LLMBasedSummarizer] ⚠️ 无LLM客户端，无法生成摘要")
            return f"对话包含 {len(messages)} 条消息（摘要功能需要LLM客户端）"
        
        if not messages:
            return "暂无对话历史"
        
        logger.info(f"[LLMBasedSummarizer] 开始LLM摘要生成 - 处理 {len(messages)} 条消息")
        
        # 构建对话文本
        conversation_text = self._build_conversation_text(messages)
        
        # 构建prompt
        system_prompt = """你是一个专业的对话摘要助手。请从对话中提取关键信息并生成简洁的摘要。

**摘要要求**:
1. 提取对话的核心主题和关键信息
2. 使用简洁清晰的语言
3. 保留重要细节（如时间、地点、人物、计划等）
4. 按时间顺序组织信息
5. 每个要点单独成行，使用数字编号

**摘要格式**:
```
对话轮次: X 轮
1. 第一个关键点
2. 第二个关键点
...
```

**注意事项**:
- **只提取用户相关的重要信息（用户的偏好、需求、计划、个人信息等）**
- **不要提取助手/机器人的信息（如助手的自我介绍、助手的能力等）**
- 忽略简单的问候和确认
- 合并重复或相似的信息
- 保持客观，不添加主观评价
- 摘要应该以用户为中心，记录用户说了什么、想要什么"""
        
        # 如果有已存在的摘要，说明这是增量更新
        if existing_summary:
            user_prompt = f"""请基于以下已有摘要和新对话，生成更新后的完整摘要：

已有摘要：
{existing_summary}

新对话：
{conversation_text}

请生成合并后的完整摘要，保持简洁清晰。"""
        else:
            user_prompt = f"""请对以下对话生成摘要：

{conversation_text}

请生成简洁清晰的摘要。"""
        
        # 合并为完整prompt
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        # 调用LLM
        try:
            if hasattr(self.llm_client, 'generate_async'):
                # 异步调用
                _, summary = await self.llm_client.generate_async(full_prompt)
            elif hasattr(self.llm_client, 'generate'):
                # 同步调用（返回 reasoning, content 元组）
                _, summary = self.llm_client.generate(full_prompt)
            else:
                raise ValueError("LLM客户端缺少generate或generate_async方法")
            
            # 清理摘要文本
            summary = summary.strip()
            
            # 截断过长的摘要
            if len(summary) > self.max_summary_length * 2:  # 给LLM摘要更多空间
                summary = summary[:self.max_summary_length * 2] + "..."
            
            logger.info(f"[LLMBasedSummarizer] LLM摘要生成完成 - 长度: {len(summary)}")
            return summary
            
        except Exception as e:
            logger.error(f"[LLMBasedSummarizer] ⚠️ LLM调用失败: {e}")
            # 返回错误信息而不是回退到规则摘要
            return f"摘要生成失败（包含 {len(messages)} 条消息）: {str(e)[:100]}"
    
    def _build_conversation_text(self, messages: List[Message]) -> str:
        """构建对话文本用于LLM摘要"""
        lines = []
        for msg in messages:
            role_name = "用户" if msg.role == MessageRole.USER else "助手"
            lines.append(f"{role_name}: {msg.content}")
        return "\n".join(lines)


# ============================================================================
# ConversationSummarizer - 主摘要器类
# ============================================================================

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
            strategy: 摘要策略（已废弃，使用 config.method 代替）
            config: 摘要配置（SummarizationConfig），优先级高于 strategy
            window_size: 摘要窗口大小 (消息条数)
            llm_client: LLM客户端（强烈推荐，用于高质量摘要）
        """
        self.config = config or SummarizationConfig()
        self.llm_client = llm_client
        
        # 如果提供了config，根据method选择strategy
        if config:
            if config.method == "llm" and llm_client:
                logger.info("[Summarizer] ✅ 使用基于大语言模型的摘要策略")
                self.strategy = LLMBasedSummarizer(llm_client, config)
            else:
                if config.method == "llm" and not llm_client:
                    logger.error("[Summarizer] ⚠️ LLM摘要需要llm_client，摘要功能将被禁用")
                    self.strategy = None
                else:
                    logger.warning("[Summarizer] ⚠️ 不支持的摘要方法，摘要功能将被禁用")
                    self.strategy = None
        else:
            if llm_client:
                logger.info("[Summarizer] ✅ 默认使用基于大语言模型的摘要策略")
                self.strategy = LLMBasedSummarizer(llm_client, self.config)
            else:
                logger.warning("[Summarizer] ⚠️ 未提供llm_client，摘要功能将被禁用")
                self.strategy = strategy  # 可能是 None
        
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
        return history_length >= self.config.summarize_threshold
    
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
        
        # 检查策略是否可用
        if self.strategy is None:
            logger.warning("[Summarizer] ⚠️ 摘要策略未初始化（可能缺少LLM客户端），无法生成摘要")
            return f"对话包含 {len(messages)} 条消息（摘要功能需要LLM客户端）"
        
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
            current_turn: 当前轮数（实际session轮数，用于摘要判断）
            
        Returns:
            (摘要文本, 最近对话列表)
            - 如果不需要摘要：返回 (None, all_history)
            - 如果需要摘要：返回 (合并的摘要文本, 最近N轮对话)
        """
        total_turns = len(all_history)
        
        # 使用实际轮数（current_turn）而非截断后的历史长度来判断
        # 这样才能正确触发摘要
        if current_turn is None:
            current_turn = total_turns
        
        # 第一步：检查是否需要开始摘要（使用实际轮数）
        if not self.should_summarize(current_turn):
            # 不需要摘要，返回所有历史
            logger.debug(f"[Summarizer] 当前{current_turn}轮，未达到摘要阈值{self.config.summarize_threshold}轮")
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
