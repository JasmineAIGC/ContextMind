"""
数据模型（Data Models）

定义DST系统使用的核心数据结构。

版本: v0.4.1
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class SpecialValue(Enum):
    """
    特殊槽位值（符合 ACL 2023 论文定义）
    
    属性:
        UNKNOWN: "?" - 用户正在询问该槽位（未提供值）
        DONTCARE: "dontcare" - 用户不关心该槽位的值
    """
    UNKNOWN = "?"
    DONTCARE = "dontcare"


@dataclass
class DialogueTurn:
    """
    单轮对话数据结构
    
    属性:
        system_utterance: 系统/助手的回复
        user_utterance: 用户的输入
        predicted_state: 本轮之后的累积对话状态
        turn_updates: 仅从本轮提取的槽位更新
        raw_llm_response: 解析前的原始 LLM 响应（可选）
    """
    system_utterance: str
    user_utterance: str
    predicted_state: Dict[str, str] = field(default_factory=dict)
    turn_updates: Dict[str, str] = field(default_factory=dict)
    raw_llm_response: Optional[str] = None
