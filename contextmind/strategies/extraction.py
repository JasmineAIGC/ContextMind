"""
Extraction Strategies - DEPRECATED

This module is deprecated. Please use contextmind.strategies.memory.extractors instead.

DEPRECATION NOTICE (v6.0):
This module will be removed in v7.0. Please update your imports:
    OLD: from contextmind.strategies.extraction import RuleBasedExtractionStrategy
    NEW: from contextmind.strategies.memory.extractors import RuleBasedExtractor
    
Or use the plugin registry:
    from contextmind import registry
    extractor = registry.get_extractor('rule_based')
"""

import warnings

# Compatibility imports from new location
from .memory.extractors import (
    RuleBasedExtractor as RuleBasedExtractionStrategy,
    LLMEntityExtractor as LLMExtractionStrategy,
    ImportancePredictorExtractor as ImportanceExtractionStrategy,
)
from .base import ExtractionStrategy

# Show deprecation warning once
warnings.warn(
    "contextmind.strategies.extraction is deprecated and will be removed in v7.0. "
    "Use contextmind.strategies.memory.extractors or the plugin registry instead.",
    DeprecationWarning,
    stacklevel=2
)

__all__ = [
    'ExtractionStrategy',
    'RuleBasedExtractionStrategy',
    'LLMExtractionStrategy',
    'ImportanceExtractionStrategy',
]
