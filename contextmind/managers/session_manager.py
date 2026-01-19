"""
SessionManager - 会话管理器

封装 Google ADK Session Service，提供简化的会话管理接口。
负责管理短期对话历史，支持添加消息、获取历史和清空会话。
"""

from typing import List, Optional, Any
import uuid

# Optional google.adk imports
try:
    from google.adk.events.event import Event
    from google.adk.sessions.base_session_service import BaseSessionService, GetSessionConfig
    from google.adk.sessions import Session
    from google.genai.types import Content, Part
    _HAS_GOOGLE_ADK = True
except ImportError:
    _HAS_GOOGLE_ADK = False
    Event = Any
    BaseSessionService = Any
    GetSessionConfig = Any
    Session = Any
    Content = Any
    Part = Any

from ..data_models import Message, MessageRole
from ..logger import get_logger

logger = get_logger(__name__)


class SessionManager:
    """
    会话管理器 - 封装 ADK Session Service
    
    提供对话会话的创建、管理和查询功能，是上下文优化框架的核心组件之一。
    
    主要功能：
    - 创建和管理会话
    - 添加用户和助手消息
    - 获取最近的对话历史
    - 清空会话历史
    
    Attributes:
        session_service: ADK Session Service 实例
        app_name: 应用名称
        user_id: 用户ID
        max_recent_events: 保留的最大近期事件数量
    """
    
    def __init__(
        self,
        session_service: Optional[BaseSessionService],
        app_name: str,
        user_id: str,
        max_recent_events: int = 9999,
    ):
        """
        初始化会话管理器
        
        Args:
            session_service: ADK Session Service 实例 (可选)
            app_name: 应用名称，用于区分不同应用
            user_id: 用户ID，用于区分不同用户
            max_recent_events: 保留的最大近期事件数量，默认9999（实际不限制）
        """
        if session_service and not _HAS_GOOGLE_ADK:
            raise ImportError(
                "google.adk is required when session_service is provided. "
                "Install it or use None for session_service."
            )
        self.session_service = session_service
        self.app_name = app_name
        self.user_id = user_id
        self.max_recent_events = max_recent_events
        self._session_id: Optional[str] = None
    
    async def _ensure_session(self) -> None:
        """确保会话存在，如果不存在则创建"""
        if self._session_id:
            try:
                session = await self.session_service.get_session(
                    app_name=self.app_name,
                    user_id=self.user_id,
                    session_id=self._session_id,
                )
                if session:
                    return
            except Exception as e:
                logger.debug(f"Failed to get existing session: {str(e)}")
        
        # 创建新会话
        session = await self.session_service.create_session(
            app_name=self.app_name,
            user_id=self.user_id,
        )
        self._session_id = session.id
        logger.debug(f"Created new session: {self._session_id}")
    
    async def add_message(self, role: MessageRole, content: str) -> None:
        """
        添加消息到会话
        
        Args:
            role: 消息角色（USER, ASSISTANT, SYSTEM）
            content: 消息内容
        """
        await self._ensure_session()
        
        # 创建事件
        event = Event(
            invocation_id=self._new_invocation_id(),
            author=role.value,
            content=Content(role=role.value, parts=[Part(text=content)]),
        )
        
        # 获取会话并添加事件
        session = await self._get_session()
        await self.session_service.append_event(session=session, event=event)
        
        logger.debug(f"Added {role.value} message to session")
    
    async def get_recent_history(self, limit: Optional[int] = None) -> List[Message]:
        """
        获取最近的对话历史
        
        Args:
            limit: 返回的最大消息数量，默认使用 max_recent_events
            
        Returns:
            消息列表，按时间顺序排列
        """
        await self._ensure_session()
        
        num_events = limit if limit is not None else self.max_recent_events
        config = GetSessionConfig(num_recent_events=num_events)
        
        session = await self.session_service.get_session(
            app_name=self.app_name,
            user_id=self.user_id,
            session_id=self._session_id,
            config=config,
        )
        
        if not session or not session.events:
            return []
        
        # 转换事件为消息
        messages = []
        for event in session.events:
            content = self._content_to_text(event.content)
            if not content:
                continue
            
            # 确定角色
            try:
                role = MessageRole(event.author)
            except ValueError:
                # 如果角色不是标准的，使用 SYSTEM
                role = MessageRole.SYSTEM
            
            messages.append(Message(
                role=role,
                content=content,
                timestamp=event.timestamp if hasattr(event, 'timestamp') else None,
                metadata={}
            ))
        
        return messages
    
    async def clear(self) -> None:
        """
        清空当前会话
        
        创建一个新的会话来替换当前会话。
        """
        # 创建新会话
        session = await self.session_service.create_session(
            app_name=self.app_name,
            user_id=self.user_id,
        )
        self._session_id = session.id
        logger.debug("Session cleared, new session created")
    
    async def get_session_id(self) -> str:
        """
        获取当前会话ID
        
        Returns:
            会话ID字符串
        """
        await self._ensure_session()
        return self._session_id
    
    async def _get_session(self) -> Session:
        """获取完整的会话对象（内部使用）"""
        if not self._session_id:
            raise RuntimeError("Session has not been initialized")
        
        session = await self.session_service.get_session(
            app_name=self.app_name,
            user_id=self.user_id,
            session_id=self._session_id,
        )
        
        if not session:
            raise RuntimeError("Unable to load session from SessionService")
        
        return session
    
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
