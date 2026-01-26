"""
Pipeline Module - Backward Compatibility Wrapper

This module provides backward compatibility by re-exporting from the new modular structure.

New structure (6-step pipeline architecture):
- preprocessor.py: Step 1 - InputPreprocessor
- retriever.py: Step 2 - ContextRetriever (placeholder)
- compressor.py: Step 3 - ContextCompressor
- reorderer.py: Step 4 - ContextReorderer
- kvcache.py: Step 5 - KVCacheManager
- postprocessor.py: Step 6 - PostProcessor

For new code, import directly from individual modules:
    from contextmind.preprocessor import InputPreprocessor
    from contextmind.compressor import ContextCompressor
    from contextmind.reorderer import ContextReorderer
    from contextmind.postprocessor import PostProcessor
"""

# Re-export all pipeline components for backward compatibility
from .preprocessor import InputPreprocessor
from .compressor import ContextCompressor, DEFAULT_MAX_SESSION_ITEMS
from .reorderer import ContextReorderer
from .postprocessor import (
    PostProcessor,
    PostProcessorStrategy,
    RuleBasedPostProcessor,
)

__all__ = [
    # Step 1: Input Preprocessing
    "InputPreprocessor",
    
    # Step 3: Context Compression
    "ContextCompressor",
    "DEFAULT_MAX_SESSION_ITEMS",
    
    # Step 4: Context Reordering
    "ContextReorderer",
    
    # Step 6: Output Post-processing
    "PostProcessor",
    "PostProcessorStrategy",
    "RuleBasedPostProcessor",
]
