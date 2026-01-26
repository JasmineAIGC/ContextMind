"""
Memory Submodule - MemoryBank Architecture

Implements the MemoryBank component from the pipeline architecture with 4 sub-modules:
- Extractor: Extract high-value information
- Retriever: Retrieve relevant memories  
- Updater: Intelligent updates (Add/Delete/Update)
- Bank: Main MemoryBank class

Also includes SessionManager for session management.
"""

from .bank import MemoryBank, STOPWORDS
from .session import SessionManager
from .extractor import (
    BaseExtractor,
    RuleBasedExtractor,
    LLMBasedExtractor,
    ImportancePredictorExtractor,
)
from .retriever import (
    BaseRetriever,
    SemanticSearchRetriever,
)
from .updater import (
    BaseUpdater,
    SimpleUpdater,
)

__all__ = [
    # Main MemoryBank
    "MemoryBank",
    "STOPWORDS",
    "SessionManager",
    
    # Extractors (Step 1: Extract high-value info)
    "BaseExtractor",
    "RuleBasedExtractor",
    "LLMBasedExtractor",
    "ImportancePredictorExtractor",
    
    # Retrievers (Step 2: Retrieve relevant memories)
    "BaseRetriever",
    "SemanticSearchRetriever",
    
    # Updaters (Step 3: Update memory bank)
    "BaseUpdater",
    "SimpleUpdater",
]
