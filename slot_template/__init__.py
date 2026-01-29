"""
Slot Template Context Optimization Module

槽位模板上下文优化模块 - 基础版本 (Baseline)

这是一个不依赖记忆库的简单上下文优化方案，作为对比实验的基线版本。

核心思路：
1. 通过对话历史提取意图
2. 将意图填充到预定义的槽位模板
3. 使用填充后的模板指导当前轮次的回复

与 ContextMind 的区别：
- ContextMind: 复杂的上下文工程，包含记忆库、检索、压缩等
- SlotTemplate: 简单的槽位填充，不使用记忆库，作为 baseline

主要组件：
- SlotTemplateEngine: 槽位模板引擎
- IntentExtractor: 意图提取器
- TemplateManager: 模板管理器
"""

from .engine import SlotTemplateEngine
from .intent_extractor import IntentExtractor
from .template_manager import TemplateManager, SlotTemplate

__all__ = [
    'SlotTemplateEngine',
    'IntentExtractor', 
    'TemplateManager',
    'SlotTemplate',
]

__version__ = '1.0.0'
