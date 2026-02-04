"""
FnCTOD Response Parser

解析 FnCTOD 的响应，包括 <function_call> 和自然语言回复
"""

import re
import json
from typing import Dict, List, Optional, Tuple, Any
from .data_models import FunctionCall
from lib.utils.logger import get_logger

logger = get_logger(__name__)


class FnCTODResponseParser:
    """
    FnCTOD响应解析器
    
    解析LLM输出，提取：
    1. Domain选择（Stage 1）
    2. Function call（Stage 2）
    3. 自然语言回复
    """
    
    def __init__(self):
        """初始化解析器"""
        logger.debug("FnCTODResponseParser 初始化")
    
    def parse_domain_selection(self, response: str) -> List[str]:
        """
        解析domain选择（Stage 1）
        
        Args:
            response: LLM响应
        
        Returns:
            domain名称列表
        """
        domains = []
        
        # 匹配 <domain>name</domain>
        pattern = r'<domain>(.*?)</domain>'
        matches = re.findall(pattern, response, re.IGNORECASE)
        
        for match in matches:
            domain_name = match.strip()
            if domain_name:
                domains.append(domain_name)
                logger.debug(f"检测到domain: {domain_name}")
        
        if not domains:
            logger.warning("未检测到domain标签，尝试从文本中推断")
            # 尝试从响应中提取可能的domain名称
            # 这是一个简单的fallback策略
            words = response.lower().split()
            common_domains = ['hotel', 'restaurant', 'attraction', 'train', 'taxi', 'insurance', 'callcenter', 'chat']
            for domain in common_domains:
                if domain in words:
                    domains.append(domain)
                    logger.debug(f"推断domain: {domain}")
        
        return domains
    
    def parse_function_call(self, response: str) -> Tuple[Optional[FunctionCall], str]:
        """
        解析function call（Stage 2）
        
        Args:
            response: LLM响应
        
        Returns:
            (FunctionCall对象, 自然语言回复)
        """
        function_call = None
        natural_response = response
        
        # 匹配 <function_call name="...">...</function_call>
        pattern = r'<function_call\s+name="([^"]+)"\s*>(.*?)</function_call>'
        match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
        
        if match:
            function_name = match.group(1).strip()
            arguments_str = match.group(2).strip()
            
            logger.debug(f"检测到function call: {function_name}")
            logger.debug(f"参数字符串: {arguments_str[:100]}...")
            
            # 解析参数
            arguments = self._parse_arguments(arguments_str)
            
            function_call = FunctionCall(
                function_name=function_name,
                arguments=arguments,
                raw_output=match.group(0)
            )
            
            # 提取function call之后的自然语言回复
            natural_response = response[match.end():].strip()
            
            # 如果没有后续回复，使用function call之前的内容
            if not natural_response:
                natural_response = response[:match.start()].strip()
            
            function_call.natural_response = natural_response
            
            logger.info(f"解析function call成功: {function_name}, {len(arguments)} 个参数")
        else:
            logger.warning("未检测到function call标签")
        
        return function_call, natural_response
    
    def _parse_arguments(self, arguments_str: str) -> Dict[str, Any]:
        """
        解析函数参数
        
        支持两种格式：
        1. JSON格式: {"key": "value", ...}
        2. 键值对格式: key=value, key2=value2
        
        Args:
            arguments_str: 参数字符串
        
        Returns:
            参数字典
        """
        arguments = {}
        
        # 首先尝试JSON格式
        try:
            arguments = json.loads(arguments_str)
            logger.debug(f"JSON解析成功: {len(arguments)} 个参数")
            return arguments
        except json.JSONDecodeError:
            logger.debug("JSON解析失败，尝试键值对格式")
        
        # 尝试键值对格式
        try:
            # 匹配 key=value 或 "key": "value" 格式
            patterns = [
                r'(["\']?)(\w+)\1\s*[=:]\s*(["\']?)([^,\n]+)\3',  # key=value 或 key:value
                r'(\w+)\s*[=:]\s*"([^"]+)"',  # key="value"
                r'(\w+)\s*[=:]\s*\'([^\']+)\'',  # key='value'
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, arguments_str)
                for match in matches:
                    if len(match) >= 2:
                        key = match[-2] if len(match) == 4 else match[0]
                        value = match[-1]
                        arguments[key.strip()] = value.strip()
            
            if arguments:
                logger.debug(f"键值对解析成功: {len(arguments)} 个参数")
                return arguments
        except Exception as e:
            logger.error(f"键值对解析失败: {e}")
        
        # 如果都失败，记录警告
        if not arguments:
            logger.warning(f"无法解析参数: {arguments_str[:100]}...")
        
        return arguments
    
    def extract_state_from_function_call(self, function_call: Optional[FunctionCall]) -> Dict[str, Any]:
        """
        从function call提取对话状态
        
        Args:
            function_call: FunctionCall对象
        
        Returns:
            状态字典
        """
        if not function_call:
            return {}
        
        # 将function的参数转换为状态
        # 格式: {domain-slot: value}
        state = {}
        domain = function_call.function_name
        
        for param_name, param_value in function_call.arguments.items():
            if param_value:  # 忽略空值
                state_key = f"{domain}-{param_name}"
                state[state_key] = param_value
        
        return state
