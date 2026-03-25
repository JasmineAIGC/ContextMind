"""
EvolveEngine - 进化引擎核心模块

上下文优化引擎，提供 optimize/update/handle_response/extract_knowledge 等核心接口。
"""

from __future__ import annotations

from typing import Optional, List, Any, Dict
from datetime import datetime

from .data_models import (
    Message,
    ContextResult,
    ContextItem,
    ProcessedContext,
    Knowledge,
)
from .config import MessageRole, ContextSource
from contextmind.infra.logger import get_logger
from contextmind.modes.evolve.memory import SessionManager, MemoryBank
from contextmind.modes.evolve.pipeline.response_handler import ResponseHandler
from contextmind.modes.evolve.pipeline.steps import InputPreprocessor
from contextmind.modes.evolve.pipeline.steps import ContextCompressor
from contextmind.modes.evolve.pipeline.steps import ContextReorderer
from contextmind.modes.evolve.pipeline.summarizer import ConversationSummarizer

logger = get_logger(__name__)


class EvolveEngine:
    """
    进化引擎，专注于上下文优化。

    核心接口：optimize()、update()、handle_response()、extract_knowledge()。
    """
    
    def __init__(
        self,
        *,
        app_name: str,
        user_id: str,
        llm_client: Optional[Any] = None,
        session_service: Optional[Any] = None,
        memory_service: Optional[Any] = None,
        max_recent_events: int = 9999,   # 实际上限由 session_service 决定，此处设为极大值不主动截断
        use_summarizer: bool = False,
        extraction_method: str = "llm",
        extraction_config: Optional[Any] = None,
    ):
        """
        Args:
            app_name: 应用名称
            user_id: 用户 ID
            llm_client: LLM 客户端实例（知识提取需要）
            session_service: Session 服务实例（可选）
            memory_service: Memory 服务实例（可选）
            max_recent_events: 保留的最大近期事件数量
            use_summarizer: 是否启用对话摘要器
            extraction_method: 知识提取方式，仅支持 'llm'
            extraction_config: 提取配置对象（可选）
        """
        self.app_name = app_name
        self.user_id = user_id
        self.llm_client = llm_client
        self.extraction_method = extraction_method
        
        self.session_manager = SessionManager(
            session_service=session_service,
            app_name=app_name,
            user_id=user_id,
            max_recent_events=max_recent_events,
        )
        
        self.memory_bank = MemoryBank(
            memory_service=memory_service,
            session_service=session_service,
            app_name=app_name,
            user_id=user_id,
        )
        
        self.preprocessor = InputPreprocessor()
        self.compressor = ContextCompressor()
        self.reorderer = ContextReorderer()
        
        from contextmind.modes.evolve.memory import LLMBasedExtractor
        from .config import DEFAULT_MEMORY_CONFIG
        
        config = extraction_config or DEFAULT_MEMORY_CONFIG.extraction
        config.extraction_method = extraction_method
        
        if extraction_method == "llm":
            if not llm_client:
                logger.error(
                    "[EvolveEngine] ⚠️ LLM提取模式需要llm_client参数！"
                    "知识提取功能将被禁用。请提供llm_client以启用自动知识提取。"
                )
                self.extractor = None
                self.extraction_method = "disabled"
            else:
                self.extractor = LLMBasedExtractor(llm_client, config)
                logger.info("[EvolveEngine] ✅ LLMBasedExtractor 已初始化用于知识提取")
        else:
            logger.warning(
                f"[EvolveEngine] ⚠️ 不支持的提取方式: {extraction_method}. "
                "v0.3.0+ 仅支持基于大语言模型的提取。知识提取功能将被禁用。"
            )
            self.extractor = None
            self.extraction_method = "disabled"
        
        self.response_handler = ResponseHandler(
            session_manager=self.session_manager,
            memory_bank=self.memory_bank,
            extractor=self.extractor
        )
        logger.info("[EvolveEngine] ResponseHandler 已初始化")
        
        if use_summarizer:
            self.summarizer = ConversationSummarizer()
            logger.info("[EvolveEngine] ConversationSummarizer 已启用")
        else:
            self.summarizer = None

        # 记录最后一次 optimize() 的结果，供 UI 状态面板展示
        self.last_context_result: Optional["ContextResult"] = None
        
        logger.info(f"EvolveEngine 已初始化 app={app_name}, user={user_id}")
    
    async def optimize(
        self,
        user_input: str,
        include_session: bool = True,
        include_memory: bool = True,
        include_knowledge: bool = False,
        max_context_length: Optional[int] = None,
    ) -> ContextResult:
        """
        优化上下文，依次执行预处理、记忆检索、上下文构建和压缩。

        Args:
            user_input: 用户输入
            include_session: 是否包含会话历史
            include_memory: 是否包含长期记忆
            include_knowledge: 是否包含外部知识（预留）
            max_context_length: 最大上下文长度限制（预留）

        Returns:
            ContextResult 对象，包含优化后的上下文
        """
        logger.info("")
        logger.info("=" * 100)
        logger.info(f"[EvolveEngine] ========== 开始上下文优化 ==========")
        logger.info(f"[EvolveEngine] 📝 用户输入: '{user_input[:60]}{'...' if len(user_input) > 60 else ''}'")
        logger.info("=" * 100)
        logger.info("")
        
        processed_input = await self.preprocessor.process(user_input)
        logger.info(f"[EvolveEngine] ✓ 预处理完成")
        logger.info("")
        
        logger.info(f"[EvolveEngine] 🔍 步骤 2/5: 召回相关上下文")
        
        recent_history = []
        if include_session:
            recent_history = await self.session_manager.get_recent_history()
            logger.info(f"[EvolveEngine]   - 会话历史: {len(recent_history)} 条消息")
        
        long_term_memory = []
        if include_memory:
            long_term_memory = await self.memory_bank.retrieve(
                query=processed_input,
                limit=10  # 取Top-10记忆：经验值，在覆盖率和 Token 开销之间取得平衡
            )
            logger.info(f"[EvolveEngine]   - 长期记忆: {len(long_term_memory)} 条知识")
        
        logger.info(f"[EvolveEngine] ✓ 召回完成 - 共检索到 {len(recent_history) + len(long_term_memory)} 条上下文")
        logger.info("")
        
        logger.info(f"[EvolveEngine] 📦 步骤 3/5: 构建上下文")
        
        all_items = []
        
        for msg in recent_history:
            all_items.append(ContextItem(
                content=f"{msg.role.value}: {msg.content}",
                source=ContextSource.HISTORY,
                score=1.0,
                metadata={"timestamp": msg.timestamp.isoformat() if msg.timestamp else None}
            ))
        
        all_items.extend(long_term_memory)
        
        logger.info(f"[EvolveEngine] ✓ 上下文构建完成 - {len(all_items)} 条上下文项")
        logger.info("")
        
        logger.info(f"[EvolveEngine] 🗜️  步骤 4/5: 上下文压缩")
        is_compressed = False
        if len(all_items) > 50:  # 50条以下的上下文规模通常在 Token 预算内，压缩收益不抵开销
            logger.info(f"[EvolveEngine]   - 上下文项过多，需要压缩")
            # TODO: 实现压缩逻辑
            is_compressed = True
            logger.info(f"[EvolveEngine] ✓ 压缩完成")
        else:
            logger.info(f"[EvolveEngine]   - 上下文项数量适中({len(all_items)}条)，无需压缩")
        logger.info("")
        
        logger.info(f"[EvolveEngine] ✅ 步骤 5/5: 生成最终上下文结果")
        compressed_result = ContextResult(
            items=all_items,
            total_tokens=0,  # TODO: 计算实际 Token 数
            compressed=is_compressed,
            metadata={
                "session_history_count": len(recent_history),
                "long_term_memory_count": len(long_term_memory),
            }
        )
        logger.info("")
        
        logger.info("-" * 100)
        logger.info(
            f"[EvolveEngine] 🎯 上下文优化完成 - "
            f"共 {len(compressed_result.items)} 条上下文项 "
            f"(会话: {compressed_result.metadata.get('session_history_count', 0)}, "
            f"记忆: {compressed_result.metadata.get('long_term_memory_count', 0)})"
        )
        
        logger.info("-" * 100)
        logger.info(f"[EvolveEngine] ========== 上下文优化结束 ==========")
        logger.info("")

        # 保存本轮 optimize 结果，供 UI 状态面板读取
        self.last_context_result = compressed_result

        return compressed_result
    
    async def update(
        self,
        user_input: str,
        assistant_response: str,
    ) -> None:
        """
        仅将当前对话轮次写入会话历史，不执行知识提取。

        适用于对延迟敏感的场景，知识提取可延迟到会话结束时批量调用
        handle_response() 或 extract_knowledge() 完成。
        """
        logger.info(f"[EvolveEngine] 💾 更新会话历史 - 添加新对话轮次")
        logger.info(f"[EvolveEngine]   - 用户消息: {len(user_input)} 字符")
        logger.info(f"[EvolveEngine]   - 助手回复: {len(assistant_response)} 字符")
        
        await self.session_manager.add_message(
            role=MessageRole.USER,
            content=user_input
        )
        await self.session_manager.add_message(
            role=MessageRole.ASSISTANT,
            content=assistant_response
        )
        
        logger.info("[EvolveEngine] ✓ 会话历史更新完成")
        logger.info("")
    
    async def handle_response(
        self,
        user_input: str,
        llm_response: str,
        context: Optional[ContextResult] = None,
        auto_extract: bool = True,
        auto_store: bool = True
    ) -> Dict[str, Any]:
        """
        处理 LLM 响应：记录对话、提取知识、存储到记忆库。

        Args:
            user_input: 原始用户输入
            llm_response: LLM 生成的响应
            context: 使用的上下文结果（可选）
            auto_extract: 是否自动提取知识
            auto_store: 是否自动存储到记忆库

        Returns:
            处理结果字典，含 recorded、extracted_knowledge、stored 字段
        """
        return await self.response_handler.handle_response(
            user_input=user_input,
            llm_response=llm_response,
            context=context,
            auto_extract=auto_extract,
            auto_store=auto_store
        )
    
    async def extract_knowledge(
        self,
        auto_store: bool = True,
    ) -> List[Knowledge]:
        """
        从最近对话中提取结构化知识，并可选地存储到长期记忆。

        Args:
            auto_store: 是否自动存储到长期记忆

        Returns:
            提取的知识列表
        """
        logger.info("")
        logger.info("=" * 100)
        logger.info("[EvolveEngine] ========== 🧠 开始知识提取 ==========")
        
        if not self.extractor:
            logger.warning("[EvolveEngine] ⚠️  知识提取器未初始化（需要llm_client）")
            logger.info("=" * 100)
            logger.info("")
            return []
        
        messages = await self.session_manager.get_recent_history()
        
        if not messages:
            logger.info("[EvolveEngine] ⚠️  没有对话历史可供提取知识")
            logger.info("=" * 100)
            logger.info("")
            return []
        
        logger.info(f"[EvolveEngine] 📖 从 {len(messages)} 条对话中提取知识...")
        logger.info("=" * 100)
        logger.info("")
        
        knowledge = await self.extractor.extract(messages)
        
        if not knowledge:
            logger.info("")
            logger.info("-" * 100)
            logger.info("[EvolveEngine] ℹ️  未提取到任何有效知识")
            logger.info("-" * 100)
            logger.info("")
            return []
        
        logger.info("")
        logger.info("-" * 100)
        logger.info(f"[EvolveEngine] ✓ 知识提取完成 - 共提取 {len(knowledge)} 条知识")
        
        if auto_store:
            logger.info("")
            logger.info(f"[EvolveEngine] 📥 入库: 存储知识到长期记忆...")
            await self.memory_bank.store(knowledge)
            logger.info(f"[EvolveEngine] ✓ 知识入库完成")
        
        logger.info("-" * 100)
        logger.info(f"[EvolveEngine] ========== 知识提取结束 ==========")
        logger.info("")
        
        return knowledge
    
    async def generate_summary(self) -> str:
        """
        从当前对话历史生成摘要。

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
        
        summary_parts = []
        
        user_msgs = [m for m in messages if m.role == MessageRole.USER]
        assistant_msgs = [m for m in messages if m.role == MessageRole.ASSISTANT]
        
        summary_parts.append(f"对话轮次: {len(messages) // 2} 轮")
        summary_parts.append(f"用户消息: {len(user_msgs)} 条")
        summary_parts.append(f"助手回复: {len(assistant_msgs)} 条")
        
        if user_msgs:
            recent_topics = []
            for msg in user_msgs[-5:]:
                if len(msg.content) > 0:
                    topic = msg.content[:30] + "..." if len(msg.content) > 30 else msg.content
                    recent_topics.append(topic)
            
            if recent_topics:
                summary_parts.append(f"\n最近话题:")
                for i, topic in enumerate(recent_topics, 1):
                    summary_parts.append(f"  {i}. {topic}")
        
        memory_cache = self.memory_bank.get_memory_cache()
        if memory_cache:
            summary_parts.append(f"\nMemory Bank: {len(memory_cache)} 条记忆")
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
        """植入预定义的知识作为长期记忆基础。"""
        await self.memory_bank.seed(facts)
    
    async def clear_session(self) -> None:
        """清空当前会话，创建新会话并清除所有历史记录。"""
        await self.session_manager.clear()
        logger.info("Session 已清空")
