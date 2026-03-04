"""
ContextMind 对话处理模式

提供四种可用模式:
- dst: 对话状态追踪模式
- fnctod: 任务型对话的函数调用模式
- evolve: 演化式上下文优化模式
- pytod: PyTOD schema 适配模式（zero/few-shot LLM prompt 工程）

新增模式时，请实现 ``BaseTracker`` 协议并在 ``scenarios.yaml`` 中注册场景。
"""

# 共享接口协议（所有追踪器均满足此协议）
from contextmind.modes.base import BaseTracker

# 导入模式入口
from contextmind.modes.dst import DialogueStateTracker
from contextmind.modes.fnctod import FnCTODTracker
from contextmind.modes.evolve import create_app_for_scenario, EvolveEngine
from contextmind.modes.pytod import PyTODTracker, PyTODPromptBuilder, ActionValidator, ServiceSchema, load_schema_from_dict

__all__ = [
    # 共享接口
    "BaseTracker",
    # 追踪器
    "DialogueStateTracker",
    "FnCTODTracker",
    "PyTODTracker",
    # Evolve 模式
    "EvolveEngine",
    "create_app_for_scenario",
    # PyTOD 工具
    "PyTODPromptBuilder",
    "ActionValidator",
    "ServiceSchema",
    "load_schema_from_dict",
]
