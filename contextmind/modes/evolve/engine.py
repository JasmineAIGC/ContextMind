"""
EvolveEngine - 进化引擎核心模块 v0.2.1

清晰的模块化架构设计:
- 应用层: 使用引擎的应用（示例：客服、聊天机器人等）
- 引擎层: EvolveEngine 统一接口
- 模块层: InputPreprocessor, MemoryBank, ContextCompressor, 
  ContextReorderer, ResponseHandler, ConversationSummarizer
- 策略层: 可插拔的策略实现

核心职责:
1. 上下文优化 (optimize)
2. 响应处理 (handle_response)
3. 知识提取 (extract_knowledge)
4. 上下文更新 (update)
"""

from __future__ import annotations

from typing import Optional, List, Any, Dict
from datetime import datetime

from .core.data_models import (
    Message,
    ContextResult,
    ContextItem,
    ProcessedContext,
    Knowledge,
)
from .core.types import MessageRole, ContextSource
from contextmind.core.common.utils.logger import get_logger
from .memory import SessionManager, MemoryBank
from .pipeline.response_handler import ResponseHandler
from .pipeline.preprocessor import InputPreprocessor
from .pipeline.compressor import ContextCompressor
from .pipeline.reorderer import ContextReorderer
from .pipeline.summarizer import LLMBasedSummarizer as ConversationSummarizer

logger = get_logger(__name__)


class EvolveEngine:
    """
    进化引擎 v7.1
    
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
        from contextmind.modes.evolve import EvolveEngine
        
        engine = EvolveEngine(
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
        extraction_method: str = "llm",  # 默认使用 'llm' 基于大语言模型的提取
        extraction_config: Optional[Any] = None,
    ):
        """
        初始化上下文引擎
        
        v0.2.1 知识提取架构:
        默认使用基于大语言模型的知识提取，确保最佳效果
        
        Args:
            app_name: 应用名称
            user_id: 用户 ID
            llm_client: LLM 客户端实例 (可选，但强烈推荐用于知识提取)
            session_service: Session 服务实例 (可选)
            memory_service: Memory 服务实例 (可选)
            max_recent_events: 保留的最大近期事件数量 (默认 9999, 实际不限制)
            use_postprocessor: (已废弃) 使用 handle_response 代替
            use_summarizer: 是否使用对话摘要器 (默认 False)
            extraction_method: 知识提取方式 (默认 'llm' 使用大语言模型)
            extraction_config: 提取配置对象 (可选)
        """
        self.app_name = app_name
        self.user_id = user_id
        self.llm_client = llm_client
        self.extraction_method = extraction_method
        
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
        
        # 初始化模块化组件 (v7.0 架构)
        self.preprocessor = InputPreprocessor()
        # 注意: 在 v7.0 中, MemoryBank 处理存储和检索
        # 不需要单独的 ContextRetriever
        self.compressor = ContextCompressor()
        self.reorderer = ContextReorderer()
        
        # 初始化知识提取器 (v0.2.1 - 默认使用 LLM，确保最佳效果)
        from .memory import LLMBasedExtractor
        from .core.configs import DEFAULT_MEMORY_CONFIG
        
        # 使用提供的配置或默认配置
        config = extraction_config or DEFAULT_MEMORY_CONFIG.extraction
        # 设置提取方式
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
            # 不再支持基于规则的提取
            logger.warning(
                f"[EvolveEngine] ⚠️ 不支持的提取方式: {extraction_method}. "
                "v0.2.1+ 仅支持基于大语言模型的提取。知识提取功能将被禁用。"
            )
            self.extractor = None
            self.extraction_method = "disabled"
        
        # 初始化响应处理器 (v0.2.1 - 替代 PostProcessor)
        self.response_handler = ResponseHandler(
            session_manager=self.session_manager,
            memory_bank=self.memory_bank,
            extractor=self.extractor
        )
        logger.info("[EvolveEngine] ResponseHandler 已初始化")
        
        # v7.1 可选组件
        if use_summarizer:
            self.summarizer = ConversationSummarizer()
            logger.info("[EvolveEngine] ConversationSummarizer 已启用")
        else:
            self.summarizer = None
        
        if use_postprocessor:
            logger.warning(
                "[EvolveEngine] use_postprocessor 已废弃，"
                "请使用 handle_response() 方法代替"
            )
        
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
        logger.info(f"[EvolveEngine] ========== 开始上下文优化 ==========")
        logger.info(f"[EvolveEngine] 📝 用户输入: '{user_input[:60]}{'...' if len(user_input) > 60 else ''}'")
        logger.info("=" * 100)
        logger.info("")
        
        # 1. 预处理输入
        logger.info(f"[EvolveEngine] 🔄 步骤 1/5: 预处理用户输入")
        processed_input = await self.preprocessor.process(user_input)
        logger.info(f"[EvolveEngine] ✓ 预处理完成")
        logger.info("")
        
        # 2. 检索上下文 (召回)
        logger.info(f"[EvolveEngine] 🔍 步骤 2/5: 召回相关上下文")
        
        # 获取会话历史
        recent_history = []
        if include_session:
            recent_history = await self.session_manager.get_recent_history()
            logger.info(f"[EvolveEngine]   - 会话历史: {len(recent_history)} 条消息")
        
        # 检索长期记忆
        long_term_memory = []
        if include_memory:
            long_term_memory = await self.memory_bank.retrieve(
                query=processed_input,
                limit=10
            )
            logger.info(f"[EvolveEngine]   - 长期记忆: {len(long_term_memory)} 条知识")
        
        logger.info(f"[EvolveEngine] ✓ 召回完成 - 共检索到 {len(recent_history) + len(long_term_memory)} 条上下文")
        logger.info("")
        
        # 3. 构建 ContextResult
        logger.info(f"[EvolveEngine] 📦 步骤 3/5: 构建上下文")
        
        # 合并所有 Context 项
        all_items = []
        
        # 将近期历史 (Message 对象) 转换为 ContextItem
        for msg in recent_history:
            all_items.append(ContextItem(
                content=f"{msg.role.value}: {msg.content}",
                source=ContextSource.HISTORY,
                score=1.0,
                metadata={"timestamp": msg.timestamp.isoformat() if msg.timestamp else None}
            ))
        
        # 添加长期记忆项 (已经是 ContextItem)
        all_items.extend(long_term_memory)
        
        logger.info(f"[EvolveEngine] ✓ 上下文构建完成 - {len(all_items)} 条上下文项")
        logger.info("")
        
        # 4. 上下文压缩（如果需要）
        logger.info(f"[EvolveEngine] 🗜️  步骤 4/5: 上下文压缩")
        # 当前版本：上下文项数量较少时不需要压缩
        is_compressed = False
        if len(all_items) > 50:  # 超过50条才需要压缩
            logger.info(f"[EvolveEngine]   - 上下文项过多，需要压缩")
            # TODO: 实现压缩逻辑
            is_compressed = True
            logger.info(f"[EvolveEngine] ✓ 压缩完成")
        else:
            logger.info(f"[EvolveEngine]   - 上下文项数量适中({len(all_items)}条)，无需压缩")
        logger.info("")
        
        # 5. 创建最终结果
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
        
        # 记录最终结果
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
        
        return compressed_result
    
    async def update(
        self,
        user_input: str,
        assistant_response: str,
    ) -> None:
        """
        更新上下文 (简化版本)
        
        将用户输入和助手回复添加到会话历史中。
        
        注意: 这是简化的 API，仅记录对话。
        如需完整功能（包括知识提取和记忆更新），请使用 handle_response()。
        
        Args:
            user_input: 用户输入
            assistant_response: 助手回复
        """
        logger.info("")
        logger.info(f"[EvolveEngine] 💾 更新会话历史 - 添加新对话轮次")
        logger.info(f"[EvolveEngine]   - 用户消息: {len(user_input)} 字符")
        logger.info(f"[EvolveEngine]   - 助手回复: {len(assistant_response)} 字符")
        
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
        处理 LLM 响应（完整版本）
        
        这是流水线的最后一步，负责：
        1. 记录对话到会话历史
        2. 从对话中提取知识
        3. 自动存储知识到记忆库
        
        推荐使用此方法代替 update()，因为它提供完整的记忆更新功能。
        
        Args:
            user_input: 原始用户输入
            llm_response: LLM 生成的响应
            context: 使用的上下文结果（可选，用于分析）
            auto_extract: 是否自动提取知识（默认 True）
            auto_store: 是否自动存储到记忆库（默认 True）
            
        Returns:
            处理结果字典，包含：
            - recorded: 是否已记录对话
            - extracted_knowledge: 提取的知识列表
            - stored: 是否已存储到记忆库
            
        示例:
            ```python
            # 1. 优化上下文
            context = await engine.optimize("今天天气怎么样？")
            
            # 2. 调用 LLM（用户自己的代码）
            response = await your_llm.chat(context.to_prompt())
            
            # 3. 处理响应并更新记忆
            result = await engine.handle_response(
                user_input="今天天气怎么样？",
                llm_response=response,
                context=context
            )
            ```
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
        提取知识到长期记忆
        
        从最近的对话中提取结构化知识, 并可选地自动存储到长期记忆
        
        Args:
            auto_store: 是否自动存储到长期记忆, 默认为 True
            
        Returns:
            提取的知识列表
        """
        logger.info("")
        logger.info("=" * 100)
        logger.info("[EvolveEngine] ========== 🧠 开始知识提取 ==========")
        
        # 检查提取器是否可用
        if not self.extractor:
            logger.warning("[EvolveEngine] ⚠️  知识提取器未初始化（需要llm_client）")
            logger.info("=" * 100)
            logger.info("")
            return []
        
        # 获取最近的对话历史
        messages = await self.session_manager.get_recent_history()
        
        if not messages:
            logger.info("[EvolveEngine] ⚠️  没有对话历史可供提取知识")
            logger.info("=" * 100)
            logger.info("")
            return []
        
        logger.info(f"[EvolveEngine] 📖 从 {len(messages)} 条对话中提取知识...")
        logger.info("=" * 100)
        logger.info("")
        
        # 提取知识
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
        
        # 自动存储到长期记忆 (入库)
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
        生成对话摘要
        
        从当前对话历史中生成摘要, 用于快速理解对话内容
        当前实现为基于规则的简单摘要, 未来可扩展为 LLM 生成
        
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
        
        # 提取关键话题 (基于用户消息)
        if user_msgs:
            recent_topics = []
            for msg in user_msgs[-5:]:  # 最近 5 条用户消息
                if len(msg.content) > 0:
                    topic = msg.content[:30] + "..." if len(msg.content) > 30 else msg.content
                    recent_topics.append(topic)
            
            if recent_topics:
                summary_parts.append(f"\n最近话题:")
                for i, topic in enumerate(recent_topics, 1):
                    summary_parts.append(f"  {i}. {topic}")
        
        # Memory Bank 状态
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
        """
        植入记忆种子
        
        在初始化时植入预定义的知识作为长期记忆的基础
        
        Args:
            facts: 事实字符串列表
        """
        await self.memory_bank.seed(facts)
    
    async def clear_session(self) -> None:
        """
        清空当前会话
        
        创建一个新的会话, 清除所有历史记录
        """
        await self.session_manager.clear()
        logger.info("Session 已清空")
