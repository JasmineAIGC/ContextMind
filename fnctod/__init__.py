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

与 DST 的区别：
- DST: 传统的槽位-值提取
- FnCTOD: 函数调用范式，更结构化，更易于扩展

版本: v0.2.1
"""

# 数据模型
from fnctod.data_models import FunctionCall, DomainSpec, FunctionParameter

# 核心组件
from fnctod.function_manager import FunctionManager
from fnctod.response_parser import FnCTODResponseParser
from fnctod.fnctod_tracker import FnCTODTracker

# 预定义Schema
from fnctod.schemas import (
    get_chat_function_schema,
    get_callcenter_function_schema,
    get_insurance_function_schema,
    get_function_schema_for_scenario,
    SCHEMA_GETTERS
)

__all__ = [
    'FnCTODTracker',
    'FunctionManager',
    'FnCTODResponseParser',
    'FunctionCall',
    'DomainSpec',
    'FunctionParameter',
    # Schema functions
    'get_chat_function_schema',
    'get_callcenter_function_schema',
    'get_insurance_function_schema',
    'get_function_schema_for_scenario',
    'SCHEMA_GETTERS',
]

__version__ = '0.2.1'
