"""
DST 响应解析器

从 LLM 响应中提取 JSON 格式的槽位更新，支持多种格式和容错处理。
主类为 ``DSTResponseParser``。
"""

import json
import re
from typing import Dict, List, Optional, Set
from contextmind.infra.logger import get_logger

logger = get_logger(__name__)


class DSTResponseParser:
    """
    响应解析器（支持动态槽位）
    
    从LLM响应中提取JSON格式的槽位更新，支持多种解析策略。
    在动态槽位模式下，不过滤任何LLM提取的信息。
    """
    
    def __init__(self, 
                 ontology_slots: Optional[Set[str]] = None,
                 enable_filtering: bool = False,
                 categorical_slots: Optional[Dict[str, list]] = None,
                 embedding_client: Optional['EmbeddingClient'] = None):
        """
        初始化响应解析器
        
        参数:
            ontology_slots: 本体中定义的槽位名称集合（可选）
            enable_filtering: 是否启用槽位过滤。默认 False 以支持动态槽位——
                              LLM 可以自由提取任何槽位，而不被本体列表截断。
                              设为 True 则只保留 ontology_slots 中的槽位。
            categorical_slots: 分类槽位及其候选值（用于归一化）
            embedding_client: Embedding客户端，用于语义槽位名称匹配（可选）
        """
        self.ontology_slots = ontology_slots or set()
        self.enable_filtering = enable_filtering
        self.categorical_slots = categorical_slots or {}
        self.embedding_client = embedding_client
    
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
        
        logger.debug("尝试策略1: 直接JSON解析")
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                logger.debug(f"策略1成功: 提取到 {len(parsed)} 个字段")
                return self._filter_if_needed(parsed)
            elif isinstance(parsed, list) and len(parsed) > 0:
                if isinstance(parsed[0], dict):
                    # 部分 LLM 会将结果包装为列表；合并所有条目以防信息丢失。
                    result = {}
                    for item in parsed:
                        if isinstance(item, dict):
                            result.update(item)
                    logger.debug(f"策略1成功（列表合并）: 提取到 {len(result)} 个字段")
                    return self._filter_if_needed(result)
        except json.JSONDecodeError as e:
            logger.debug(f"策略1失败: {e}")
        
        logger.debug("尝试策略2: 正则表达式提取JSON")
        extracted = self._extract_json_with_regex(text)
        if extracted:
            logger.debug(f"策略2成功: 提取到 {len(extracted)} 个字段")
            return self._filter_if_needed(extracted)
        else:
            logger.debug("策略2失败: 未找到有效的JSON结构")
        
        logger.debug("尝试策略3: 键值对提取")
        extracted = self._extract_key_value_pairs(text)
        if extracted:
            logger.debug(f"策略3成功: 提取到 {len(extracted)} 个字段")
            return self._filter_if_needed(extracted)
        else:
            logger.debug("策略3失败: 未找到键值对")
        
        logger.warning(f"无法从响应中提取JSON: {text[:100]}...")
        logger.debug(f"完整失败响应:\n{text}")
        return {}
    
    def _extract_json_with_regex(self, text: str) -> Optional[Dict[str, str]]:
        """
        使用正则表达式从文本中提取JSON

        Tries patterns in decreasing flexibility: nested objects first, then
        flat objects, then arrays. Returns the first successfully parsed dict.
        
        参数:
            text: 包含JSON的文本
            
        返回:
            提取的字典，如果失败则返回 None
        """
        patterns = [
            r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',
            r'\{[^{}]+\}',
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
    
    def _find_similar_slot_name(self, llm_slot: str, expected_slots: Set[str]) -> Optional[str]:
        """
        使用语义相似度找到最相似的槽位名称（通用方法，适用于任何领域）
        
        LLM may use synonyms or slightly different phrasing for slot names.
        Embedding similarity generalises across domains without hard-coded
        lookup tables; the 0.85 threshold (on the [0,1]-scaled cosine score)
        was empirically chosen to avoid false positives while still catching
        minor paraphrases.
        
        参数:
            llm_slot: LLM提取的槽位名称
            expected_slots: 期望的本体槽位名称集合
            
        返回:
            最相似的槽位名称（如果相似度>0.85），否则返回None
        """
        if not expected_slots or not self.embedding_client:
            return None
        
        try:
            from contextmind.infra.embedding import calculate_embedding_similarity
            
            # 生成LLM槽位名的embedding
            llm_embedding = self.embedding_client.generate_embedding(llm_slot)
            if not llm_embedding:
                return None
            
            best_match = None
            best_similarity = 0.0
            
            # 计算与所有期望槽位的相似度
            for expected_slot in expected_slots:
                exp_embedding = self.embedding_client.generate_embedding(expected_slot)
                if not exp_embedding:
                    continue
                
                similarity, success = calculate_embedding_similarity(llm_embedding, exp_embedding)
                
                if success and similarity > best_similarity:
                    best_similarity = similarity
                    best_match = expected_slot
            
            # 仅接受高置信度匹配，避免跨槽位混淆。
            if best_similarity >= 0.85:
                logger.debug(f"语义槽位匹配: {llm_slot} -> {best_match} (相似度: {best_similarity:.3f})")
                return best_match
            
        except Exception as e:
            logger.warning(f"语义槽位匹配失败: {e}")
        
        return None
    
    def _filter_if_needed(self, updates: Dict[str, str]) -> Dict[str, str]:
        """
        根据配置决定是否过滤槽位，并使用语义相似度匹配槽位名称
        
        参数:
            updates: 从LLM响应中提取的槽位更新
            
        返回:
            过滤后的槽位更新（或原始更新）
        """
        filtered = {k: v for k, v in updates.items() if k != 'intent'}
        
        # 将 LLM 产生的近义词或非标准槽位名映射为规范名称，
        # 然后再执行本体过滤。
        if self.ontology_slots:
            mapped_updates = {}
            for slot, value in filtered.items():
                similar_slot = self._find_similar_slot_name(slot, self.ontology_slots)
                if similar_slot:
                    mapped_updates[similar_slot] = value
                else:
                    mapped_updates[slot] = value
            filtered = mapped_updates
        
        if not self.enable_filtering or not self.ontology_slots:
            return filtered
        
        final_filtered = {}
        for slot, value in filtered.items():
            if slot in self.ontology_slots:
                final_filtered[slot] = value
            else:
                logger.debug(f"过滤未知槽位: {slot}")
        
        return final_filtered
    
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
        if not value:
            return value
        
        # 确保value是字符串类型（处理int、bool等类型）
        value_str = str(value) if not isinstance(value, str) else value
        
        if not value_str.strip():
            return value_str
        
        normalized = value_str.strip()
        
        if candidates is None:
            if slot in self.categorical_slots:
                candidates = self.categorical_slots[slot]
            else:
                return normalized
        
        value_lower = normalized.lower()
        
        for candidate in candidates:
            if value_lower == candidate.lower():
                return candidate
        
        if strict:
            logger.debug(f"严格模式下 {slot}='{value}' 无精确匹配，返回None")
            return None
        
        for candidate in candidates:
            if value_lower in candidate.lower() or candidate.lower() in value_lower:
                logger.debug(f"归一化: {slot}='{value}' -> '{candidate}'")
                return candidate
        
        return normalized
    
    def normalize_extracted(self, extracted: Dict[str, str], 
                           allowed_slots: Dict[str, str],
                           categorical_slots: Dict[str, List[str]]) -> Dict[str, str]:
        """
        归一化提取的槽位
        
        在动态槽位模式下（enable_filtering=False），接受所有LLM提取的槽位。
        在严格模式下（enable_filtering=True），仅保留预定义槽位并严格匹配分类值。
        
        参数:
            extracted: 从LLM响应中提取的槽位
            allowed_slots: 允许的槽位定义（仅在严格模式下使用）
            categorical_slots: 分类槽位的候选值（用于值归一化）
            
        返回:
            归一化后的槽位字典
        """
        normalized = {}
        
        for slot, value in extracted.items():
            # 确保value是字符串类型（处理int、bool等类型）
            if value is None:
                continue
            
            value_str = str(value) if not isinstance(value, str) else value
            
            # 跳过空值（空字符串或仅包含空白字符）
            if not value_str or not value_str.strip():
                continue
            
            if not self.enable_filtering:
                if slot in categorical_slots:
                    normalized_value = self.normalize_value(
                        slot, value_str, categorical_slots[slot], strict=False
                    )
                    normalized[slot] = normalized_value if normalized_value else value_str
                else:
                    normalized[slot] = value_str
                continue
            
            if slot not in allowed_slots:
                logger.warning(f"跳过未定义的槽位: {slot} (值: {value_str})")
                continue
            
            if slot in categorical_slots:
                normalized_value = self.normalize_value(
                    slot, value_str, categorical_slots[slot], strict=True
                )
                if normalized_value:
                    normalized[slot] = normalized_value
                else:
                    logger.warning(f"槽位 {slot} 的值 '{value_str}' 不在预定义列表中，已跳过")
            else:
                if value_str.strip():
                    normalized[slot] = value_str
        
        return normalized



