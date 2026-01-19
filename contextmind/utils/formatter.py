"""
Formatter - Context formatting and summarization utilities

Merged from context_formatter.py and summarizer.py.
Provides formatting, visualization, and summarization tools.
"""

from typing import List, Optional, TYPE_CHECKING, Tuple
from dataclasses import dataclass
from ..core import get_logger, DEFAULT_MEMORY_CONFIG, SummarizationConfig, Message

if TYPE_CHECKING:
    from ..core import ContextResult, ContextItem

logger = get_logger(__name__)

# ============================================================================
# Summarization
# ============================================================================

@dataclass
class SummarizedHistory:
    """摘要后的对话历史"""
    summary: str
    recent_messages: List[Message]
    metadata: dict

class ConversationSummarizer:
    """对话摘要器"""
    def __init__(self, config: Optional[SummarizationConfig] = None, llm_client: Optional[any] = None):
        self.config = config or DEFAULT_MEMORY_CONFIG.summarization
        self.llm_client = llm_client
    
    def summarize(self, messages: List[Message]) -> SummarizedHistory:
        """摘要对话历史"""
        if len(messages) <= self.config.recent_turns:
            return SummarizedHistory(summary="", recent_messages=messages, metadata={"total_turns": len(messages)})
        
        split_point = len(messages) - self.config.recent_turns
        early_messages = messages[:split_point]
        recent_messages = messages[split_point:]
        
        summary = self._generate_summary(early_messages)
        
        return SummarizedHistory(
            summary=summary,
            recent_messages=recent_messages,
            metadata={"total_turns": len(messages), "summarized_turns": len(early_messages)}
        )
    
    def _generate_summary(self, messages: List[Message]) -> str:
        """生成摘要"""
        if not messages:
            return ""
        
        turn_summaries = []
        for msg in messages:
            role = msg.role.value if hasattr(msg.role, 'value') else str(msg.role)
            content_preview = msg.content[:50] + "..." if len(msg.content) > 50 else msg.content
            turn_summaries.append(f"{role}: {content_preview}")
        
        return f"[早期对话摘要 {len(messages)}轮] " + " | ".join(turn_summaries[:3])

# ============================================================================
# Formatting
# ============================================================================

BOX_WIDTH = 100
BORDER_CHAR = "="
MIN_BOX_WIDTH = 40

class ContextFormatter:
    """上下文格式化器"""
    def __init__(self, box_width: int = BOX_WIDTH):
        self.box_width = max(box_width, MIN_BOX_WIDTH)
    
    def format_context_result(self, context_result: "ContextResult") -> str:
        """格式化上下文结果"""
        lines = ["\n=== Context Optimization Result ==="]
        lines.append(f"History: {len(context_result.recent_history)} messages")
        lines.append(f"Memory: {len(context_result.long_term_memory)} items")
        lines.append(f"Knowledge: {len(context_result.external_knowledge)} items")
        return "\n".join(lines)

_formatter = ContextFormatter()

def format_context_result(context_result: "ContextResult") -> str:
    return _formatter.format_context_result(context_result)

def format_memory_cache(memory_cache: List["ContextItem"]) -> str:
    return f"\n=== Memory Cache ===\nItems: {len(memory_cache)}"

def format_prompt_analysis(prompt: str, context_result: "ContextResult") -> str:
    return f"\n=== Prompt Analysis ===\nLength: {len(prompt)} chars"

def format_complete_prompt(prompt: str) -> str:
    return f"\n=== Complete Prompt ===\n{prompt}"
