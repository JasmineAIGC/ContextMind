"""
ContextMind — 通用上下文工程框架

三步框架
--------
1. **建立知识库**（Phase 1，:mod:`contextmind.knowledge`）：针对任意对话数据集，
   通过 LLM 自动发现槽位和意图，合成标准 SGD 格式 ``schema.json``。
   统一使用 ``examples/build_kb.py``，输出：

   - ``schema.json``          — 服务 schema（槽位 + 意图）
   - ``dialogues_001.json``   — SGD 格式标注对话
   - ``discovery_raw.json``   — 逐轮原始提取结果

2. **Schema 数据生成**（Phase 2，:mod:`contextmind.schema_builder`，可选）：
   将 Phase 1 输出的 ``schema.json`` 转换为算法专用的结构化数据。
   目前支持为 PyTOD 自动生成 API 代码文件（``xxx_pytod_apis.py``）。
   DST / FnCTOD / Evolve 不需要此步骤。

3. **算法执行**（Phase 3，:mod:`contextmind.modes`）：基于知识库与生成的
   schema 数据，在对话中提取有效的上下文，提升对话质量。
   支持四种算法，均基于 SGD 数据格式：

   ============  ================  =============================================
   算法           schema.json       适用场景
   ============  ================  =============================================
   ``pytod``     **必须**           任务型对话（AP→EE→DM 三步流程）
   ``fnctod``    **必须**           ADK 原生函数调用对话状态追踪
   ``dst``       可选               通用槽位提取（无需 schema 也可运行）
   ``evolve``    不需要             演化式上下文优化（会话记忆 + 长期记忆）
   ============  ================  =============================================

推荐使用 :class:`~contextmind.pipeline.ContextPipeline` 作为统一入口：
灵活整合三步流程，3 行代码完成端到端上下文工程。

主要组件：
- pipeline:   统一上下文工程流水线（:class:`~contextmind.pipeline.ContextPipeline`）
- knowledge:  通用知识库构建（任意数据 → schema.json，三步框架第一步）
- schema_builder: Schema 数据生成（schema.json → 算法专用数据，三步框架第二步）
- infra:      基础设施（LLM 客户端、日志、嵌入向量）
- modes:      四种对话模式（三步框架第三步，共享 BaseTracker 协议）
- scenarios:  场景配置与注册表
- ui:         用户界面组件（Gradio）

LLM 配置通过 ``.env`` 文件管理（LLM_API_KEY / LLM_BASE_URL / LLM_MODEL），
由 :class:`~contextmind.infra.llm_client.AdkLLMClient` 统一接入
本地 vLLM / OpenAI 兼容端点。
"""

__version__ = "0.3.0"

from contextmind.pipeline import ContextPipeline
from contextmind.knowledge import KnowledgeBaseBuilder
from contextmind.scenarios.registry import scenario_registry
from contextmind.modes.base import BaseTracker
from contextmind.modes.dst import DialogueStateTracker
from contextmind.modes.fnctod import FnCTODTracker, adk_tools_from_function_manager
from contextmind.modes.pytod import AdkPyTODTracker
from contextmind.modes.pytod.schemas import ServiceSchema, load_schema_from_dict
from contextmind.modes.evolve import create_app_for_scenario, EvolveEngine, EvolveApplication

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
    "EvolveApplication",
    "create_app_for_scenario",
    # LLM 客户端
    "LLMConfig",
    "AdkLLMClient",
    "create_local_adk_model",
    # ADK 工具转换
    "adk_tools_from_function_manager",
]
