"""
ContextEngine - 上下文引擎核心模块 v7.1
ContextEngine - Core Context Engine Module v7.1

清晰的模块化架构设计 Clear modular architecture design：
- 应用层 Application Layer：使用引擎的应用（示例：客服、聊天机器人等）
  Applications using the engine (e.g., customer service, chatbots)
- 引擎层 Engine Layer：ContextEngine 统一接口
  ContextEngine unified interface
- 模块层 Module Layer：InputPreprocessor, MemoryBank, 
  ContextCompressor, ContextReorderer, PostProcessor, ConversationSummarizer
- 策略层 Strategy Layer：可插拔的策略实现
  Pluggable strategy implementations

核心职责 Core Responsibilities：
1. 上下文优化 Context optimization (optimize)
2. 上下文更新 Context update (update)
3. 知识提取 Knowledge extraction (extract_knowledge)
"""

from __future__ import annotations

from typing import Optional, List, Any
from datetime import datetime

from .models import (
    Message,
    MessageRole,
    ContextResult,
    ContextItem,
    ContextSource,
    ProcessedContext,
    Knowledge,
    get_logger,
)
from .pipeline import (
    SessionManager,
    InputPreprocessor,
    MemoryBank,
    ContextCompressor,
    ContextReorderer,
    PostProcessor,
    ConversationSummarizer,
    KVCacheManager,
)

logger = get_logger(__name__)


class ContextEngine:
    """
    上下文引擎 v7.1
    
    专注于上下文优化的核心引擎，提供简洁的API：
    - optimize(): 优化上下文，返回 ContextResult
    - update(): 更新上下文（添加对话到会话）
    - extract_knowledge(): 提取知识到长期记忆
    
    架构特点：
    - 职责清晰：只负责上下文优化，不包含业务逻辑
    - 模块解耦：Pipeline、Manager、Strategy各司其职
    - 易于扩展：所有策略都可插拔替换
    - 异步优先：全面使用async/await
    
    使用示例：
        ```python
        from contextmind import ContextEngine
        
        engine = ContextEngine(
            app_name="my-app",
            user_id="user-123"
        )
        
        # 优化上下文
        context_result = await engine.optimize("你好")
        
        # 更新上下文
        await engine.update(
            user_input="你好",
            assistant_response="你好，有什么可以帮助你的？"
        )
        ```
    """
    
    def __init__(
        self,
        *,
        app_name: str,
        user_id: str,
        llm_client: Optional[Any] = None,
        session_service: Optional[Any] = None,
        memory_service: Optional[Any] = None,
        max_recent_events: int = 9999,
        use_postprocessor: bool = False,
        use_summarizer: bool = False,
    ):
        """
        初始化上下文引擎
        
        v3.4 Plugin Architecture:
        Now supports optional PostProcessor and Summarizer components.
        
        Args:
            app_name: 应用名称
            user_id: 用户ID
            llm_client: LLM客户端实例（可选）
            session_service: Session服务实例（可选）
            memory_service: Memory服务实例（可选）
            max_recent_events: 保留的最大近期事件数量（默认9999，实际不限制）
            use_postprocessor: 是否使用输出后处理器（默认False）
            use_summarizer: 是否使用对话摘要器（默认False）
        """
        self.app_name = app_name
        self.user_id = user_id
        self.llm_client = llm_client
        
        # 初始化管理器
        self.session_manager = SessionManager(
            session_service=session_service,
            app_name=app_name,
            user_id=user_id,
            max_recent_events=max_recent_events,
        )
        
        # 初始化记忆库
        self.memory_bank = MemoryBank(
            memory_service=memory_service,
            session_service=session_service,
            app_name=app_name,
            user_id=user_id,
        )
        
        # Initialize modular components (v7.0 architecture)
        self.preprocessor = InputPreprocessor()
        # Note: In v7.0, MemoryBank handles both storage and retrieval
        # No separate ContextRetriever needed
        self.compressor = ContextCompressor()
        self.reorderer = ContextReorderer()
        # Note: Knowledge extraction is handled by extractors in strategies layer
        
        # v7.1 Optional components (all components are now standard)
        if use_postprocessor:
            self.postprocessor = PostProcessor()
            logger.info("[ContextEngine] PostProcessor enabled")
        else:
            self.postprocessor = None
        
        if use_summarizer:
            self.summarizer = ConversationSummarizer()
            logger.info("[ContextEngine] ConversationSummarizer enabled")
        else:
            self.summarizer = None
        
        logger.info(f"ContextEngine initialized for app={app_name}, user={user_id}")
    
    async def optimize(
        self,
        user_input: str,
        include_session: bool = True,
        include_memory: bool = True,
        include_knowledge: bool = False,
        max_context_length: Optional[int] = None,
    ) -> ContextResult:
        """
        优化上下文 - 核心方法
        
        执行完整的模块化上下文优化流程 v7.0：
        1. InputPreprocessor: 预处理输入
        2. MemoryBank: 检索长期记忆
        3. ContextCompressor: 压缩上下文
        4. ContextReorderer: 重排序上下文
        
        Args:
            user_input: 用户输入
            include_session: 是否包含会话历史
            include_memory: 是否包含长期记忆
            include_knowledge: 是否包含外部知识（预留）
            max_context_length: 最大上下文长度限制（预留）
            
        Returns:
            ContextResult 对象，包含优化后的上下文
            
        Raises:
            ValueError: 如果输入无效
        """
        logger.info("")
        logger.info("=" * 100)
        logger.info(f"[ContextEngine] ========== 开始上下文优化 ==========")
        logger.info(f"[ContextEngine] 用户输入: '{user_input[:60]}{'...' if len(user_input) > 60 else ''}'")
        logger.debug(f"[ContextEngine] 配置 - 会话历史: {include_session}, 长期记忆: {include_memory}, 外部知识: {include_knowledge}")
        logger.info("=" * 100)
        logger.info("")
        
        # 1. 预处理输入
        logger.debug(f"[ContextEngine] 步骤 1/4: 预处理输入")
        processed_input = await self.preprocessor.process(user_input)
        logger.debug(f"[ContextEngine] 预处理完成: '{processed_input[:60]}...'")
        logger.debug("")
        
        # 2. 检索上下文（使用 MemoryBank 和 SessionManager）
        logger.debug(f"[ContextEngine] 步骤 2/4: 检索上下文")
        
        # 获取会话历史
        recent_history = []
        if include_session:
            recent_history = await self.session_manager.get_recent_history()
            logger.debug(f"[ContextEngine] 检索到会话历史: {len(recent_history)} 条")
        
        # 检索长期记忆
        long_term_memory = []
        if include_memory:
            long_term_memory = await self.memory_bank.retrieve(
                query=processed_input,
                limit=10
            )
            logger.debug(f"[ContextEngine] 检索到长期记忆: {len(long_term_memory)} 条")
        
        logger.debug("")
        
        # 3. 构建 ContextResult
        logger.debug(f"[ContextEngine] 步骤 3/4: 构建上下文结果")
        
        # Combine all context items
        all_items = []
        
        # Convert recent history (Message objects) to ContextItem
        for msg in recent_history:
            all_items.append(ContextItem(
                content=f"{msg.role.value}: {msg.content}",
                source=ContextSource.HISTORY,
                score=1.0,
                metadata={"timestamp": msg.timestamp.isoformat() if msg.timestamp else None}
            ))
        
        # Add long-term memory items (already ContextItem)
        all_items.extend(long_term_memory)
        
        # 创建 ContextResult
        compressed_result = ContextResult(
            items=all_items,
            total_tokens=0,  # TODO: Calculate actual token count
            metadata={
                "session_history_count": len(recent_history),
                "long_term_memory_count": len(long_term_memory),
            }
        )
        logger.debug(f"[ContextEngine] 上下文构建完成: {len(all_items)} 条")
        logger.debug("")
        
        # Log final result with details
        logger.info("")
        logger.info("-" * 100)
        logger.info(
            f"[ContextEngine] ✓ 上下文优化完成 - "
            f"总共: {len(compressed_result.items)} 条上下文项 "
            f"(会话历史: {compressed_result.metadata.get('session_history_count', 0)}, "
            f"长期记忆: {compressed_result.metadata.get('long_term_memory_count', 0)})"
        )
        
        # Log details of what was included
        if compressed_result.items:
            logger.debug(f"[ContextEngine] 上下文项详情:")
            for i, item in enumerate(compressed_result.items[:5], 1):
                logger.debug(f"  {i}. [{item.source.value}] {item.content[:80]}...")
            if len(compressed_result.items) > 5:
                logger.debug(f"  ... 以及其他 {len(compressed_result.items) - 5} 条")
        
        logger.info("-" * 100)
        logger.info(f"[ContextEngine] ========== 上下文优化结束 ==========")
        logger.info("")
        
        return compressed_result
    
    async def update(
        self,
        user_input: str,
        assistant_response: str,
    ) -> None:
        """
        更新上下文
        
        将用户输入和助手回复添加到会话历史中。
        
        Args:
            user_input: 用户输入
            assistant_response: 助手回复
        """
        logger.info(f"[ContextEngine] 更新上下文 - 添加新对话")
        logger.debug(f"[ContextEngine] 用户: {user_input[:60]}...")
        logger.debug(f"[ContextEngine] 助手: {assistant_response[:60]}...")
        
        # 添加用户消息
        await self.session_manager.add_message(
            role=MessageRole.USER,
            content=user_input
        )
        
        # 添加助手消息
        await self.session_manager.add_message(
            role=MessageRole.ASSISTANT,
            content=assistant_response
        )
        
        logger.info("[ContextEngine] ✓ 上下文更新完成")
    
    async def extract_knowledge(
        self,
        auto_store: bool = True,
    ) -> List[Knowledge]:
        """
        提取知识到长期记忆
        
        从最近的对话中提取结构化知识，并可选地自动存储到长期记忆。
        
        Args:
            auto_store: 是否自动存储到长期记忆，默认为True
            
        Returns:
            提取的知识列表
        """
        logger.info("")
        logger.info("=" * 100)
        logger.info("[ContextEngine] ========== 开始知识提取 ==========")
        
        # 获取最近的对话历史
        messages = await self.session_manager.get_recent_history()
        
        if not messages:
            logger.info("[ContextEngine] 没有对话历史可供提取知识")
            logger.info("=" * 100)
            logger.info("")
            return []
        
        logger.info(f"[ContextEngine] 准备从 {len(messages)} 条对话中提取知识")
        logger.info("=" * 100)
        logger.info("")
        
        # 提取知识
        knowledge = await self.extractor.extract(messages)
        
        if not knowledge:
            logger.info("")
            logger.info("-" * 100)
            logger.info("[ContextEngine] 未提取到任何知识")
            logger.info("-" * 100)
            logger.info("")
            return []
        
        logger.info("")
        logger.info("-" * 100)
        logger.info(f"[ContextEngine] ✓ 知识提取完成 - 提取到 {len(knowledge)} 条知识")
        logger.debug(f"[ContextEngine] 提取的知识详情:")
        for i, k in enumerate(knowledge, 1):
            logger.debug(f"  {i}. [{k.type.value}] {k.content[:80]}... (置信度: {k.confidence:.2f})")
        
        # 自动存储到长期记忆
        if auto_store:
            logger.info(f"[ContextEngine] 存储知识到长期记忆...")
            await self.memory_bank.store(knowledge)
        
        logger.info("-" * 100)
        logger.info(f"[ContextEngine] ========== 知识提取结束 ==========")
        logger.info("")
        
        return knowledge
    
    async def generate_summary(self) -> str:
        """
        生成对话摘要 (Issue 3)
        
        从当前对话历史中生成摘要，用于快速理解对话内容。
        当前实现为基于规则的简单摘要，未来可扩展为LLM生成。
        
        Returns:
            对话摘要文本
        """
        logger.info("")
        logger.info("=" * 100)
        logger.info("[Summary] ========== 开始生成对话摘要 ==========")
        logger.info("=" * 100)
        logger.info("")
        
        messages = await self.session_manager.get_recent_history()
        
        if not messages:
            logger.info("[Summary] 无对话历史，无法生成摘要")
            logger.info("")
            return "暂无对话历史"
        
        # 简单的基于规则的摘要生成
        summary_parts = []
        
        # 统计信息
        user_msgs = [m for m in messages if m.role == MessageRole.USER]
        assistant_msgs = [m for m in messages if m.role == MessageRole.ASSISTANT]
        
        summary_parts.append(f"对话轮次: {len(messages) // 2} 轮")
        summary_parts.append(f"用户消息: {len(user_msgs)} 条")
        summary_parts.append(f"助手回复: {len(assistant_msgs)} 条")
        
        # 提取关键话题（基于用户消息）
        if user_msgs:
            recent_topics = []
            for msg in user_msgs[-5:]:  # 最近5条用户消息
                if len(msg.content) > 0:
                    topic = msg.content[:30] + "..." if len(msg.content) > 30 else msg.content
                    recent_topics.append(topic)
            
            if recent_topics:
                summary_parts.append(f"\n最近话题:")
                for i, topic in enumerate(recent_topics, 1):
                    summary_parts.append(f"  {i}. {topic}")
        
        # 记忆库状态
        memory_cache = self.memory_bank.get_memory_cache()
        if memory_cache:
            summary_parts.append(f"\n记忆库: {len(memory_cache)} 条记忆")
            for i, mem in enumerate(memory_cache[:3], 1):
                summary_parts.append(f"  {i}. {mem.content[:50]}...")
        
        summary = "\n".join(summary_parts)
        
        logger.info("[Summary] ✓ 摘要生成完成:")
        logger.info(summary)
        logger.info("")
        logger.info("-" * 100)
        logger.info("[Summary] ========== 对话摘要结束 ==========")
        logger.info("")
        
        return summary
    
    async def seed_memory(self, facts: List[str]) -> None:
        """
        植入记忆种子
        
        在初始化时植入预定义的知识作为长期记忆的基础。
        
        Args:
            facts: 事实字符串列表
        """
        await self.memory_bank.seed(facts)
    
    async def clear_session(self) -> None:
        """
        清空当前会话
        
        创建一个新的会话，清除所有历史记录。
        """
        await self.session_manager.clear()
        logger.info("Session cleared")
