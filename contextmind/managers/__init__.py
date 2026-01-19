"""
ContextMind Managers - 管理器模块

提供会话管理的封装，简化对 Google ADK 服务的使用。
"""

from .session_manager import SessionManager

__all__ = [
    "SessionManager",
]
