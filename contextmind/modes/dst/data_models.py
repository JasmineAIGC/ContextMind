"""
数据模型（Data Models）

定义DST系统使用的核心数据结构。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class SpecialValue(Enum):
    """特殊槽位值，UNKNOWN="?" 表示用户询问，DONTCARE="dontcare" 表示不关心。"""
    UNKNOWN = "?"
    DONTCARE = "dontcare"


@dataclass
class DialogueTurn:
    """单轮对话数据结构，包含系统/用户发言和槽位状态信息。"""
    system_utterance: str
    user_utterance: str
    predicted_state: Dict[str, str] = field(default_factory=dict)
    turn_updates: Dict[str, str] = field(default_factory=dict)
    raw_llm_response: Optional[str] = None
