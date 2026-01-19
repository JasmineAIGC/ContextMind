"""
ContextEngine - 上下文引擎核心模块 v4.0

清晰的模块化架构设计：
- 应用层：使用引擎的应用（示例：客服、聊天机器人等）
- 适配器层：对话系统集成接口
- 引擎层：ContextEngine 统一接口
- 模块层：InputPreprocessor, ContextRetriever, MemoryBank, ContextCompressor, ContextReorderer, KnowledgeExtractor
- 策略层：可插拔的策略实现
- 基础层：TokenizerService, VectorClient, CacheManager

核心职责：
1. 上下文优化 (optimize)
2. 上下文更新 (update)
3. 知识提取 (extract_knowledge)
"""

from __future__ import annotations

from typing import Optional, List, Any
from datetime import datetime

from google.adk.memory import InMemoryMemoryService
from google.adk.memory.base_memory_service import BaseMemoryService
from google.adk.sessions import InMemorySessionService
from google.adk.sessions.base_session_service import BaseSessionService

from .client import Client
from .logger import get_logger
from .data_models import (
    Message,
    MessageRole,
    ContextResult,
    ContextItem,
    ContextSource,
    ProcessedContext,
    Knowledge,
)
from .managers import SessionManager
from .modules import (
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
        from google.adk.memory import InMemoryMemoryService
        
        client = Client()
        engine = ContextEngine(
            app_name="my-app",
            user_id="user-123",
            llm_client=client,
            memory_service=InMemoryMemoryService()
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
        session_service: Optional[BaseSessionService] = None,
        memory_service: Optional[BaseMemoryService] = None,
        max_recent_events: int = 9999,
    ):
        """
        初始化上下文引擎
        
        Args:
            app_name: 应用名称
            user_id: 用户ID
            llm_client: LLM客户端实例（可选）
            session_service: Session服务实例，默认使用InMemorySessionService
            memory_service: Memory服务实例，默认使用InMemoryMemoryService
            max_recent_events: 保留的最大近期事件数量（默认9999，实际不限制）
        """
        self.app_name = app_name
        self.user_id = user_id
        self.llm_client = llm_client
        
        # 初始化服务
        if session_service is None:
            self.session_service = InMemorySessionService()
        else:
            self.session_service = session_service
            
        if memory_service is None:
            self.memory_service = InMemoryMemoryService()
        else:
            self.memory_service = memory_service
        
        # 初始化管理器
        self.session_manager = SessionManager(
            session_service=self.session_service,
            app_name=app_name,
            user_id=user_id,
            max_recent_events=max_recent_events,
        )
        
        # 初始化记忆库
        self.memory_bank = MemoryBank(
            memory_service=self.memory_service,
            session_service=self.session_service,
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
        logger.debug(f"Optimizing context for input: {user_input}")
        
        # 1. 预处理输入
        processed_input = await self.preprocessor.process(user_input)
        
        # 2. 检索上下文（RAG）
        retrieved_context = await self.retriever.retrieve(
            query=processed_input,
            include_session=include_session,
            include_memory=include_memory,
            include_knowledge=include_knowledge,
        )
        
        # 3. 重排序上下文
        reordered_context = await self.reorderer.reorder(retrieved_context)
        
        # 4. 压缩上下文
        compressed_result = await self.compressor.compress(reordered_context)
        
        logger.debug(
            f"Context optimized: {len(compressed_result.recent_history)} history, "
            f"{len(compressed_result.long_term_memory)} memory items"
        )
        
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
        logger.debug(f"Updating context with new messages")
        
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
        
        logger.debug("Context updated successfully")
    
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
        logger.debug("Extracting knowledge from recent conversation")
        
        # 获取最近的对话历史
        messages = await self.session_manager.get_recent_history()
        
        if not messages:
            logger.debug("No messages to extract knowledge from")
            return []
        
        # 提取知识
        knowledge = await self.extractor.extract(messages)
        
        # 自动存储到长期记忆
        if auto_store and knowledge:
            await self.memory_bank.store(knowledge)
            logger.info(f"Extracted and stored {len(knowledge)} knowledge items")
        else:
            logger.info(f"Extracted {len(knowledge)} knowledge items")
        
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
