"""
Strategies module for ContextMind v7.0

This module contains plugin-based strategies for context engineering:
- Base strategy interfaces (base.py)
- Default implementations (defaults.py)
- Knowledge extraction plugins (now in memory.extractor)
- Memory retrieval plugins (now in memory.retriever)
- Memory update plugins (now in memory.updater)

All strategies follow a plugin architecture pattern for easy swapping and extension.
"""

from .base import (
    ExtractionStrategy,
    RetrievalStrategy,
    IntegrationStrategy,
    OptimizationStrategy,
)

from .defaults import (
    CompressionStrategy,
    RerankingStrategy,
)

# Import plugin implementations from new memory submodule
from ..memory import extractor, retriever, updater

# Alias for backwards compatibility
extractors = extractor
retrievers = retriever
updaters = updater

# Create a simple BaseStrategy alias for backwards compatibility
BaseStrategy = ExtractionStrategy

__all__ = [
    # Base strategy interfaces
    'ExtractionStrategy',
    'RetrievalStrategy',
    'IntegrationStrategy',
    'OptimizationStrategy',
    'BaseStrategy',
    # Default strategies
    'CompressionStrategy',
    'RerankingStrategy',
    # Plugin modules (aliases to memory submodule)
    'extractors',
    'retrievers',
    'updaters',
    # Direct access
    'extractor',
    'retriever',
    'updater',
]
