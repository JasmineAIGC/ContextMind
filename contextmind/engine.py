"""
ContextEngine - 上下文引擎核心模块 v5.1
ContextEngine - Core Context Engine Module v5.1

清晰的模块化架构设计 Clear modular architecture design：
- 应用层 Application Layer：使用引擎的应用（示例：客服、聊天机器人等）
  Applications using the engine (e.g., customer service, chatbots)
- 适配器层 Adapter Layer：对话系统集成接口
  Dialogue system integration interfaces
- 引擎层 Engine Layer：ContextEngine 统一接口
  ContextEngine unified interface
- 模块层 Module Layer：InputPreprocessor, ContextRetriever, MemoryBank, 
  ContextCompressor, ContextReorderer, KnowledgeExtractor
- 策略层 Strategy Layer：可插拔的策略实现
  Pluggable strategy implementations
- 基础层 Foundation Layer：TokenizerService, VectorClient, CacheManager
  Foundation services

核心职责 Core Responsibilities：
1. 上下文优化 Context optimization (optimize)
2. 上下文更新 Context update (update)
3. 知识提取 Knowledge extraction (extract_knowledge)
"""

from __future__ import annotations

from typing import Optional, List, Any
from datetime import datetime

from .client import Client
from .core import (
    Message,
    MessageRole,
    ContextResult,
    ContextItem,
    ContextSource,
    ProcessedContext,
    Knowledge,
)
from .utils import get_logger
from .pipeline import (
    SessionManager,
    InputPreprocessor,
    ContextRetriever,
    MemoryBank,
    ContextCompressor,
    ContextReorderer,
    KnowledgeExtractor,
)

logger = get_logger(__name__)


class ContextEngine:
    """
    上下文引擎 v4.0
    
    专注于上下文优化的核心引擎，提供简洁的API：
    - optimize(): 优化上下文，返回 ContextResult
    - update(): 更新上下文（添加对话到会话）
    - extract_knowledge(): 提取知识到长期记忆
    
    架构特点：
    - 职责清晰：只负责上下文优化，不包含业务逻辑
    - 模块解耦：Pipeline、Manager、Strategy各司其职
    - 易于扩展：所有策略都可插拔替换
    - 异步优先：全面使用async/await
    - 容错机制：FlowController 和 CircuitBreaker 保障稳定性
    
    使用示例：
        ```python
        from contextmind import ContextEngine, Client
        
        client = Client()
        engine = ContextEngine(
            app_name="my-app",
            user_id="user-123",
            llm_client=client
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
        llm_client: Optional[Client] = None,
        session_service: Optional[Any] = None,
        memory_service: Optional[Any] = None,
        max_recent_events: int = 9999,
    ):
        """
        初始化上下文引擎
        
        Args:
            app_name: 应用名称
            user_id: 用户ID
            llm_client: LLM客户端实例（可选）
            session_service: Session服务实例（可选）
            memory_service: Memory服务实例（可选）
            max_recent_events: 保留的最大近期事件数量（默认9999，实际不限制）
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
        
        # 初始化模块化组件
        self.preprocessor = InputPreprocessor()
        self.retriever = ContextRetriever(
            session_manager=self.session_manager,
            memory_bank=self.memory_bank,
        )
        self.compressor = ContextCompressor()
        self.reorderer = ContextReorderer()
        self.extractor = KnowledgeExtractor()
        
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
        
        执行完整的模块化上下文优化流程：
        1. InputPreprocessor: 预处理输入
        2. ContextRetriever: 检索上下文（RAG）
        3. ContextReorderer: 重排序上下文
        4. ContextCompressor: 压缩上下文
        
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
        logger.info(f"[ContextEngine] ========== 开始上下文优化 ==========")
        logger.info(f"[ContextEngine] 用户输入: '{user_input[:60]}{'...' if len(user_input) > 60 else ''}'")
        logger.debug(f"[ContextEngine] 配置 - 会话历史: {include_session}, 长期记忆: {include_memory}, 外部知识: {include_knowledge}")
        
        # 1. 预处理输入
        logger.debug(f"[ContextEngine] 步骤 1/4: 预处理输入")
        processed_input = await self.preprocessor.process(user_input)
        logger.debug(f"[ContextEngine] 预处理完成: '{processed_input[:60]}...'")
        
        # 2. 检索上下文（RAG）
        logger.debug(f"[ContextEngine] 步骤 2/4: 检索上下文")
        retrieved_context = await self.retriever.retrieve(
            query=processed_input,
            include_session=include_session,
            include_memory=include_memory,
            include_knowledge=include_knowledge,
        )
        logger.debug(f"[ContextEngine] 检索完成 - 获得 {len(retrieved_context.items)} 个上下文项")
        
        # 3. 重排序上下文
        logger.debug(f"[ContextEngine] 步骤 3/4: 重排序上下文")
        reordered_context = await self.reorderer.reorder(retrieved_context)
        logger.debug(f"[ContextEngine] 重排序完成")
        
        # 4. 压缩上下文
        logger.debug(f"[ContextEngine] 步骤 4/4: 压缩上下文")
        compressed_result = await self.compressor.compress(reordered_context)
        
        # Log final result with details
        logger.info(
            f"[ContextEngine] ✓ 上下文优化完成 - "
            f"会话历史: {len(compressed_result.recent_history)} 条, "
            f"长期记忆: {len(compressed_result.long_term_memory)} 条, "
            f"外部知识: {len(compressed_result.external_knowledge)} 条"
        )
        
        # Log details of what was included
        if compressed_result.recent_history:
            logger.debug(f"[ContextEngine] 会话历史详情:")
            for i, msg in enumerate(compressed_result.recent_history[:3], 1):
                logger.debug(f"  {i}. {msg.content[:80]}...")
            if len(compressed_result.recent_history) > 3:
                logger.debug(f"  ... 以及其他 {len(compressed_result.recent_history) - 3} 条")
        
        if compressed_result.long_term_memory:
            logger.debug(f"[ContextEngine] 长期记忆详情:")
            for i, mem in enumerate(compressed_result.long_term_memory, 1):
                logger.debug(f"  {i}. {mem.content[:80]}...")
        
        logger.info(f"[ContextEngine] ========== 上下文优化结束 ==========")
        
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
        logger.info("[ContextEngine] ========== 开始知识提取 ==========")
        
        # 获取最近的对话历史
        messages = await self.session_manager.get_recent_history()
        
        if not messages:
            logger.info("[ContextEngine] 没有对话历史可供提取知识")
            return []
        
        logger.info(f"[ContextEngine] 准备从 {len(messages)} 条对话中提取知识")
        
        # 提取知识
        knowledge = await self.extractor.extract(messages)
        
        if not knowledge:
            logger.info("[ContextEngine] 未提取到任何知识")
            return []
        
        logger.info(f"[ContextEngine] ✓ 知识提取完成 - 提取到 {len(knowledge)} 条知识")
        logger.debug(f"[ContextEngine] 提取的知识详情:")
        for i, k in enumerate(knowledge, 1):
            logger.debug(f"  {i}. [{k.type.value}] {k.content[:80]}... (置信度: {k.confidence:.2f})")
        
        # 自动存储到长期记忆
        if auto_store:
            logger.info(f"[ContextEngine] 存储知识到长期记忆...")
            await self.memory_bank.store(knowledge)
        
        logger.info(f"[ContextEngine] ========== 知识提取结束 ==========")
        
        return knowledge
    
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
