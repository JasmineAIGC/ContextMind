"""
FnCTOD Module - Function Calling for Task-Oriented Dialogue

基于论文 "Large Language Models as Zero-shot Dialogue State Tracker through Function Calling"
将 DST 升级为基于函数调用的方法。

核心特性：
1. 将每个domain视为一个function
2. DST转化为"调用函数填槽位参数"
3. 支持两阶段分解：domain选择 → parameter填充
4. 输出格式：<function_call> + 自然语言回复
5. 支持 zero-shot 和 fine-tuning
6. 工厂方法 - from_scenario() 简化创建流程

与 DST 的区别：
- DST: 传统的槽位-值提取
- FnCTOD: 函数调用范式，更结构化，更易于扩展

使用示例：
    # 方式1: 使用工厂方法（推荐）
    from contextmind.modes.fnctod import FnCTODTracker
    tracker = FnCTODTracker.from_scenario(llm_client, scenario_config)
    
    # 方式2: 手动创建
    from contextmind.modes.fnctod import FnCTODTracker, FunctionManager, get_function_schema_for_scenario
    function_manager = FunctionManager()
    schema = get_function_schema_for_scenario("chat")
    function_manager.add_domain(schema)
    tracker = FnCTODTracker(llm_client=llm_client, function_manager=function_manager)

版本: v0.2.1
"""

# 数据模型
from .function_manager import FunctionCall, DomainSpec, FunctionParameter, ParameterType

# 核心组件
from .function_manager import FunctionManager
from .parser import FnCTODResponseParser
from .tracker import FnCTODTracker

# 预定义Schema
from .schemas import (
    get_chat_function_schema,
    get_callcenter_function_schema,
    get_insurance_function_schema,
    get_function_schema_for_scenario,
)

__all__ = [
    'FnCTODTracker',
    'FunctionManager',
    'FnCTODResponseParser',
    'FunctionCall',
    'DomainSpec',
    'FunctionParameter',
    'ParameterType',  # 导出 ParameterType
    # Schema 转换函数
    'get_chat_function_schema',
    'get_callcenter_function_schema',
    'get_insurance_function_schema',
    'get_function_schema_for_scenario',
]

__version__ = '0.2.1'
