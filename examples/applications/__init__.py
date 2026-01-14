"""
Applications Layer

包含使用 ContextMind 的应用层实现示例。
"""

from .base import BaseApplication
from .callcenter import CallCenterApp

__all__ = [
    "BaseApplication",
    "CallCenterApp",
]
