"""
FnCTOD — ADK 原生函数调用对话状态追踪模块

基于 "Large Language Models as Zero-shot Dialogue State Tracker through Function Calling"
论文思想，利用 Google ADK 原生 Function Calling 实现结构化槽位提取。

FnCTOD 不在算法代码内部硬编码场景 Schema 数据。所有 Schema 均通过外部文件传入：
  1. 生成 companion 文件：``python examples/step2b_build_schema_data.py --schema schema/xxx_schema.json``
  2. 加载 DomainSpec：``domain_spec = load_domain_spec_from_file("schema/xxx_fnctod_domain.json")``
  3. 传入追踪器：``FnCTODTracker.from_scenario(..., domain_spec=domain_spec)``

核心组件：
- FnCTODTracker: ADK 原生追踪器（主类）
- FunctionManager: domain 函数管理器
- DomainSpec / FunctionParameter: 数据模型
- schemas.load_domain_spec_from_file: 从外部文件加载 DomainSpec

使用示例::

    from contextmind.modes.fnctod import FnCTODTracker, FunctionManager
    from contextmind.modes.fnctod.schemas import load_domain_spec_from_file

    domain_spec = load_domain_spec_from_file("schema/callcenter_fnctod_domain.json")
    fm = FunctionManager()
    fm.add_domain(domain_spec)
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
from .schemas import load_domain_spec_from_file

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
    "load_domain_spec_from_file",
]

