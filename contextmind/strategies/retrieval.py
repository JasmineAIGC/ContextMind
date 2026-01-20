"""
Retrieval Strategies - DEPRECATED

This module is deprecated. Please use contextmind.strategies.memory.retrievers instead.

DEPRECATION NOTICE (v6.0):
This module will be removed in v7.0. Please update your imports:
    OLD: from contextmind.strategies.retrieval import SemanticRetrievalStrategy
    NEW: from contextmind.strategies.memory.retrievers import SemanticSearchRetriever
    
Or use the plugin registry:
    from contextmind import registry
    retriever = registry.get_retriever('semantic')
"""

import warnings

# Compatibility imports from new location
from .memory.retrievers import (
    SemanticSearchRetriever as SemanticRetrievalStrategy,
    HybridRetriever as HybridRetrievalStrategy,
    LocatorRetriever as LocatorRetrievalStrategy,
)
from .base import RetrievalStrategy

# Show deprecation warning once
warnings.warn(
    "contextmind.strategies.retrieval is deprecated and will be removed in v7.0. "
    "Use contextmind.strategies.memory.retrievers or the plugin registry instead.",
    DeprecationWarning,
    stacklevel=2
)

__all__ = [
    'RetrievalStrategy',
    'SemanticRetrievalStrategy',
    'HybridRetrievalStrategy',
    'LocatorRetrievalStrategy',
]
