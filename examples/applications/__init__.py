"""Applications Package"""

from .base import BaseApplication
from .callcenter import CallCenterApplication
from .chat import ChatApplication, CHAT_SYSTEM_PROMPT

__all__ = [
    "BaseApplication",
    "CallCenterApplication",
    "ChatApplication",
    "CHAT_SYSTEM_PROMPT"
]
