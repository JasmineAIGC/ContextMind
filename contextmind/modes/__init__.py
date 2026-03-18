"""
ContextMind 对话处理模式

提供四种对话处理模式（全部基于 ADK）：
- dst:    对话状态追踪
- fnctod: ADK 原生函数调用对话状态追踪
- pytod:  ADK 原生可编程任务型对话
- evolve: 演化式上下文优化
"""

from contextmind.modes.base import BaseTracker
from contextmind.modes.dst import DialogueStateTracker
from contextmind.modes.fnctod import FnCTODAgent
from contextmind.modes.pytod import PyTODAgent
from contextmind.modes.evolve import create_app_for_scenario, EvolveEngine

__all__ = [
    "BaseTracker",
    "DialogueStateTracker",
    "FnCTODAgent",
    "PyTODAgent",
    "EvolveEngine",
    "create_app_for_scenario",
]
