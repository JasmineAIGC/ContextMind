"""
ContextMind — 基于 Google ADK 的多模式对话 AI 框架

提供四种对话处理模式，全部基于 ADK 原生 Function Calling：
- DST:     对话状态追踪（槽位提取）
- FnCTOD:  函数调用式对话状态追踪（ADK 原生）
- PyTOD:   可编程任务型对话（ADK + ExecutionEngine）
- Evolve:  演化式上下文优化（记忆 + 知识提取）

主要组件：
- infra:      基础设施（LLM 客户端、日志、嵌入向量）
- modes:      四种对话模式（共享 BaseTracker 协议）
- scenarios:  场景配置与注册表
- ui:         用户界面组件（Gradio）

LLM 配置通过 ``.env`` 文件管理（QWEN3_BASE_URL / QWEN3_MODEL 等），
由 :func:`contextmind.infra.llm_client.create_local_adk_model` 统一接入
本地 vLLM / OpenAI 兼容端点。
"""

__version__ = "0.3.0"

from contextmind.scenarios.registry import scenario_registry
from contextmind.modes.base import BaseTracker
from contextmind.modes.dst import DialogueStateTracker
from contextmind.modes.fnctod import FnCTODTracker, adk_tools_from_function_manager
from contextmind.modes.pytod import AdkPyTODTracker, adk_tools_from_engine
from contextmind.modes.evolve import create_app_for_scenario, EvolveEngine

from contextmind.infra.llm_client import (
    LLMConfig,
    AdkLLMClient,
    create_local_adk_model,
)

__all__ = [
    "scenario_registry",
    # 共享接口
    "BaseTracker",
    # 追踪器
    "DialogueStateTracker",
    "FnCTODTracker",
    "AdkPyTODTracker",
    # Evolve 模式
    "EvolveEngine",
    "create_app_for_scenario",
    # LLM 客户端
    "LLMConfig",
    "AdkLLMClient",
    "create_local_adk_model",
    # ADK 工具转换
    "adk_tools_from_function_manager",
    "adk_tools_from_engine",
]
