"""
PyTOD — 任务型对话模块

两种实现版本：

``PyTODTracker``（论文原版三步流程，推荐用于研究）
    严格遵循 "Task-Oriented Dialogue as Dataflow Synthesis" 论文：
    Action Parser → Execution Engine → Dialogue Manager。
    每轮有显式程序文本，可解释性强。

``AdkPyTODTracker``（ADK 原生函数调用，推荐用于生产）
    以 ADK 原生 Function Calling 替代显式三步流程，
    LLM 直接决定调用哪个 API 并生成回复，延迟更低。

使用示例::

    # 论文三步流程版本
    from contextmind.modes.pytod import PyTODTracker, ExecutionEngine

    engine = ExecutionEngine()
    SCENARIO_API_REGISTRY["callcenter"](engine)
    llm = AdkLLMClient()
    tracker = PyTODTracker(llm_client=llm, engine=engine)
    result = await tracker.process_turn("查询订单状态")
    print(result["program_text"])  # x1 lookup_order(order_id='ORD-001')
    print(result["response"])      # 您的订单已发货...

    # ADK 原生版本
    from contextmind.modes.pytod import AdkPyTODTracker
    tracker = AdkPyTODTracker.from_scenario(llm, scenario_config)
    result = await tracker.process_turn("查询订单状态")
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
    "PyTODTracker",         # 论文三步流程（AP→EE→DM）
    "AdkPyTODTracker",      # ADK 原生函数调用
    # 提示词构建
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
