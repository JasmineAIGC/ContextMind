"""
ContextMind - 多模式对话AI框架

ContextMind 提供三种先进的对话处理模式：
- DST（对话状态追踪）：状态提取和槽位填充
- FnCTOD（任务型对话的函数调用）：基于函数的对话处理
- Evolve（演化式上下文优化）：具有记忆演化的高级上下文管理

主要组件：
- infra：基础设施（日志、LLM客户端、工具）
- config：配置管理（场景注册、配置文件）
- ui：用户界面组件
- modes：三种对话处理模式
- scenarios：场景配置定义
- apps：应用实现
"""

__version__ = "0.2.1"
__author__ = "ContextMind Team"

# 重新导出主要组件，方便访问
from contextmind.config.registry import scenario_registry
from contextmind.modes.dst import DialogueStateTracker
from contextmind.modes.fnctod import FnCTODTracker
from contextmind.modes.evolve import create_app_for_scenario, EvolveEngine

__all__ = [
    "scenario_registry",
    "DialogueStateTracker",
    "FnCTODTracker",
    "EvolveEngine",
    "create_app_for_scenario",
]
