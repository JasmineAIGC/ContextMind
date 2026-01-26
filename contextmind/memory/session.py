"""
SessionManager - Session Management

Manages conversation sessions and message history.
"""

import uuid
from typing import List, Optional, Any
from datetime import datetime

from ..core.data_models import Message
from ..core.types import MessageRole
from ..utils.logger import get_logger

logger = get_logger(__name__)


class SessionManager:
    """
    会话管理器
    
    提供对话会话的创建、管理和查询功能, 是上下文优化框架的核心组件之一
    
    主要功能:
    - 创建和管理会话
    - 添加用户和助手消息
    - 获取最近的对话历史
    - 清空会话历史
    
    Attributes:
        app_name: 应用名称
        user_id: 用户 ID
        max_recent_events: 保留的最大近期事件数量
    """
    
    def __init__(
        self,
        session_service: Optional[Any] = None,  # 保留参数以保持兼容性, 但不再使用
        app_name: str = "default_app",
        user_id: str = "default_user",
        max_recent_events: int = 9999,
    ):
        """
        初始化会话管理器
        
        Args:
            session_service: 会话服务实例 (可选, 暂不使用)
            app_name: 应用名称, 用于区分不同应用
            user_id: 用户 ID, 用于区分不同用户
            max_recent_events: 保留的最大近期事件数量, 默认 9999 (实际不限制)
        """
        self.app_name = app_name
        self.user_id = user_id
        self.max_recent_events = max_recent_events
        self._session_id: str = str(uuid.uuid4())
        self._messages: List[Message] = []  # 使用本地缓存
    
    async def _ensure_session(self) -> None:
        """确保会话存在, 如果不存在则创建"""
        if not self._session_id:
            self._session_id = str(uuid.uuid4())
            logger.debug(f"创建新会话: {self._session_id}")
    
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
