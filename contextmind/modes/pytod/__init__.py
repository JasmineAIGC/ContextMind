"""
PyTOD — 任务型对话模块（ADK 原生版本）

唯一实现：``AdkPyTODTracker`` — 基于 Google ADK 原生 Function Calling，
LLM 直接决定调用哪个 API 并生成自然语言回复，通过 adk-python 统一管理 LLM 调用。

使用示例::

    from contextmind.modes.pytod import AdkPyTODTracker, ExecutionEngine
    from contextmind.modes.pytod.registry import SCENARIO_API_REGISTRY

    engine = ExecutionEngine()
    SCENARIO_API_REGISTRY["callcenter"](engine)
    agent = AdkPyTODTracker(engine=engine)
    result = await agent.process_turn("查询订单状态")
    print(result["response"])

    # 或使用工厂方法
    tracker = AdkPyTODTracker.from_scenario(llm_client, scenario_config)
"""

from .schemas import SlotDefinition, IntentDefinition, ServiceSchema, load_schema_from_dict
from .execution_engine import (
    ExecutionEngine,
    ProgramStatement,
    ExecutionResult,
    SlotAssignment,
    HintStatement,
    SayStatement,
    ProgramBlock,
    ProgramExecutionResult,
)
from .prompts import ConversationTurn, PyTODPromptBuilder
from .tracker import AdkPyTODTracker, adk_tools_from_engine
from .registry import SCENARIO_API_REGISTRY, get_scenario_key

__all__ = [
    # 主追踪器
    "AdkPyTODTracker",      # ADK 原生函数调用（唯一版本）
    # 提示词构建（保留供外部使用）
    "PyTODPromptBuilder",
    "ConversationTurn",
    # 工具转换
    "adk_tools_from_engine",
    # 执行引擎
    "ExecutionEngine",
    "ProgramStatement",
    "ExecutionResult",
    "SlotAssignment",
    "HintStatement",
    "SayStatement",
    "ProgramBlock",
    "ProgramExecutionResult",
    # Schema 数据模型
    "SlotDefinition",
    "IntentDefinition",
    "ServiceSchema",
    "load_schema_from_dict",
    # API 注册表
    "SCENARIO_API_REGISTRY",
    "get_scenario_key",
]
