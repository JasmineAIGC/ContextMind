"""
Adapters - 对话系统适配器层

提供标准化接口，支持将 ContextMind 接入任意对话系统。

主要组件：
- BaseAdapter: 适配器基类
- OpenAIAdapter: OpenAI 对话系统适配器
- LangChainAdapter: LangChain 适配器
- CustomAdapter: 自定义对话系统适配器
"""

from .base import BaseAdapter, DialogContext, DialogMessage
from .openai_adapter import OpenAIAdapter
from .langchain_adapter import LangChainAdapter
from .custom_adapter import CustomAdapter

__all__ = [
    "BaseAdapter",
    "DialogContext",
    "DialogMessage",
    "OpenAIAdapter",
    "LangChainAdapter",
    "CustomAdapter",
]
