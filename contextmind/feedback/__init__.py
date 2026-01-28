"""
反馈收集模块

提供完整的观测和反馈收集功能，用于对话系统中的记忆优化。
包含显式反馈、隐式反馈和自动反馈的收集和处理。
"""

from .collector import (
    FeedbackCollector,
    ObservationCollector,
    ImplicitFeedbackAnalyzer
)
from .types import (
    FeedbackEvent,
    ObservationEvent,
    FeedbackSource,
    FeedbackType,
    ConversationTurn,
    ConversationSession
)

__all__ = [
    # 收集器
    'FeedbackCollector',
    'ObservationCollector',
    'ImplicitFeedbackAnalyzer',
    
    # 类型
    'FeedbackEvent',
    'ObservationEvent',
    'FeedbackSource',
    'FeedbackType',
    'ConversationTurn',
    'ConversationSession',
]
