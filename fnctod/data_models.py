"""
FnCTOD 数据模型

定义 FnCTOD 所需的核心数据结构
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum


class ParameterType(Enum):
    """参数类型枚举"""
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


@dataclass
class FunctionParameter:
    """函数参数定义"""
    name: str
    description: str
    param_type: ParameterType = ParameterType.STRING
    required: bool = False
    enum_values: Optional[List[str]] = None  # 分类槽位的可选值
    default: Optional[Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于生成JSON schema）"""
        param_def = {
            "type": self.param_type.value,
            "description": self.description
        }
        if self.enum_values:
            param_def["enum"] = self.enum_values
        if self.default is not None:
            param_def["default"] = self.default
        return param_def


@dataclass
class DomainSpec:
    """
    Domain 规格定义（作为Function）
    
    每个domain被视为一个function，包含：
    - name: domain名称（也是函数名）
    - description: domain描述
    - parameters: 参数列表（即槽位）
    """
    name: str
    description: str
    parameters: List[FunctionParameter] = field(default_factory=list)
    
    def add_parameter(self, param: FunctionParameter):
        """添加参数"""
        self.parameters.append(param)
    
    def get_required_parameters(self) -> List[str]:
        """获取必需参数列表"""
        return [p.name for p in self.parameters if p.required]
    
    def to_json_schema(self) -> Dict[str, Any]:
        """
        转换为JSON Schema格式（符合OpenAI function calling规范）
        
        Returns:
            符合OpenAI function calling的JSON schema
        """
        properties = {}
        required = []
        
        for param in self.parameters:
            properties[param.name] = param.to_dict()
            if param.required:
                required.append(param.name)
        
        schema = {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties
            }
        }
        
        if required:
            schema["parameters"]["required"] = required
        
        return schema
    
    def to_prompt_format(self) -> str:
        """
        转换为提示词格式
        
        Returns:
            格式化的函数说明文本
        """
        lines = [
            f"Function: {self.name}",
            f"Description: {self.description}",
            "Parameters:"
        ]
        
        for param in self.parameters:
            required_mark = " (required)" if param.required else ""
            enum_info = f" [options: {', '.join(param.enum_values)}]" if param.enum_values else ""
            lines.append(f"  - {param.name} ({param.param_type.value}){required_mark}: {param.description}{enum_info}")
        
        return "\n".join(lines)


@dataclass
class FunctionCall:
    """
    函数调用结果
    
    表示一次function call的结果，包括：
    - function_name: 调用的函数名（domain）
    - arguments: 参数字典（槽位-值）
    - raw_output: 原始LLM输出
    - natural_response: 自然语言回复
    """
    function_name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    raw_output: str = ""
    natural_response: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "function": self.function_name,
            "arguments": self.arguments,
            "response": self.natural_response
        }
    
    def to_xml(self) -> str:
        """
        转换为XML格式的function call（用于提示词中的历史记录）
        
        Returns:
            XML格式的function call字符串
        """
        import json
        args_json = json.dumps(self.arguments, ensure_ascii=False, indent=0)
        return f"<function_call name=\"{self.function_name}\">\n{args_json}\n</function_call>"
    
    def __str__(self) -> str:
        """字符串表示"""
        return self.to_xml()


@dataclass
class DialogueTurn:
    """
    对话轮次
    
    记录一轮对话的信息
    """
    turn_id: int
    user_utterance: str
    system_utterance: str = ""
    function_call: Optional[FunctionCall] = None
    state: Dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            "turn_id": self.turn_id,
            "user": self.user_utterance,
            "system": self.system_utterance,
            "state": self.state
        }
        if self.function_call:
            result["function_call"] = self.function_call.to_dict()
        if self.timestamp:
            result["timestamp"] = self.timestamp
        return result
