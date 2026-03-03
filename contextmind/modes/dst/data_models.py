"""
数据模型（Data Models）

定义DST系统使用的核心数据结构。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class SpecialValue(Enum):
    """特殊槽位值，遵循 MultiWOZ / DSTC 惯例。

    UNKNOWN ("?") — user is *asking* for this slot rather than providing a value.
    DONTCARE ("dontcare") — user explicitly doesn't care about this slot's value.
    """
    UNKNOWN = "?"
    DONTCARE = "dontcare"


@dataclass
class DialogueTurn:
    """单轮对话数据结构，包含系统/用户发言和槽位状态信息。"""
    system_utterance: str
    user_utterance: str
    predicted_state: Dict[str, str] = field(default_factory=dict)
    turn_updates: Dict[str, str] = field(default_factory=dict)
    # Preserved for debugging and offline analysis; not used in state tracking.
    raw_llm_response: Optional[str] = None
