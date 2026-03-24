"""
FnCTOD — ADK 原生函数调用对话状态追踪模块

基于 "Large Language Models as Zero-shot Dialogue State Tracker through Function Calling"
论文思想，利用 Google ADK 原生 Function Calling 实现结构化槽位提取。

核心组件：
- FnCTODTracker: ADK 原生追踪器（主类）
- FunctionManager: domain 函数管理器
- DomainSpec / FunctionParameter: 数据模型
- schemas.yaml: 预定义场景 schema（chat / callcenter / insurance）

使用示例::

    from contextmind.modes.fnctod import FnCTODTracker, FunctionManager
    from contextmind.modes.fnctod.schemas import get_function_schema_for_scenario

    fm = FunctionManager()
    fm.add_domain(get_function_schema_for_scenario("callcenter"))
    tracker = FnCTODTracker(function_manager=fm)
    updates = await tracker.process_turn("我的订单什么时候到？")
    print(tracker.get_current_state())
"""

from .function_manager import (
    FunctionCall,
    DomainSpec,
    FunctionParameter,
    ParameterType,
    FunctionManager,
)
from .tracker import FnCTODTracker, adk_tools_from_function_manager
from .schemas import (
    get_chat_function_schema,
    get_callcenter_function_schema,
    get_insurance_function_schema,
    get_function_schema_for_scenario,
)

__all__ = [
    # 主追踪器
    "FnCTODTracker",
    # 工具转换
    "adk_tools_from_function_manager",
    # 数据模型 & 管理器
    "FunctionManager",
    "DomainSpec",
    "FunctionParameter",
    "FunctionCall",
    "ParameterType",
    # Schema 加载函数
    "get_chat_function_schema",
    "get_callcenter_function_schema",
    "get_insurance_function_schema",
    "get_function_schema_for_scenario",
]

