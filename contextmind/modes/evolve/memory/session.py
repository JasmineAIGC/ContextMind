"""
SessionManager - 会话管理

管理对话会话和消息历史。
"""

import uuid
from typing import List, Optional, Any
from datetime import datetime

from ..core.data_models import Message
from ..core.types import MessageRole
from contextmind.infra.logger import get_logger

logger = get_logger(__name__)


class SessionManager:
    """会话管理器，提供对话会话的创建、管理和查询功能。"""
    
    def __init__(
        self,
        session_service: Optional[Any] = None,  # 保留参数以保持兼容性, 但不再使用
        app_name: str = "default_app",
        user_id: str = "default_user",
        max_recent_events: int = 9999,
    ):
        """
        Args:
            session_service: 保留参数以保持兼容性，不再使用
            app_name: 应用名称
            user_id: 用户 ID
            max_recent_events: 保留的最大近期事件数量
        """
        self.app_name = app_name
        self.user_id = user_id
        self.max_recent_events = max_recent_events
        self._session_id: str = str(uuid.uuid4())
        self._messages: List[Message] = []  # In-memory store; no external persistence needed
    
    async def _ensure_session(self) -> None:
        if not self._session_id:
            self._session_id = str(uuid.uuid4())
            logger.debug(f"创建新会话: {self._session_id}")
    
    async def add_message(self, role: MessageRole, content: str) -> None:
        """添加消息到会话。"""
        await self._ensure_session()
        
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
        获取最近的对话历史。

        Args:
            limit: 返回的最大消息数量，默认使用 max_recent_events

        Returns:
            消息列表，按时间顺序排列
        """
        await self._ensure_session()
        
        num_events = limit if limit is not None else self.max_recent_events
        
        # Return a copy to prevent callers from mutating internal state.
        if num_events >= len(self._messages):
            return self._messages.copy()
        else:
            return self._messages[-num_events:].copy()
    
    async def clear(self) -> None:
        """清空当前会话，创建新会话 ID。"""
        self._messages.clear()
        self._session_id = str(uuid.uuid4())
        logger.debug("会话已清空, 创建新会话")
    
    async def get_session_id(self) -> str:
        await self._ensure_session()
        return self._session_id
