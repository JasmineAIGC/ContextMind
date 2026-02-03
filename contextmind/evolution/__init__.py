"""
Evolution Module - 进化式记忆优化

借鉴 AlphaEvolve/ThetaEvolve 思想的进化式记忆管理模块。
通过观测-反馈-学习循环，持续优化对话记忆质量。

支持与 google-adk (Agent Development Kit) 的集成，
可使用 ADK 的 Agent 回调机制进行自动反馈收集。

核心组件:
- EvolutionaryMemoryUpdater: 进化式记忆更新器
- FeedbackCollector: 反馈收集系统
- ObservationCollector: 观测收集系统

使用方式:
    from contextmind.evolution import EvolutionaryMemoryUpdater
    from contextmind.evolution import FeedbackCollector
    
ADK 集成示例:
    from utils import create_agent, ADKAgentBuilder
    from contextmind.evolution import FeedbackCollector
    
    collector = FeedbackCollector()
    
    # 创建带反馈收集的 Agent
    agent = (
        ADKAgentBuilder("assistant")
        .with_instruction("你是一个友好的助手")
        .build()
    )

版本: v0.4.0
"""

__version__ = "0.4.0"

# 从模块文件导入主要类
from .evolutionary_updater import EvolutionaryMemoryUpdater
from .feedback_system import (
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
