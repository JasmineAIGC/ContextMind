"""
PyTOD — 任务型对话模块

提供两种实现：
    - ``PyTODTracker``      论文三步流程（AP → EE → DM），推荐用于精确控制
    - ``AdkPyTODTracker``   ADK 原生函数调用，推荐用于快速接入

公共组件：
    - ``ExecutionEngine``   程序执行引擎（两种实现共用）
    - ``PyTODPromptBuilder`` 提示词构建器（仅三步流程使用）
    - ``ConversationTurn``  对话历史记录数据类（仅三步流程使用）

使用示例::

    # 论文三步流程
    from contextmind.modes.pytod import PyTODTracker, PyTODPromptBuilder, ExecutionEngine
    from contextmind.modes.pytod.schemas import ServiceSchema, load_schema_from_dict

    engine = ExecutionEngine()
    builder = PyTODPromptBuilder(schema=my_schema)
    tracker = PyTODTracker(llm_client=llm, execution_engine=engine, prompt_builder=builder)
    result = await tracker.process_turn("查询账户")

    # ADK 原生
    from contextmind.modes.pytod import AdkPyTODTracker, ExecutionEngine
    from contextmind.modes.pytod.registry import SCENARIO_API_REGISTRY

    engine = ExecutionEngine()
    SCENARIO_API_REGISTRY["callcenter"](engine)
    agent = AdkPyTODTracker(engine=engine)
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
from .prompts import ConversationTurn, PyTODPromptBuilder
from .tracker import PyTODTracker, AdkPyTODTracker, adk_tools_from_engine
from .registry import SCENARIO_API_REGISTRY, get_scenario_key

__all__ = [
    # 主追踪器
    "PyTODTracker",         # 论文三步流程（AP → EE → DM）
    "AdkPyTODTracker",      # ADK 原生函数调用
    # 提示词构建（三步流程专用）
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
    # Schema 数据模型（可选）
    "SlotDefinition",
    "IntentDefinition",
    "ServiceSchema",
    "load_schema_from_dict",
    # API 注册表
    "SCENARIO_API_REGISTRY",
    "get_scenario_key",
]

