"""
MemoryManager - 记忆管理器

封装 Google ADK Memory Service，提供简化的长期记忆管理接口。
负责管理长期记忆的存储和检索，支持知识植入和智能检索。
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
    - 检索相关记忆
    - 存储知识到长期记忆
    - 植入记忆种子
    
    Attributes:
        memory_service: ADK Memory Service 实例（可选）
        app_name: 应用名称
        user_id: 用户ID
        session_service: Session Service 实例（用于创建临时会话）
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
    
    async def retrieve(self, query: str, limit: int = 5) -> List[ContextItem]:
        """
        检索相关记忆
        
        根据查询字符串从长期记忆中检索相关的上下文信息。
        
        Args:
            query: 查询字符串
            limit: 返回的最大记忆数量
            
        Returns:
            上下文条目列表，按相关性排序
        """
        if not self.memory_service:
            logger.debug("Memory service is not configured, returning empty list")
            return []
        
        try:
            # 调用 Memory Service 搜索
            response = await self.memory_service.search_memory(
                app_name=self.app_name,
                user_id=self.user_id,
                query=query
            )
            
            if not response or not response.memories:
                logger.debug(f"No memories found for query: {query}")
                return []
            
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
            
            logger.debug(f"Retrieved {len(items)} memories for query: {query}")
            return items
            
        except Exception as e:
            logger.warning(f"Failed to retrieve memories: {str(e)}")
            return []
    
    async def store(self, knowledge: List[Knowledge]) -> None:
        """
        存储知识到长期记忆
        
        将提取的知识存储到长期记忆中，供后续检索使用。
        
        Args:
            knowledge: 知识列表
        """
        if not self.memory_service:
            logger.debug("Memory service is not configured, cannot store knowledge")
            return
        
        if not knowledge:
            logger.debug("No knowledge to store")
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
            
            logger.debug(f"Stored {len(knowledge)} knowledge items to memory")
            
        except Exception as e:
            logger.warning(f"Failed to store knowledge: {str(e)}")
    
    async def seed(self, facts: List[str]) -> None:
        """
        植入记忆种子
        
        在初始化时植入预定义的知识，作为长期记忆的基础。
        
        Args:
            facts: 事实字符串列表
        """
        if not self.memory_service:
            logger.debug("Memory service is not configured, cannot seed memory")
            return
        
        if not facts:
            logger.debug("No facts to seed")
            return
        
        # 过滤空字符串和过短的事实
        valid_facts = [f.strip() for f in facts if f.strip() and len(f.strip()) > 5]
        if not valid_facts:
            logger.debug("All facts are empty or too short, skipping seed")
            return
        
        logger.info(f"Seeding {len(valid_facts)} facts into long-term memory...")
        
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
            logger.error(f"Failed to seed memory: {str(e)}")
    
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
