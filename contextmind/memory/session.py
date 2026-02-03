"""
SessionManager - 会话管理

管理对话会话和消息历史。
支持原生实现和可选的 ADK (Agent Development Kit) 集成。

版本: v0.4.0
"""

import uuid
from typing import List, Optional, Any
from datetime import datetime

from ..core.data_models import Message
from ..core.types import MessageRole
from utils.logger import get_logger

# 尝试导入 ADK 适配器
try:
    from utils.adk_adapter import is_adk_available, ADK_AVAILABLE
    if ADK_AVAILABLE:
        from google.adk.sessions import InMemorySessionService
    else:
        InMemorySessionService = None  # type: ignore
except ImportError:
    ADK_AVAILABLE = False
    InMemorySessionService = None  # type: ignore

logger = get_logger(__name__)


class SessionManager:
    """
    会话管理器
    
    提供对话会话的创建、管理和查询功能, 是上下文优化框架的核心组件之一。
    支持原生实现和可选的 ADK (Agent Development Kit) 会话服务集成。
    
    主要功能:
    - 创建和管理会话
    - 添加用户和助手消息
    - 获取最近的对话历史
    - 清空会话历史
    - 可选的 ADK InMemorySessionService 集成
    
    Attributes:
        app_name: 应用名称
        user_id: 用户 ID
        max_recent_events: 保留的最大近期事件数量
        use_adk: 是否使用 ADK 会话服务
    """
    
    def __init__(
        self,
        session_service: Optional[Any] = None,
        app_name: str = "default_app",
        user_id: str = "default_user",
        max_recent_events: int = 9999,
        use_adk: bool = False,
    ):
        """
        初始化会话管理器
        
        Args:
            session_service: 会话服务实例 (可选，可传入 ADK InMemorySessionService)
            app_name: 应用名称, 用于区分不同应用
            user_id: 用户 ID, 用于区分不同用户
            max_recent_events: 保留的最大近期事件数量, 默认 9999 (实际不限制)
            use_adk: 是否使用 ADK 会话服务 (默认 False，向后兼容)
        """
        self.app_name = app_name
        self.user_id = user_id
        self.max_recent_events = max_recent_events
        self._session_id: str = str(uuid.uuid4())
        self._messages: List[Message] = []  # 使用本地缓存
        
        # ADK 集成支持
        self.use_adk = use_adk and ADK_AVAILABLE
        self._adk_session_service = None
        self._adk_session = None
        
        if self.use_adk:
            if session_service and ADK_AVAILABLE:
                self._adk_session_service = session_service
            elif ADK_AVAILABLE and InMemorySessionService:
                self._adk_session_service = InMemorySessionService()
            logger.info(f"[SessionManager] 使用 ADK 会话服务 - app: {app_name}")
        else:
            logger.debug(f"[SessionManager] 使用原生会话管理 - app: {app_name}")
    
    def get_session(self) -> Optional[Any]:
        """
        获取当前会话对象
        
        Returns:
            如果使用 ADK，返回 ADK Session；否则返回 None
        """
        return self._adk_session
    
    async def _ensure_session(self) -> None:
        """确保会话存在, 如果不存在则创建"""
        if not self._session_id:
            self._session_id = str(uuid.uuid4())
            logger.debug(f"创建新会话: {self._session_id}")
        
        # 如果使用 ADK，确保 ADK 会话存在
        if self.use_adk and self._adk_session_service and self._adk_session is None:
            try:
                self._adk_session = await self._adk_session_service.get_session(
                    app_name=self.app_name,
                    user_id=self.user_id,
                    session_id=self._session_id,
                )
                if self._adk_session is None:
                    self._adk_session = await self._adk_session_service.create_session(
                        app_name=self.app_name,
                        user_id=self.user_id,
                        session_id=self._session_id,
                    )
                    logger.debug(f"[ADK] 创建新会话: {self._session_id}")
            except Exception as e:
                logger.warning(f"[ADK] 会话创建失败，回退到原生模式: {e}")
                self.use_adk = False
    
    async def add_message(self, role: MessageRole, content: str) -> None:
        """
        添加消息到会话
        
        Args:
            role: 消息角色 (USER, ASSISTANT, SYSTEM)
            content: 消息内容
        """
        await self._ensure_session()
        
        # 直接添加到本地缓存
        message = Message(
            role=role,
            content=content,
            timestamp=datetime.now(),
            metadata={}
        )
        self._messages.append(message)
        
        logger.debug(f"添加 {role.value} 消息到会话")
    
    async def get_recent_history(self, limit: Optional[int] = None) -> List[Message]:
        """
        获取最近的对话历史
        
        Args:
            limit: 返回的最大消息数量, 默认使用 max_recent_events
            
        Returns:
            消息列表, 按时间顺序排列
        """
        await self._ensure_session()
        
        num_events = limit if limit is not None else self.max_recent_events
        
        # 从本地缓存返回
        if num_events >= len(self._messages):
            return self._messages.copy()
        else:
            return self._messages[-num_events:].copy()
    
    async def clear(self) -> None:
        """
        清空当前会话
        
        创建一个新的会话来替换当前会话
        """
        # 如果使用 ADK，删除 ADK 会话
        if self.use_adk and self._adk_session_service and self._adk_session:
            try:
                await self._adk_session_service.delete_session(
                    app_name=self.app_name,
                    user_id=self.user_id,
                    session_id=self._session_id,
                )
                self._adk_session = None
                logger.debug("[ADK] 会话已删除")
            except Exception as e:
                logger.warning(f"[ADK] 删除会话失败: {e}")
        
        # 清空本地缓存并创建新会话 ID
        self._messages.clear()
        self._session_id = str(uuid.uuid4())
        logger.debug("会话已清空, 创建新会话")
    
    async def get_session_id(self) -> str:
        """
        获取当前会话 ID
        
        Returns:
            会话 ID 字符串
        """
        await self._ensure_session()
        return self._session_id
