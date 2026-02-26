"""
ContextMind 对话处理模式

提供四种可用模式:
- dst: 对话状态追踪模式
- fnctod: 任务型对话的函数调用模式
- evolve: 演化式上下文优化模式
- pytod: PyTOD schema 适配模式（zero/few-shot LLM prompt 工程）
"""

# 导入模式入口
from contextmind.modes.dst import DialogueStateTracker
from contextmind.modes.fnctod import FnCTODTracker
from contextmind.modes.evolve import create_app_for_scenario, EvolveEngine
from contextmind.modes.pytod import PyTODPromptBuilder, ActionValidator, ServiceSchema, load_schema_from_dict

__all__ = [
    "DialogueStateTracker",
    "FnCTODTracker",
    "EvolveEngine",
    "create_app_for_scenario",
    "PyTODPromptBuilder",
    "ActionValidator",
    "ServiceSchema",
    "load_schema_from_dict",
]
