"""
响应解析器（Response Parser）

鲁棒的JSON响应解析，支持多种格式和容错处理。

版本: v0.4.0
"""

import json
import re
import logging
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)


class ResponseParser:
    """
    响应解析器（支持动态槽位）
    
    从LLM响应中提取JSON格式的槽位更新，支持多种解析策略。
    在动态槽位模式下，不过滤任何LLM提取的信息。
    
    特性:
    - 多策略解析（直接解析、正则提取、键值对提取）
    - 处理嵌套和列表格式
    - 可选的幻觉过滤（仅在非动态模式下）
    
    属性:
        ontology_slots: 本体槽位集合（用于可选的过滤）
        enable_filtering: 是否启用槽位过滤（动态模式下为False）
    """
    
    def __init__(self, 
                 ontology_slots: Optional[Set[str]] = None,
                 enable_filtering: bool = False):
        """
        初始化响应解析器
        
        参数:
            ontology_slots: 本体中定义的槽位名称集合（可选）
            enable_filtering: 是否启用槽位过滤（默认False，支持动态槽位）
        """
        self.ontology_slots = ontology_slots or set()
        self.enable_filtering = enable_filtering
    
    def extract_json(self, text: str) -> Dict[str, str]:
        """
        从LLM响应中提取JSON（多策略鲁棒解析）
        
        使用三种策略依次尝试：
        1. 直接JSON解析
        2. 正则表达式提取JSON
        3. 键值对提取
        
        参数:
            text: LLM的原始响应文本
            
        返回:
            提取的槽位更新字典
        """
        if not text or not text.strip():
            return {}
        
        # 策略1：直接JSON解析（最快，适用于干净的输出）
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return self._filter_if_needed(parsed)
            elif isinstance(parsed, list) and len(parsed) > 0:
                if isinstance(parsed[0], dict):
                    # 处理字典列表：合并它们
                    result = {}
                    for item in parsed:
                        if isinstance(item, dict):
                            result.update(item)
                    return self._filter_if_needed(result)
        except json.JSONDecodeError:
            pass
        
        # 策略2：基于正则的JSON提取（处理嵌入的JSON）
        extracted = self._extract_json_with_regex(text)
        if extracted:
            return self._filter_if_needed(extracted)
        
        # 策略3：键值对提取（用于格式错误的JSON的后备方案）
        extracted = self._extract_key_value_pairs(text)
        if extracted:
            return self._filter_if_needed(extracted)
        
        # 所有策略都失败了
        logger.warning(f"无法从响应中提取JSON: {text[:100]}...")
        return {}
    
    def _extract_json_with_regex(self, text: str) -> Optional[Dict[str, str]]:
        """
        使用正则表达式从文本中提取JSON
        
        参数:
            text: 包含JSON的文本
            
        返回:
            提取的字典，如果失败则返回 None
        """
        # 按特异性排序的模式
        patterns = [
            # 嵌套花括号（处理复杂的嵌套结构）
            r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',
            # 简单花括号（单层对象）
            r'\{[^{}]+\}',
            # 方括号（数组格式）
            r'\[[^\[\]]+\]',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                try:
                    parsed = json.loads(match)
                    if isinstance(parsed, dict):
                        return parsed
                    elif isinstance(parsed, list) and len(parsed) > 0:
                        if isinstance(parsed[0], dict):
                            return parsed[0]
                except json.JSONDecodeError:
                    continue
        
        return None
    
    def _extract_key_value_pairs(self, text: str) -> Dict[str, str]:
        """
        从文本中提取键值对（后备解析方法）
        
        参数:
            text: 包含键值对的文本
            
        返回:
            提取的槽位字典
        """
        result = {}
        # 模式："key": "value" 或 'key': 'value'
        pattern = r'["\'](\w+)["\']\s*:\s*["\']([^"\']+)["\']'
        matches = re.findall(pattern, text)
        for key, value in matches:
            result[key] = value
        return result
    
    def _filter_if_needed(self, updates: Dict[str, str]) -> Dict[str, str]:
        """
        根据配置决定是否过滤槽位
        
        参数:
            updates: 从LLM响应中提取的槽位更新
            
        返回:
            过滤后的槽位更新（或原始更新）
        """
        if not self.enable_filtering or not self.ontology_slots:
            # 动态槽位模式：不过滤，接受所有LLM提取的信息
            return updates
        
        # 仅在启用过滤时才过滤
        filtered = {}
        for slot, value in updates.items():
            if slot in self.ontology_slots:
                filtered[slot] = value
            else:
                logger.debug(f"过滤未知槽位: {slot}")
        
        return filtered
