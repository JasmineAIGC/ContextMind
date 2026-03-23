"""
ContextMind — 通用上下文工程框架

整体框架两步走：
    1. **建立知识库**（:mod:`contextmind.kb`）：针对任意数据集，通过 LLM 自动发现
       槽位和意图，合成标准 SGD 格式 ``schema.json``。
    2. **执行**（:mod:`contextmind.pipeline` 或 :mod:`contextmind.modes.pytod` 等）：
       基于知识库，在对话中提取有效的上下文，提升对话质量。

推荐使用 :class:`~contextmind.pipeline.ContextPipeline` 作为统一入口：
将知识库构建（Phase 1）和对话上下文提取（Phase 2）整合为一个简洁 API。

提供四种对话处理模式：
- DST:     对话状态追踪（槽位提取）
- FnCTOD:  函数调用式对话状态追踪（ADK 原生）
- PyTOD:   可编程任务型对话（AP→EE→DM 三步流程）
- Evolve:  演化式上下文优化（记忆 + 知识提取）

主要组件：
- pipeline:   统一上下文工程流水线（:class:`~contextmind.pipeline.ContextPipeline`）
- kb:         通用知识库构建（任意数据 → schema.json）
- infra:      基础设施（LLM 客户端、日志、嵌入向量）
- modes:      四种对话模式（共享 BaseTracker 协议）
- scenarios:  场景配置与注册表
- ui:         用户界面组件（Gradio）

LLM 配置通过 ``.env`` 文件管理（LLM_API_KEY / LLM_BASE_URL / LLM_MODEL），
由 :class:`~contextmind.infra.llm_client.AdkLLMClient` 统一接入
本地 vLLM / OpenAI 兼容端点。
"""

__version__ = "0.3.0"

from contextmind.pipeline import ContextPipeline
from contextmind.kb import KnowledgeBaseBuilder
from contextmind.scenarios.registry import scenario_registry
from contextmind.modes.base import BaseTracker
from contextmind.modes.dst import DialogueStateTracker
from contextmind.modes.fnctod import FnCTODTracker, adk_tools_from_function_manager
from contextmind.modes.pytod import AdkPyTODTracker, adk_tools_from_engine
from contextmind.modes.pytod.schemas import ServiceSchema, load_schema_from_dict
from contextmind.modes.evolve import create_app_for_scenario, EvolveEngine

from contextmind.infra.llm_client import (
    LLMConfig,
    AdkLLMClient,
    create_local_adk_model,
)

__all__ = [
    # 统一上下文工程流水线（推荐入口）
    "ContextPipeline",
    # 知识库构建（Phase 1）
    "KnowledgeBaseBuilder",
    # Phase 1→2 桥接：schema 数据模型
    "ServiceSchema",
    "load_schema_from_dict",
    # 场景注册表
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
