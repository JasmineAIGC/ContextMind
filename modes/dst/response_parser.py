"""
响应解析器（Response Parser）

鲁棒的JSON响应解析，支持多种格式和容错处理。

版本: v0.2.1
"""

import json
import re
from typing import Dict, List, Optional, Set
from lib.utils.logger import get_logger

logger = get_logger(__name__)


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
                 enable_filtering: bool = False,
                 categorical_slots: Optional[Dict[str, list]] = None):
        """
        初始化响应解析器
        
        参数:
            ontology_slots: 本体中定义的槽位名称集合（可选）
            enable_filtering: 是否启用槽位过滤（默认False，支持动态槽位）
            categorical_slots: 分类槽位及其候选值（用于归一化）
        """
        self.ontology_slots = ontology_slots or set()
        self.enable_filtering = enable_filtering
        self.categorical_slots = categorical_slots or {}  # 新增
    
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
            logger.debug("响应为空")
            return {}
        
        # 策略1：直接JSON解析（最快，适用于干净的输出）
        logger.debug("尝试策略1: 直接JSON解析")
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                logger.debug(f"策略1成功: 提取到 {len(parsed)} 个字段")
                return self._filter_if_needed(parsed)
            elif isinstance(parsed, list) and len(parsed) > 0:
                if isinstance(parsed[0], dict):
                    # 处理字典列表：合并它们
                    result = {}
                    for item in parsed:
                        if isinstance(item, dict):
                            result.update(item)
                    logger.debug(f"策略1成功（列表合并）: 提取到 {len(result)} 个字段")
                    return self._filter_if_needed(result)
        except json.JSONDecodeError as e:
            logger.debug(f"策略1失败: {e}")
        
        # 策略2：基于正则的JSON提取（处理嵌入的JSON）
        logger.debug("尝试策略2: 正则表达式提取JSON")
        extracted = self._extract_json_with_regex(text)
        if extracted:
            logger.debug(f"策略2成功: 提取到 {len(extracted)} 个字段")
            return self._filter_if_needed(extracted)
        else:
            logger.debug("策略2失败: 未找到有效的JSON结构")
        
        # 策略3：键值对提取（用于格式错误的JSON的后备方案）
        logger.debug("尝试策略3: 键值对提取")
        extracted = self._extract_key_value_pairs(text)
        if extracted:
            logger.debug(f"策略3成功: 提取到 {len(extracted)} 个字段")
            return self._filter_if_needed(extracted)
        else:
            logger.debug("策略3失败: 未找到键值对")
        
        # 所有策略都失败了
        logger.warning(f"无法从响应中提取JSON: {text[:100]}...")
        logger.debug(f"完整失败响应:\n{text}")
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
    
    def normalize_value(self, slot: str, value: str, candidates: List[str] = None, strict: bool = False) -> Optional[str]:
        """
        归一化槽位值（优化功能）
        
        对于分类槽位，尝试匹配到预定义的候选值。
        实现ACL 2023论文中的手工归一化步骤。
        
        参数:
            slot: 槽位名称
            value: 原始值
            candidates: 候选值列表（如果未提供则使用self.categorical_slots）
            strict: 是否严格模式（只接受精确匹配，不接受模糊匹配）
            
        返回:
            归一化后的值，strict模式下无匹配返回None
        """
        if not value or not value.strip():
            return value
        
        # 基础归一化：去除首尾空格
        normalized = value.strip()
        
        # 确定候选值列表
        if candidates is None:
            if slot in self.categorical_slots:
                candidates = self.categorical_slots[slot]
            else:
                # 非分类槽位，返回归一化后的值
                return normalized
        
        value_lower = normalized.lower()
        
        # 1. 精确匹配（忽略大小写）
        for candidate in candidates:
            if value_lower == candidate.lower():
                return candidate
        
        # 严格模式：不允许模糊匹配
        if strict:
            logger.debug(f"严格模式下 {slot}='{value}' 无精确匹配，返回None")
            return None
        
        # 2. 包含匹配（非严格模式）
        for candidate in candidates:
            if value_lower in candidate.lower() or candidate.lower() in value_lower:
                logger.debug(f"归一化: {slot}='{value}' -> '{candidate}'")
                return candidate
        
        return normalized
    
    def normalize_extracted(self, extracted: Dict[str, str], 
                           allowed_slots: Dict[str, str],
                           categorical_slots: Dict[str, List[str]]) -> Dict[str, str]:
        """
        严格归一化提取的槽位（仅保留预定义槽位，严格匹配分类值）
        
        参数:
            extracted: 从LLM响应中提取的槽位
            allowed_slots: 允许的槽位定义
            categorical_slots: 分类槽位的候选值
            
        返回:
            归一化后的槽位字典（只包含预定义槽位和值）
        """
        normalized = {}
        
        for slot, value in extracted.items():
            # 跳过空值（空字符串或仅包含空白字符）
            if not value or not value.strip():
                continue
            
            # 过滤1：只保留预定义的槽位名称
            if slot not in allowed_slots:
                logger.warning(f"跳过未定义的槽位: {slot} (值: {value})")
                continue
            
            # 过滤2：对分类槽位进行严格归一化
            if slot in categorical_slots:
                normalized_value = self.normalize_value(
                    slot, value, categorical_slots[slot], strict=True
                )
                if normalized_value:
                    normalized[slot] = normalized_value
                else:
                    logger.warning(f"槽位 {slot} 的值 '{value}' 不在预定义列表中，已跳过")
            else:
                # 非分类槽位，直接保留（但值必须非空）
                if value.strip():
                    normalized[slot] = value
        
        return normalized
