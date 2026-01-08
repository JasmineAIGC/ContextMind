"""
ContextMind - 基于 ADK 的上下文工程框架

提供多轮对话的短期记忆（Session）和长期记忆（Memory）管理。
"""

from .client import Client, ClientConfig
from .engine import ContextEngine, ContextTurnResult
from .logger import get_logger, setup_logging, ContextMindLogger

__all__ = [
    "Client",
    "ClientConfig",
    "ContextEngine",
    "ContextTurnResult",
    "get_logger",
    "setup_logging",
    "ContextMindLogger",
]
