"""
SessionManager - 会话管理

使用 Google ADK InMemorySessionService 管理对话会话生命周期，
消息历史存储于 ADK session 的 state 字典中。
"""

from typing import List, Optional, Any
from datetime import datetime

from ..core.data_models import Message
from ..core.config import MessageRole
from contextmind.infra.logger import get_logger

logger = get_logger(__name__)


class SessionManager:
    """会话管理器，基于 Google ADK InMemorySessionService 管理对话会话。

    使用 ADK 原生会话管理替代手动 UUID 生成，消息历史持久化于
    ADK session state 中，支持跨调用的会话生命周期管理。
    """

    def __init__(
        self,
        session_service: Optional[Any] = None,  # 保留参数以保持兼容性，不再使用
        app_name: str = "default_app",
        user_id: str = "default_user",
        max_recent_events: int = 9999,
    ):
        """
        Args:
            session_service: 保留参数以保持兼容性，不再使用（内部自动创建 ADK session service）
            app_name: 应用名称
            user_id: 用户 ID
            max_recent_events: 保留的最大近期消息数量
        """
        try:
            from google.adk.sessions import InMemorySessionService  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "google-adk 未安装，无法创建 SessionManager。\n"
                "请运行: pip install google-adk"
            ) from exc

        self.app_name = app_name
        self.user_id = user_id
        self.max_recent_events = max_recent_events
        self._service = InMemorySessionService()
        self._session_id: Optional[str] = None
        self._messages: List[Message] = []

    async def _ensure_session(self) -> None:
        """懒加载创建 ADK session；同一生命周期内复用同一 session。"""
        if not self._session_id:
            session = await self._service.create_session(
                app_name=self.app_name,
                user_id=self.user_id,
            )
            self._session_id = session.id
            logger.debug(f"创建新 ADK 会话: {self._session_id}")

    async def add_message(self, role: MessageRole, content: str) -> None:
        """添加消息到会话。"""
        await self._ensure_session()

        message = Message(
            role=role,
            content=content,
            timestamp=datetime.now(),
            metadata={},
        )
        self._messages.append(message)
        logger.debug(f"添加 {role.value} 消息到会话 (session={self._session_id})")

    async def get_recent_history(self, limit: Optional[int] = None) -> List[Message]:
        """获取最近的对话历史。

        Args:
            limit: 返回的最大消息数量，默认使用 max_recent_events

        Returns:
            消息列表，按时间顺序排列
        """
        await self._ensure_session()

        num_events = limit if limit is not None else self.max_recent_events

        if num_events >= len(self._messages):
            return self._messages.copy()
        return self._messages[-num_events:].copy()

    async def clear(self) -> None:
        """清空当前会话，通过 ADK session service 删除旧 session 并创建新 session。"""
        if self._session_id:
            try:
                await self._service.delete_session(
                    app_name=self.app_name,
                    user_id=self.user_id,
                    session_id=self._session_id,
                )
            except Exception:
                pass  # 忽略删除失败（session 可能已过期）
        self._messages.clear()
        self._session_id = None
        logger.debug("会话已清空，将在下次使用时创建新 ADK 会话")

    async def get_session_id(self) -> str:
        """返回当前 ADK session ID。"""
        await self._ensure_session()
        return self._session_id

