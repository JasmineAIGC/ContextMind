"""
Conversation Summarizer (backward compatibility)

此文件保持向后兼容性，所有类现在从 summarizer 模块导入
"""

# Re-export all summarizers for backward compatibility
from ..summarizer import (
    SummarizationConfig,
    SummarizerStrategy,
    LLMBasedSummarizer,
    RuleBasedSummarizer,
    ConversationSummarizer,
)

__all__ = [
    "SummarizationConfig",
    "SummarizerStrategy",
    "LLMBasedSummarizer",
    "RuleBasedSummarizer",
    "ConversationSummarizer",
]
