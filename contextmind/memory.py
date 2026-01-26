"""
Memory Module - Unified Memory Management (Backward Compatibility Wrapper)

This module provides backward compatibility by re-exporting from the new memory/ submodule.

New structure:
- memory/bank.py: MemoryBank
- memory/session.py: SessionManager  
- memory/extractor.py: Extractors
- memory/retriever.py: Retrievers
- memory/updater.py: Updaters

For new code, import directly from memory/ submodule:
    from contextmind.memory import MemoryBank, SessionManager
    from contextmind.memory import BaseExtractor, BaseRetriever, BaseUpdater
"""

# Re-export from memory/ submodule for backward compatibility
from .memory import (
    MemoryBank,
    STOPWORDS,
    SessionManager,
    BaseExtractor,
    RuleBasedExtractor,
    LLMBasedExtractor,
    ImportancePredictorExtractor,
    BaseRetriever,
    SemanticSearchRetriever,
    BaseUpdater,
    SimpleUpdater,
)

# Re-export KVCacheManager from kvcache.py
from .kvcache import (
    KVCacheManager,
    KVCacheManagerStrategy,
    SlidingWindowStrategy,
)

__all__ = [
    # MemoryBank
    "MemoryBank",
    "STOPWORDS",
    "SessionManager",
    
    # Extractors
    "BaseExtractor",
    "RuleBasedExtractor",
    "LLMBasedExtractor",
    "ImportancePredictorExtractor",
    
    # Retrievers
    "BaseRetriever",
    "SemanticSearchRetriever",
    
    # Updaters
    "BaseUpdater",
    "SimpleUpdater",
    
    # KVCache
    "KVCacheManager",
    "KVCacheManagerStrategy",
    "SlidingWindowStrategy",
]
