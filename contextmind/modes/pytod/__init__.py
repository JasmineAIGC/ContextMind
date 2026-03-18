"""
PyTOD — ADK 原生函数调用任务型对话模块

通过 Google ADK 原生 Function Calling 实现任务型对话，
ExecutionEngine 中注册的 API 函数自动成为 ADK 工具。

子模块:
    execution_engine — 执行引擎（安全解析并执行程序语句）
    registry        — 场景 API 注册表（chat / callcenter / insurance）
    schemas         — PyTOD schema 数据模型（可选，开放域无需预定义）
    tracker         — PyTODAgent 主追踪器

使用示例::

    from contextmind.modes.pytod import PyTODAgent, ExecutionEngine
    from contextmind.modes.pytod.registry import SCENARIO_API_REGISTRY

    engine = ExecutionEngine()
    SCENARIO_API_REGISTRY["callcenter"](engine)
    agent = PyTODAgent(engine=engine)
    result = await agent.process_turn("查询订单状态")
    print(result["response"])
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
from .tracker import PyTODAgent, adk_tools_from_engine
from .registry import SCENARIO_API_REGISTRY, get_scenario_key

__all__ = [
    # 主追踪器
    "PyTODAgent",
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
    # Schema 数据模型（可选）
    "SlotDefinition",
    "IntentDefinition",
    "ServiceSchema",
    "load_schema_from_dict",
    # API 注册表
    "SCENARIO_API_REGISTRY",
    "get_scenario_key",
]
