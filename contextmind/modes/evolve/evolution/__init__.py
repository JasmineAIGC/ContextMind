"""
Evolution Module - 进化式记忆优化

借鉴 AlphaEvolve/ThetaEvolve 思想的进化式记忆管理模块。
通过观测-反馈-学习循环，持续优化对话记忆质量。

核心组件:
- EvolutionaryMemoryUpdater: 进化式记忆更新器
- FeedbackCollector: 反馈收集系统
- ObservationCollector: 观测收集系统

使用方式:
    from evolve.evolution import EvolutionaryMemoryUpdater
    from evolve.evolution import FeedbackCollector
"""

__version__ = "0.2.1"

# 从模块文件导入主要类
from .updater import EvolutionaryMemoryUpdater
from .feedback import (
    ObservationCollector,
    FeedbackCollector,
    ImplicitFeedbackAnalyzer,
    FeedbackEvent,
    ObservationEvent,
    FeedbackSource,
    FeedbackType,
    ConversationTurn,
    ConversationSession,
)

__all__ = [
    # 更新器
    'EvolutionaryMemoryUpdater',
    
    # 反馈收集
    'ObservationCollector',
    'FeedbackCollector',
    'ImplicitFeedbackAnalyzer',
    
    # 数据类型
    'FeedbackEvent',
    'ObservationEvent',
    'FeedbackSource',
    'FeedbackType',
    'ConversationTurn',
    'ConversationSession',
]
