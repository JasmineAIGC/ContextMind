"""
ContextMind - 多模式对话AI框架

ContextMind 提供四种先进的对话处理模式：
- DST（对话状态追踪）：状态提取和槽位填充
- FnCTOD（任务型对话的函数调用）：基于函数的对话处理
- Evolve（演化式上下文优化）：具有记忆演化的高级上下文管理
- PyTOD（可编程任务型对话）：程序执行 + 真实 API 调用

主要组件：
- infra：基础设施（日志、LLM客户端、嵌入向量、基础数据模型）
- modes：四种对话处理模式（共享 BaseTracker 协议）
- scenarios：场景配置、系统提示词、注册表及 Evolve 应用实现
- ui：用户界面组件（Gradio）
"""

__version__ = "0.2.1"
__author__ = "ContextMind Team"

# 重新导出主要组件，方便访问
from contextmind.scenarios.registry import scenario_registry
from contextmind.modes.base import BaseTracker
from contextmind.modes.dst import DialogueStateTracker
from contextmind.modes.fnctod import FnCTODTracker
from contextmind.modes.pytod import PyTODTracker
from contextmind.modes.evolve import create_app_for_scenario, EvolveEngine

__all__ = [
    "scenario_registry",
    # 共享接口
    "BaseTracker",
    # 追踪器
    "DialogueStateTracker",
    "FnCTODTracker",
    "PyTODTracker",
    # Evolve 模式
    "EvolveEngine",
    "create_app_for_scenario",
]
