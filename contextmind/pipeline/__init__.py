"""管道处理组件。"""

from .preprocessor import InputPreprocessor as Preprocessor
from .context_retriever import ContextRetriever
from .compressor import ContextCompressor
from .reorderer import ContextReorderer
from .kvcache import KVCacheManager
from .postprocessor import PostProcessor
from .summarizer import (
    SummarizerStrategy as BaseSummarizer,
    LLMBasedSummarizer,
    RuleBasedSummarizer,
)

# 向后兼容
InputPreprocessor = Preprocessor

__all__ = [
    "Preprocessor",
    "InputPreprocessor",
    "ContextRetriever",
    "ContextCompressor",
    "ContextReorderer",
    "KVCacheManager",
    "PostProcessor",
    "BaseSummarizer",
    "LLMBasedSummarizer",
    "RuleBasedSummarizer",
]
