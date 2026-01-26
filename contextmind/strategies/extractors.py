"""
Memory Extractors - 知识提取的 Plugin 实现

本模块提供多种策略, 用于从对话中提取有价值的信息并存储到长期记忆

此文件保持向后兼容性，所有类现在从 extractors 子模块导入
"""

# Re-export all extractors for backward compatibility
from .extractors import (
    BaseExtractor,
    RuleBasedExtractor,
    LLMBasedExtractor,
    ImportancePredictorExtractor,
)

__all__ = [
    "BaseExtractor",
    "RuleBasedExtractor",
    "LLMBasedExtractor",
    "ImportancePredictorExtractor",
]
