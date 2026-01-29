"""管道处理组件。"""

from .preprocessor import InputPreprocessor as Preprocessor
from .context_retriever import ContextRetriever
from .compressor import ContextCompressor
from .reorderer import ContextReorderer
from .response_handler import ResponseHandler
from .summarizer import (
    SummarizerStrategy as BaseSummarizer,
    LLMBasedSummarizer,
)
from .intent_extractor import (
    IntentExtractor,
    LLMIntentExtractor,
    ExtractedIntent,
)
from .template_optimizer import TemplateBasedOptimization

# 向后兼容
InputPreprocessor = Preprocessor

__all__ = [
    "Preprocessor",
    "InputPreprocessor",
    "ContextRetriever",
    "ContextCompressor",
    "ContextReorderer",
    "ResponseHandler",
    "BaseSummarizer",
    "LLMBasedSummarizer",
    "IntentExtractor",
    "LLMIntentExtractor",
    "ExtractedIntent",
    "TemplateBasedOptimization",
]
