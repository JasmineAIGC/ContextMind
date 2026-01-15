"""
MemoryManager - 记忆管理器

封装 Google ADK Memory Service，提供简化的长期记忆管理接口。
负责管理长期记忆的存储和检索，支持知识植入和智能检索。

上下文工程核心能力：
- 长期记忆存储和检索
- 跨会话的知识持久化
- 基于语义相似度的记忆检索
- 本地缓存提供备用检索
"""

from typing import List, Optional
import uuid

from google.adk.memory.base_memory_service import BaseMemoryService
from google.adk.events.event import Event
from google.adk.sessions.base_session_service import BaseSessionService
from google.genai.types import Content, Part

from ..data_models import ContextItem, ContextSource, Knowledge
from ..logger import get_logger

logger = get_logger(__name__)


class MemoryManager:
    """
    记忆管理器 - 封装 ADK Memory Service
    
    提供长期记忆的存储、检索和管理功能，是上下文优化框架的核心组件之一。
    
    主要功能：
    - 检索相关记忆（支持语义搜索和关键词备用）
    - 存储知识到长期记忆
    - 植入记忆种子
    - 本地缓存用于备用检索
    
    Attributes:
        memory_service: ADK Memory Service 实例（可选）
        app_name: 应用名称
        user_id: 用户ID
        session_service: Session Service 实例（用于创建临时会话）
        _local_cache: 本地记忆缓存，用于备用检索
    """
    
    def __init__(
        self,
        memory_service: Optional[BaseMemoryService],
        session_service: BaseSessionService,
        app_name: str,
        user_id: str,
    ):
        """
        初始化记忆管理器
        
        Args:
            memory_service: ADK Memory Service 实例，如果为None则不使用长期记忆
            session_service: Session Service 实例，用于创建临时会话
            app_name: 应用名称
            user_id: 用户ID
        """
        self.memory_service = memory_service
        self.session_service = session_service
        self.app_name = app_name
        self.user_id = user_id
        
        # 本地缓存：存储所有已存储的知识，用于备用检索
        self._local_cache: List[ContextItem] = []
    
    async def retrieve(self, query: str, limit: int = 5) -> List[ContextItem]:
        """
        检索相关记忆
        
        根据查询字符串从长期记忆中检索相关的上下文信息。
        支持两种检索方式：
        1. 优先使用 Memory Service 的语义搜索
        2. 如果语义搜索无结果，使用本地缓存的关键词匹配
        
        Args:
            query: 查询字符串
            limit: 返回的最大记忆数量
            
        Returns:
            上下文条目列表，按相关性排序
        """
        if not self.memory_service:
            logger.debug("Memory service is not configured, using local cache")
            return self._retrieve_from_cache(query, limit)
        
        try:
            # 调用 Memory Service 搜索
            response = await self.memory_service.search_memory(
                app_name=self.app_name,
                user_id=self.user_id,
                query=query
            )
            
            if response and response.memories:
                # 转换为 ContextItem
                items = []
                for memory in response.memories[:limit]:
                    content = self._content_to_text(memory.content)
                    if not content:
                        continue
                    
                    items.append(ContextItem(
                        content=content,
                        source=ContextSource.MEMORY,
                        score=1.0,  # ADK不提供分数，默认为1.0
                        timestamp=memory.timestamp if hasattr(memory, 'timestamp') else None,
                        metadata={}
                    ))
                
                if items:
                    logger.debug(f"Retrieved {len(items)} memories from Memory Service for query: {query}")
                    return items
            
            # Memory Service 未返回结果，使用本地缓存备用
            logger.debug(f"No memories from Memory Service for query: {query}, using local cache")
            return self._retrieve_from_cache(query, limit)
            
        except Exception as e:
            logger.warning(f"Failed to retrieve memories from Memory Service: {str(e)}, using local cache")
            return self._retrieve_from_cache(query, limit)
    
    def _retrieve_from_cache(self, query: str, limit: int = 5) -> List[ContextItem]:
        """
        从本地缓存检索相关记忆
        
        使用简单的关键词匹配进行检索。
        
        Args:
            query: 查询字符串
            limit: 返回的最大记忆数量
            
        Returns:
            匹配的上下文条目列表
        """
        if not self._local_cache:
            return []
        
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        # 计算每个缓存项的相关性分数
        scored_items = []
        for item in self._local_cache:
            content_lower = item.content.lower()
            
            # 方法1: 完整匹配
            if query_lower in content_lower:
                score = 0.9
            # 方法2: 词语重叠
            else:
                content_words = set(content_lower.split())
                overlap = len(query_words & content_words)
                if overlap > 0:
                    score = 0.5 + (overlap / max(len(query_words), len(content_words))) * 0.4
                else:
                    score = 0
            
            if score > 0:
                scored_items.append((item, score))
        
        # 按分数排序
        scored_items.sort(key=lambda x: x[1], reverse=True)
        
        # 返回前limit个
        result = [
            ContextItem(
                content=item.content,
                source=item.source,
                score=score,
                timestamp=item.timestamp,
                metadata=item.metadata
            )
            for item, score in scored_items[:limit]
        ]
        
        if result:
            logger.debug(f"Retrieved {len(result)} memories from local cache for query: {query}")
        
        return result
    
    async def store(self, knowledge: List[Knowledge]) -> None:
        """
        存储知识到长期记忆
        
        将提取的知识存储到长期记忆中，供后续检索使用。
        同时存储到本地缓存，确保备用检索可用。
        
        Args:
            knowledge: 知识列表
        """
        if not knowledge:
            logger.debug("No knowledge to store")
            return
        
        # 首先添加到本地缓存
        for k in knowledge:
            formatted_content = f"[{k.type.value.upper()}] {k.content}"
            self._local_cache.append(ContextItem(
                content=formatted_content,
                source=ContextSource.MEMORY,
                score=k.confidence,
                metadata=k.metadata
            ))
        
        logger.debug(f"Added {len(knowledge)} items to local cache, total: {len(self._local_cache)}")
        
        # 然后尝试存储到 Memory Service
        if not self.memory_service:
            logger.debug("Memory service is not configured, knowledge stored in local cache only")
            return
        
        try:
            # 创建临时会话来存储知识
            session = await self.session_service.create_session(
                app_name=self.app_name,
                user_id=self.user_id,
            )
            
            # 将知识作为事件添加到会话
            for k in knowledge:
                # 格式化知识内容，包含类型标签
                formatted_content = f"[{k.type.value.upper()}] {k.content}"
                
                event = Event(
                    invocation_id=self._new_invocation_id(),
                    author="system",
                    content=Content(role="system", parts=[Part(text=formatted_content)]),
                )
                await self.session_service.append_event(session=session, event=event)
            
            # 持久化到 Memory Service
            await self.memory_service.add_session_to_memory(session)
            
            logger.debug(f"Stored {len(knowledge)} knowledge items to Memory Service")
            
        except Exception as e:
            logger.warning(f"Failed to store knowledge to Memory Service: {str(e)}, kept in local cache")
    
    async def seed(self, facts: List[str]) -> None:
        """
        植入记忆种子
        
        在初始化时植入预定义的知识，作为长期记忆的基础。
        
        Args:
            facts: 事实字符串列表
        """
        if not facts:
            logger.debug("No facts to seed")
            return
        
        # 过滤空字符串和过短的事实
        valid_facts = [f.strip() for f in facts if f.strip() and len(f.strip()) > 3]
        if not valid_facts:
            logger.debug("All facts are empty or too short, skipping seed")
            return
        
        logger.info(f"Seeding {len(valid_facts)} facts into long-term memory...")
        
        # 首先添加到本地缓存
        for fact in valid_facts:
            self._local_cache.append(ContextItem(
                content=f"[预设知识] {fact}",
                source=ContextSource.MEMORY,
                score=1.0,
                metadata={'seeded': True}
            ))
        
        logger.debug(f"Added {len(valid_facts)} seed facts to local cache")
        
        # 然后尝试添加到 Memory Service
        if not self.memory_service:
            logger.debug("Memory service is not configured, seeds stored in local cache only")
            logger.info(f"Successfully seeded {len(valid_facts)} facts to local cache")
            return
        
        try:
            # 创建临时会话来存储种子知识
            session = await self.session_service.create_session(
                app_name=self.app_name,
                user_id=self.user_id,
            )
            
            # 将种子数据作为系统事件添加到会话
            for fact in valid_facts:
                event = Event(
                    invocation_id=self._new_invocation_id(),
                    author="system",
                    content=Content(role="system", parts=[Part(text=f"[预设知识] {fact}")]),
                )
                await self.session_service.append_event(session=session, event=event)
            
            # 持久化到 Memory Service
            await self.memory_service.add_session_to_memory(session)
            
            logger.info(f"Successfully seeded {len(valid_facts)} facts to memory")
            
        except Exception as e:
            logger.error(f"Failed to seed memory: {str(e)}, kept in local cache")
    
    @staticmethod
    def _content_to_text(content: Optional[Content]) -> str:
        """将 Content 对象转换为纯文本"""
        if not content or not content.parts:
            return ""
        
        fragments: List[str] = []
        for part in content.parts:
            if part.text:
                fragments.append(part.text)
            elif part.function_call:
                fragments.append(f"[FunctionCall] {part.function_call.name}")
            elif part.function_response:
                fragments.append(f"[FunctionResponse] {part.function_response.name}")
            elif part.code_execution_result:
                fragments.append(part.code_execution_result.output_text or "")
        
        return "\n".join(fragment for fragment in fragments if fragment)
    
    @staticmethod
    def _new_invocation_id() -> str:
        """生成新的调用ID"""
        return str(uuid.uuid4())
