"""
Evolution Module - AlphaEvolve/ThetaEvolve 启发的进化式记忆优化

这是 ContextMind 的一个内部模块，实现了借鉴 AlphaEvolve 和 ThetaEvolve 思想的进化式记忆管理。
用于对话任务中记忆库的智能优化。

主要组件:
- updaters: 进化式记忆更新器
- feedback: 观测和反馈收集系统

使用方式:
    from contextmind import EvolutionaryMemoryUpdater, FeedbackCollector
    
    # 或直接从 evolution 子模块导入
    from contextmind.evolution import EvolutionaryMemoryUpdater
"""

__version__ = "0.1.0"

# 从子模块导出主要类
from .updaters import EvolutionaryMemoryUpdater
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
