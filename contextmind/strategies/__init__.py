"""
Strategies module for ContextMind v6.0

This module contains plugin-based strategies for context engineering:
- Base strategy interfaces (base.py)
- Knowledge extraction plugins (extractors.py)
- Memory retrieval plugins (retrievers.py)
- Memory update plugins (updaters.py)

All strategies follow a plugin architecture pattern for easy swapping and extension.
"""

from .base import (
    ExtractionStrategy,
    RetrievalStrategy,
    UpdateStrategy,
    CompressionStrategy,
    ReorderStrategy,
    PostProcessorStrategy,
    SummarizerStrategy,
    KVCacheManagerStrategy
)

# Plugin implementations
from . import extractors, retrievers, updaters

__all__ = [
    # Base strategy interfaces
    'ExtractionStrategy',
    'RetrievalStrategy',
    'UpdateStrategy',
    'CompressionStrategy',
    'ReorderStrategy',
    'PostProcessorStrategy',
    'SummarizerStrategy',
    'KVCacheManagerStrategy',
    # Plugin modules
    'extractors',
    'retrievers',
    'updaters',
]
