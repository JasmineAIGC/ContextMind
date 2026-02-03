"""
记忆子模块 - MemoryBank 架构

从管道架构实现 MemoryBank 组件，包含 4 个子模块：
- Extractor: 提取高价值信息
- Retriever: 检索相关记忆
- Updater: 智能更新 (添加/删除/更新)
- Bank: 主 MemoryBank 类

同时包含用于会话管理的 SessionManager。

v0.4.1: 使用 ADK Session 和 Memory
"""

# 使用 ADK 版本（推荐）
from .adk_session import ADKSessionManager
from .adk_memory import ADKMemoryBank  # 临时占位符实现，需要重构

# 向后兼容别名
SessionManager = ADKSessionManager
MemoryBank = ADKMemoryBank  # 临时占位符实现，需要重构

# STOPWORDS for backward compatibility
STOPWORDS = set()
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
    # 主组件
    "SessionManager",
    "MemoryBank",  # 临时占位符实现，需要重构
    "STOPWORDS",
    
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
