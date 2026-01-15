"""
ContextMind Strategies - 策略模块

提供可插拔的策略实现，用于自定义上下文处理的各个环节。
"""

from .base import (
    RetrievalStrategy,
    IntegrationStrategy,
    OptimizationStrategy,
    ExtractionStrategy,
)
from .retrieval import (
    KeywordRetrievalStrategy,
    VectorRetrievalStrategy,
    HybridRetrievalStrategy,
)
from .integration import (
    SimpleIntegrationStrategy,
    PriorityIntegrationStrategy,
)
from .optimization import (
    CompressionStrategy,
    RerankingStrategy,
)
from .extraction import (
    RuleBasedExtractionStrategy,
    LLMExtractionStrategy,
)

__all__ = [
    # 基类
    "RetrievalStrategy",
    "IntegrationStrategy",
    "OptimizationStrategy",
    "ExtractionStrategy",
    
    # 检索策略
    "KeywordRetrievalStrategy",
    "VectorRetrievalStrategy",
    "HybridRetrievalStrategy",
    
    # 整合策略
    "SimpleIntegrationStrategy",
    "PriorityIntegrationStrategy",
    
    # 优化策略
    "CompressionStrategy",
    "RerankingStrategy",
    
    # 提取策略
    "RuleBasedExtractionStrategy",
    "LLMExtractionStrategy",
]
