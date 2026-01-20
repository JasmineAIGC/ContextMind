"""
Memory Plugin Architecture

This module provides a plugin-based architecture for MemoryBank operations:
- Extractors: Extract valuable information from conversations
- Retrievers: Retrieve relevant memories based on queries
- Updaters: Update and maintain the memory bank

Each category has a base interface and multiple implementations.
"""

from .extractors import (
    BaseExtractor,
    RuleBasedExtractor,
    LLMEntityExtractor,
    ImportancePredictorExtractor,
)

from .retrievers import (
    BaseRetriever,
    SemanticSearchRetriever,
    HybridRetriever,
    LocatorRetriever,
)

from .updaters import (
    BaseUpdater,
    SimpleUpdater,
    ConflictResolverUpdater,
    AdaptiveEvictionUpdater,
)

__all__ = [
    # Extractors
    'BaseExtractor',
    'RuleBasedExtractor',
    'LLMEntityExtractor',
    'ImportancePredictorExtractor',
    
    # Retrievers
    'BaseRetriever',
    'SemanticSearchRetriever',
    'HybridRetriever',
    'LocatorRetriever',
    
    # Updaters
    'BaseUpdater',
    'SimpleUpdater',
    'ConflictResolverUpdater',
    'AdaptiveEvictionUpdater',
]
