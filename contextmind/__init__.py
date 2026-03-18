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

Google ADK 集成（本地部署版）
------------------------------
通过 :class:`contextmind.infra.llm_client.AdkLLMClient` 可将任意
Tracker/Engine 切换到 ADK + 本地 vLLM 后端，无需修改调用方代码。
LLM 配置统一通过 ``.env`` 文件管理（QWEN3_BASE_URL / QWEN3_MODEL 等）。

FnCTOD 模式提供 :class:`contextmind.modes.fnctod.AdkFnCTODAgent`，
利用 ADK 原生 Function Calling 替代 XML 提示词解析。

PyTOD 模式提供 :class:`contextmind.modes.pytod.AdkPyTODAgent`，
利用 ADK 原生 Function Calling 替代自定义程序解析器。
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

# LLM 客户端（OpenAI 兼容 + Google ADK 本地部署）
from contextmind.infra.llm_client import (
    SimpleLLMClient,
    LLMConfig,
    AdkLLMClient,
    create_local_adk_model,
)

# ADK 集成组件（按需使用）
from contextmind.modes.pytod.adk_bridge import (
    adk_tools_from_engine,
    AdkLlmClientBridge,
    AdkPyTODAgent,
)
from contextmind.modes.fnctod.adk_bridge import (
    adk_tools_from_function_manager,
    AdkFnCTODAgent,
)

__all__ = [
    "scenario_registry",
    # 共享接口
    "BaseTracker",
    # 追踪器（兼容层，ADK 版本是 AdkFnCTODAgent / AdkPyTODAgent）
    "DialogueStateTracker",
    "FnCTODTracker",
    "PyTODTracker",
    # Evolve 模式
    "EvolveEngine",
    "create_app_for_scenario",
    # LLM 客户端
    "SimpleLLMClient",
    "LLMConfig",
    "AdkLLMClient",
    "create_local_adk_model",
    # ADK 集成（PyTOD）
    "adk_tools_from_engine",
    "AdkLlmClientBridge",
    "AdkPyTODAgent",
    # ADK 集成（FnCTOD）
    "adk_tools_from_function_manager",
    "AdkFnCTODAgent",
]
