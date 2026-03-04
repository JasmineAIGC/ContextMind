"""
FnCTOD Function Manager

管理 domain-as-function 规格
"""

import json
from typing import Dict, List, Optional
from .data_models import DomainSpec, FunctionParameter, ParameterType
from contextmind.infra.logger import get_logger

logger = get_logger(__name__)


class FunctionManager:
    """
    函数管理器
    
    管理所有domain的function规格，支持：
    1. 添加/删除domain函数
    2. 生成function calling提示词
    3. 生成JSON schema
    """
    
    def __init__(self):
        self.domains: Dict[str, DomainSpec] = {}
        logger.info("FunctionManager 初始化完成")
    
    def add_domain(self, domain: DomainSpec):
        """
        添加domain函数
        
        Args:
            domain: DomainSpec对象
        """
        self.domains[domain.name] = domain
        logger.debug(f"添加domain函数: {domain.name} ({len(domain.parameters)} 个参数)")
    
    def add_domain_from_slots(
        self, 
        domain_name: str, 
        domain_description: str,
        slots: Dict[str, str],
        categorical_slots: Optional[Dict[str, List[str]]] = None,
        required_slots: Optional[List[str]] = None
    ):
        """
        从槽位定义创建domain函数
        
        Args:
            domain_name: domain名称
            domain_description: domain描述
            slots: 槽位字典 {slot_name: slot_description}
            categorical_slots: 分类槽位 {slot_name: [values]}
            required_slots: 必需槽位列表
        """
        domain = DomainSpec(name=domain_name, description=domain_description)
        
        required_set = set(required_slots or [])
        categorical_slots = categorical_slots or {}
        
        for slot_name, slot_desc in slots.items():
            param = FunctionParameter(
                name=slot_name,
                description=slot_desc,
                param_type=ParameterType.STRING,
                required=slot_name in required_set,
                enum_values=categorical_slots.get(slot_name)
            )
            domain.add_parameter(param)
        
        self.add_domain(domain)
        logger.info(f"从槽位创建domain函数: {domain_name} ({len(slots)} 个槽位)")
    
    def get_domain(self, name: str) -> Optional[DomainSpec]:
        """按名称查找已注册的 domain，不存在时返回 None。"""
        return self.domains.get(name)

    def get_all_domains(self) -> List[DomainSpec]:
        """返回所有已注册 domain 的列表（顺序与注册顺序一致）。"""
        return list(self.domains.values())

    def get_domain_names(self) -> List[str]:
        """返回所有已注册 domain 的名称列表。"""
        return list(self.domains.keys())
    
    def generate_system_prompt(self, include_all_specs: bool = False) -> str:
        """
        生成系统提示词
        
        Args:
            include_all_specs: 是否包含所有domain的完整规格（False则仅包含简要描述）
        
        Returns:
            系统提示词
        """
        if include_all_specs:
            # Stage 2: 包含完整规格
            return self._generate_full_spec_prompt()
        else:
            # Stage 1: 仅包含domain简要描述
            return self._generate_domain_selection_prompt()
    
    def _generate_domain_selection_prompt(self) -> str:
        """生成第一阶段（Domain Selection）使用的系统提示词。

        仅列出各 domain 的名称和简述，让 LLM 快速判断当前话语属于哪个业务域，
        避免在第一阶段暴露完整参数规格（减少 token 消耗，降低决策干扰）。
        """
        prompt_parts = [
            "You are a task-oriented dialogue assistant.",
            "Your task is to identify the relevant domain(s) from the user's utterance.",
            "",
            "Available domains:"
        ]
        
        for domain in self.domains.values():
            prompt_parts.append(f"- {domain.name}: {domain.description}")
        
        prompt_parts.extend([
            "",
            "Based on the conversation history and current user utterance, identify the relevant domain(s).",
            "Output format:",
            "<domain>domain_name</domain>",
            "",
            "You can output multiple domains if needed."
        ])
        
        return "\n".join(prompt_parts)
    
    def _generate_full_spec_prompt(self) -> str:
        """生成第二阶段（Function Calling）使用的系统提示词。

        包含每个 domain 的完整函数规格（参数名、类型、枚举值等），
        引导 LLM 以 XML 标签格式输出结构化的 function call，并附带自然语言回复。
        """
        prompt_parts = [
            "You are a task-oriented dialogue assistant with function calling capability.",
            "Use the provided functions to track dialogue state and generate appropriate responses.",
            "",
            "Available functions:"
        ]
        
        for domain in self.domains.values():
            prompt_parts.append("")
            prompt_parts.append(domain.to_prompt_format())
        
        prompt_parts.extend([
            "",
            "Instructions:",
            "1. Based on the conversation, call the appropriate function with relevant parameters",
            "2. Output the function call in this format:",
            "   <function_call name=\"function_name\">",
            "   {\"param1\": \"value1\", \"param2\": \"value2\"}",
            "   </function_call>",
            "3. After the function call, provide a natural language response to the user",
            "",
            "Remember: Only fill parameters that are mentioned or can be inferred from the conversation."
        ])
        
        return "\n".join(prompt_parts)
    
    def generate_function_spec_for_domain(self, domain_name: str) -> str:
        """
        为特定domain生成函数规格
        
        Args:
            domain_name: domain名称
        
        Returns:
            函数规格文本
        """
        domain = self.get_domain(domain_name)
        if not domain:
            return f"Domain '{domain_name}' not found."
        
        return domain.to_prompt_format()
    
    def to_json_schemas(self) -> List[Dict]:
        """
        导出所有domain为JSON schemas（OpenAI格式）
        
        Returns:
            JSON schema列表
        """
        return [domain.to_json_schema() for domain in self.domains.values()]
