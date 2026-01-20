"""
Adapters - Adapter layer

Provides adapters for LLM frameworks, vector stores, and caching.
"""

from .base import BaseAdapter, DialogContext, DialogMessage
from .llm import OpenAIAdapter, LangChainAdapter, CustomAdapter
from .vector import VectorClient, VectorSearchResult
from .cache import CacheManager, CacheEntry

__all__ = [
    "BaseAdapter",
    "DialogContext",
    "DialogMessage",
    "OpenAIAdapter",
    "LangChainAdapter",
    "CustomAdapter",
    "VectorClient",
    "VectorSearchResult",
    "CacheManager",
    "CacheEntry",
]

