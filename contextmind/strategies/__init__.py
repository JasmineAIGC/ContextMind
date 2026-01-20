"""
Strategies module for ContextMind v7.0

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
    IntegrationStrategy,
    OptimizationStrategy,
)

# Plugin implementations
from . import extractors, retrievers, updaters

# Create a simple BaseStrategy alias for backwards compatibility
BaseStrategy = ExtractionStrategy

__all__ = [
    # Base strategy interfaces
    'ExtractionStrategy',
    'RetrievalStrategy',
    'IntegrationStrategy',
    'OptimizationStrategy',
    'BaseStrategy',
    # Plugin modules
    'extractors',
    'retrievers',
    'updaters',
]
