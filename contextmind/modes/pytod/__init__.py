"""
PyTOD — 任务型对话模块（AP → EE → DM 三步流程）

``AdkPyTODTracker`` 是唯一实现，严格遵循论文
"Task-Oriented Dialogue as Dataflow Synthesis"：

    Step 1  AP（动作解析器）：AdkLLMClient 根据对话历史和 Schema 生成 PyTOD 程序
    Step 2  EE（执行引擎）：ExecutionEngine 安全解析并执行程序
    Step 3  DM（对话管理器）：AdkLLMClient 根据执行结果生成自然语言回复

使用示例::

    from contextmind.modes.pytod import AdkPyTODTracker, ExecutionEngine
    from contextmind.modes.pytod.registry import SCENARIO_API_REGISTRY
    from contextmind.infra.llm_client import AdkLLMClient

    llm = AdkLLMClient()
    engine = ExecutionEngine()
    SCENARIO_API_REGISTRY["callcenter"](engine)
    tracker = AdkPyTODTracker(llm_client=llm, engine=engine)
    result = await tracker.process_turn("查询订单状态")
    print(result["program_text"])  # x1 lookup_order(order_id='ORD-001')
    print(result["response"])      # 您的订单已发货...

    # 或使用工厂方法
    tracker = AdkPyTODTracker.from_scenario(llm, scenario_config)
"""

from .schemas import SlotDefinition, IntentDefinition, ServiceSchema, load_schema_from_dict
from .execution_engine import (
    ExecutionEngine,
    ProgramStatement,
    ExecutionResult,
    SlotAssignment,
    HintStatement,
    SayStatement,
    ConfirmStatement,
    PerformStatement,
    ProgramBlock,
    ProgramExecutionResult,
)
from .prompts import ConversationTurn, PyTODPromptBuilder
from .tracker import AdkPyTODTracker, adk_tools_from_engine
from .registry import SCENARIO_API_REGISTRY, get_scenario_key

__all__ = [
    # 主追踪器（唯一实现：AP→EE→DM 三步流程）
    "AdkPyTODTracker",
    # 提示词构建
    "PyTODPromptBuilder",
    "ConversationTurn",
    # 工具转换（已废弃，保留向后兼容）
    "adk_tools_from_engine",
    # 执行引擎
    "ExecutionEngine",
    "ProgramStatement",
    "ExecutionResult",
    "SlotAssignment",
    "HintStatement",
    "SayStatement",
    "ConfirmStatement",
    "PerformStatement",
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
