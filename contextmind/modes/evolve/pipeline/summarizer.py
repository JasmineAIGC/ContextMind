"""
Summarizer 模块 - 统一的对话摘要。
"""

from typing import List, Optional, Any, Tuple
from datetime import datetime

from ..core.data_models import Message, ContextItem
from ..core.config import MessageRole, SummarizationConfig
from contextmind.infra.logger import get_logger
from ..core.strategies import SummarizerStrategy  # 使用核心基类

logger = get_logger(__name__)


class RuleBasedSummarizer(SummarizerStrategy):
    """
    基于规则的摘要器，使用统计信息和关键词提取生成摘要。

    通过匹配预设的中文关键词识别用户偏好、身份、状态等要点，
    无需 LLM 推理，延迟极低，适合对话历史较短或无法提供 LLM 客户端的场景。
    推荐在生产中使用 LLMBasedSummarizer 获取语义更丰富的摘要。
    """

    def __init__(self, config: Optional[Any] = None):
        """
        Args:
            config: SummarizationConfig 或字典，支持 max_topics、topic_length、include_stats 等字段。
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

        if self.include_stats:
            user_msgs = [m for m in messages if m.role == MessageRole.USER]
            assistant_msgs = [m for m in messages if m.role == MessageRole.ASSISTANT]

            summary_parts.append(f"对话轮次: {len(messages) // 2} 轮")

        if self.extract_key_points:
            key_points = []
            user_msgs = [m for m in messages if m.role == MessageRole.USER]

            for msg in user_msgs:
                content = msg.content

                if len(content) < 10:
                    continue

                if any(keyword in content for keyword in ["我是", "我叫", "我的", "我在"]):
                    key_points.append(content.strip())

                elif any(keyword in content for keyword in ["喜欢", "不喜欢", "偏好", "想要", "需要", "希望"]):
                    key_points.append(content.strip())

                elif any(keyword in content for keyword in ["是", "有", "没有", "已经", "正在"]):
                    key_points.append(content.strip())

            seen = set()
            unique_points = []
            for point in key_points:
                key = point[:30]  # 以前30个字符作为去重键，避免相似句重复
                if key not in seen:
                    seen.add(key)
                    unique_points.append(point)

            if unique_points:
                for i, point in enumerate(unique_points[:8], 1):  # 最多8个要点
                    if len(point) > 50:
                        point = point[:50] + "..."
                    summary_parts.append(f"{i}. {point}")

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

        if existing_summary:
            summary_parts.append(f"\n[历史摘要]: {existing_summary}")

        summary = "\n".join(summary_parts) if summary_parts else "暂无对话历史"

        if len(summary) > self.max_summary_length:
            summary = summary[:self.max_summary_length] + "..."

        return summary


# ============================================================================
# LLMBasedSummarizer - 基于LLM的摘要
# ============================================================================

class LLMBasedSummarizer(SummarizerStrategy):
    """基于LLM的摘要器（推荐），使用语义理解生成高质量摘要。"""

    def __init__(
        self,
        llm_client: Optional[any] = None,
        config: Optional[Any] = None
    ):
        """
        Args:
            llm_client: LLM客户端（需要有 generate 或 generate_async 方法）
            config: SummarizationConfig 或字典
        """
        self.llm_client = llm_client

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
        使用LLM生成摘要。

        Args:
            messages: 消息列表
            existing_summary: 已有摘要（用于增量更新）

        Returns:
            摘要文本
        """
        if not self.llm_client:
            logger.warning("[LLMBasedSummarizer] ⚠️ 无LLM客户端，无法生成摘要")
            return f"对话包含 {len(messages)} 条消息（摘要功能需要LLM客户端）"

        if not messages:
            return "暂无对话历史"

        logger.info(f"[LLMBasedSummarizer] 开始LLM摘要生成 - 处理 {len(messages)} 条消息")

        conversation_text = self._build_conversation_text(messages)

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
        
        # 如果有已存在的摘要，将其作为前缀让 LLM 进行增量更新而非全量重写
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
        
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        try:
            if hasattr(self.llm_client, 'generate_async'):
                _, summary = await self.llm_client.generate_async(full_prompt)
            elif hasattr(self.llm_client, 'generate'):
                _, summary = self.llm_client.generate(full_prompt)
            else:
                raise ValueError("LLM客户端缺少generate或generate_async方法")

            summary = summary.strip()

            if len(summary) > self.max_summary_length * 2:  # LLM 输出通常比规则摘要更详细，给双倍空间
                summary = summary[:self.max_summary_length * 2] + "..."

            logger.info(f"[LLMBasedSummarizer] LLM摘要生成完成 - 长度: {len(summary)}")
            return summary

        except Exception as e:
            logger.error(f"[LLMBasedSummarizer] ⚠️ LLM调用失败: {e}")
            return f"摘要生成失败（包含 {len(messages)} 条消息）: {str(e)[:100]}"

    def _build_conversation_text(self, messages: List[Message]) -> str:
        lines = []
        for msg in messages:
            role_name = "用户" if msg.role == MessageRole.USER else "助手"
            lines.append(f"{role_name}: {msg.content}")
        return "\n".join(lines)


class ConversationSummarizer:
    """对话摘要器，支持短期/长期摘要及增量摘要模式。"""

    def __init__(
        self,
        config: Optional[SummarizationConfig] = None,
        window_size: int = 10,
        llm_client = None
    ):
        """
        Args:
            config: SummarizationConfig；未提供时使用默认配置。
            window_size: 摘要窗口大小（消息条数）。
            llm_client: LLM 客户端；不提供则回退到规则摘要。
        """
        self.config = config or SummarizationConfig()
        self.llm_client = llm_client

        if config:
            if config.method == "llm" and llm_client:
                logger.info("[Summarizer] ✅ 使用基于大语言模型的摘要策略")
                self.strategy = LLMBasedSummarizer(llm_client, config)
            elif config.method == "rule":
                logger.info("[Summarizer] ✅ 使用基于规则的摘要策略")
                self.strategy = RuleBasedSummarizer(config)
            else:
                if config.method == "llm" and not llm_client:
                    logger.error("[Summarizer] ⚠️ LLM摘要需要llm_client，回退到规则摘要")
                    self.strategy = RuleBasedSummarizer(config)
                else:
                    logger.warning("[Summarizer] ⚠️ 不支持的摘要方法，使用规则摘要作为默认")
                    self.strategy = RuleBasedSummarizer(config)
        else:
            if llm_client:
                logger.info("[Summarizer] ✅ 默认使用基于大语言模型的摘要策略")
                self.strategy = LLMBasedSummarizer(llm_client, self.config)
            else:
                logger.warning("[Summarizer] ⚠️ 未提供llm_client，使用规则摘要")
                self.strategy = RuleBasedSummarizer(self.config)
        
        self.window_size = window_size

        # 分层摘要状态：base_summary 覆盖早期对话，incremental_summaries 覆盖中间段
        self.base_summary: Optional[str] = None
        self.incremental_summaries: List[str] = []
        self.last_summarized_turn: int = 0
        self.last_update: Optional[datetime] = None

        self.increment_interval: int = 5   # 每5轮生成一次增量，避免频繁调用 LLM
        self.consolidate_threshold: int = 3  # 积累3个增量后合并，防止增量链过长导致上下文膨胀

        logger.info(f"[Summarizer] 初始化完成 - 策略: {self.strategy.__class__.__name__}, 窗口: {window_size}, 增量模式启用")

    def should_summarize(self, history_length: int) -> bool:
        """判断是否需要生成摘要。"""
        return history_length >= self.config.summarize_threshold

    def should_create_incremental_summary(self, current_turn: int) -> bool:
        """判断是否需要生成增量摘要。"""
        if self.base_summary is None:
            return False

        turns_since_last = current_turn - self.last_summarized_turn
        return turns_since_last >= self.increment_interval

    async def generate_summary(
        self,
        messages: List[Message],
        incremental: bool = False
    ) -> str:
        """
        生成对话摘要。

        Args:
            messages: 消息列表
            incremental: 是否增量更新（基于已有摘要）

        Returns:
            摘要文本
        """
        if not messages:
            logger.warning("[Summarizer] 消息列表为空")
            return "暂无对话历史"

        if self.strategy is None:
            logger.warning("[Summarizer] ⚠️ 摘要策略未初始化（可能缺少LLM客户端），无法生成摘要")
            return f"对话包含 {len(messages)} 条消息（摘要功能需要LLM客户端）"

        logger.info(f"[Summarizer] 开始生成对话摘要 - 消息数: {len(messages)}, 增量模式: {incremental}")

        messages_to_summarize = messages[-self.window_size:] if len(messages) > self.window_size else messages

        existing = self.get_combined_summary() if incremental else None
        summary = await self.strategy.summarize(messages_to_summarize, existing)

        self.last_update = datetime.now()

        logger.info(f"[Summarizer] ✓ 摘要生成完成 (长度: {len(summary)})")

        return summary

    async def create_base_summary(self, messages: List[Message], turns: int):
        """创建基础摘要。"""
        logger.info(f"[Summarizer] 创建基础摘要 (轮数: {turns})")
        self.base_summary = await self.generate_summary(messages, incremental=False)
        self.last_summarized_turn = turns
        logger.info(f"[Summarizer] ✓ 基础摘要已创建，覆盖到第{turns}轮")

    async def create_incremental_summary(self, messages: List[Message], turns: int):
        """创建增量摘要。"""
        logger.info(f"[Summarizer] 创建增量摘要 (轮数: {self.last_summarized_turn}→{turns})")
        increment = await self.generate_summary(messages, incremental=False)
        self.incremental_summaries.append(increment)
        self.last_summarized_turn = turns

        logger.info(f"[Summarizer] ✓ 增量摘要已添加 (共{len(self.incremental_summaries)}个增量)")

        if len(self.incremental_summaries) >= self.consolidate_threshold:
            await self.consolidate_summaries()

    async def consolidate_summaries(self):
        """合并所有增量摘要到基础摘要。"""
        if not self.incremental_summaries:
            return

        logger.info(f"[Summarizer] 🔄 合并摘要: 基础摘要 + {len(self.incremental_summaries)}个增量")

        all_parts = [self.base_summary] + self.incremental_summaries
        combined_text = "\n\n".join(f"[阶段{i+1}] {part}" for i, part in enumerate(all_parts))

        temp_messages = [Message(role=MessageRole.ASSISTANT, content=combined_text)]
        new_base = await self.strategy.summarize(temp_messages, None)

        self.base_summary = new_base
        self.incremental_summaries = []

        logger.info("[Summarizer] ✓ 摘要合并完成，增量列表已清空")

    def get_combined_summary(self) -> Optional[str]:
        """获取合并了基础摘要和所有增量的完整摘要。"""
        if self.base_summary is None:
            return None

        if not self.incremental_summaries:
            return self.base_summary

        parts = [f"[基础] {self.base_summary}"]
        for i, inc in enumerate(self.incremental_summaries, 1):
            parts.append(f"[增量{i}] {inc}")

        return "\n\n".join(parts)

    def get_current_summary(self) -> Optional[str]:
        """获取当前摘要（兼容旧接口）。"""
        return self.get_combined_summary()

    def clear_summary(self):
        """清空所有摘要。"""
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
        """
        获取摘要和最近对话，自动判断是否需要摘要，支持增量模式。

        Args:
            all_history: 所有对话历史（ContextItem列表）
            current_turn: 实际session轮数（用于摘要触发判断，默认使用历史长度）

        Returns:
            (摘要文本, 最近对话列表)；不需要摘要时返回 (None, all_history)
        """
        total_turns = len(all_history)

        if current_turn is None:
            current_turn = total_turns

        if not self.should_summarize(current_turn):
            logger.debug(f"[Summarizer] 当前{current_turn}轮，未达到摘要阈值{self.config.summarize_threshold}轮")
            return None, all_history

        if self.base_summary is None:
            summary_turns = total_turns - self.config.keep_recent_turns
            if summary_turns > 0:
                messages_to_summarize = []
                for item in all_history[:summary_turns]:
                    messages_to_summarize.append(self._contextitem_to_message(item))

                await self.create_base_summary(messages_to_summarize, summary_turns)
                logger.info(f"[Summarizer] 📝 基础摘要已创建，覆盖第1-{summary_turns}轮")

        elif self.should_create_incremental_summary(current_turn):
            start_turn = self.last_summarized_turn
            end_turn = total_turns - self.config.keep_recent_turns

            if end_turn > start_turn:
                messages_for_increment = []
                for item in all_history[start_turn:end_turn]:
                    messages_for_increment.append(self._contextitem_to_message(item))

                await self.create_incremental_summary(messages_for_increment, end_turn)
                logger.info(f"[Summarizer] 📝 增量摘要已创建，覆盖第{start_turn+1}-{end_turn}轮")

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
        """
        将 ContextItem 转换为 Message。

        通过简单的字符串前缀启发式判断角色，因为 ContextItem 不携带结构化角色字段。
        无法识别角色时默认归为 USER，以避免摘要器遗漏内容。
        """
        content = item.content

        if "user:" in content.lower():
            role = MessageRole.USER
            content = content.split(":", 1)[1].strip() if ":" in content else content
        elif "assistant:" in content.lower():
            role = MessageRole.ASSISTANT
            content = content.split(":", 1)[1].strip() if ":" in content else content
        else:
            role = MessageRole.USER

        return Message(role=role, content=content)
