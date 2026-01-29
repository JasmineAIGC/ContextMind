"""
记忆子模块 - MemoryBank 架构

从管道架构实现 MemoryBank 组件，包含 4 个子模块：
- Extractor: 提取高价值信息
- Retriever: 检索相关记忆
- Updater: 智能更新 (添加/删除/更新)
- Bank: 主 MemoryBank 类

同时包含用于会话管理的 SessionManager。
"""

from .bank import MemoryBank, STOPWORDS
from .session import SessionManager
from .extractor import (
    BaseExtractor,
    RuleBasedExtractor,
    LLMBasedExtractor,
    ImportancePredictorExtractor,
)
from .retriever import (
    BaseRetriever,
    SemanticSearchRetriever,
)
from .updater import (
    BaseUpdater,
    SimpleUpdater,
)
from .memory_fitness import (
    MemoryFitness,
    FitnessCalculator,
    DialogueObservationType,
    FeedbackType,
    DialogueObservation,
)

__all__ = [
    # 主 MemoryBank
    "MemoryBank",
    "STOPWORDS",
    "SessionManager",
    
    # 提取器 (步骤 1: 提取高价值信息)
    "BaseExtractor",
    "RuleBasedExtractor",
    "LLMBasedExtractor",
    "ImportancePredictorExtractor",
    
    # 检索器 (步骤 2: 检索相关记忆)
    "BaseRetriever",
    "SemanticSearchRetriever",
    
    # 更新器 (步骤 3: 更新记忆库)
    "BaseUpdater",
    "SimpleUpdater",
    
    # 适应度评估 (观测和反馈核心能力)
    "MemoryFitness",
    "FitnessCalculator",
    "DialogueObservationType",
    "FeedbackType",
    "DialogueObservation",
]

# 注意：EvolutionaryMemoryUpdater 已移至 evolution 模块
# 使用方法: from evolution.updaters import EvolutionaryMemoryUpdater
