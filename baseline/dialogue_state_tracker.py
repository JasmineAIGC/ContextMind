"""
对话状态追踪器 (Dialogue State Tracker)

基于 ACL 2023 论文实现（全LLM方法）：
"ChatGPT for Zero-shot Dialogue State Tracking: A Solution or an Opportunity?"

完整实现零样本对话状态追踪系统，符合论文的8项核心要求，完全基于LLM：
1. 零样本方法（无需微调）
2. 基于提示词工程和槽位本体定义
3. 维护完整对话历史进行上下文管理
4. 累积式状态更新: DS_t = update(DS_{t-1}, updates)
5. 处理特殊值 (?, dontcare)
6. 过滤幻觉（非本体槽位）- 由LLM理解
7. 值归一化处理 - 由LLM理解
8. 鲁棒的 JSON 响应解析

核心特点：
    - 所有步骤完全基于LLM，不使用规则方法
    - PromptManager: 管理本体、约束和提示词生成
    - ResponseParser: 鲁棒的 JSON 提取
    - DialogueStateTracker: 多轮 DST 主控制器

版本: v7.4.0
"""

import json
import re
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SpecialValue(Enum):
    """
    特殊槽位值（符合 ACL 2023 论文定义）
    
    属性:
        UNKNOWN: "?" - 用户正在询问该槽位（未提供值）
        DONTCARE: "dontcare" - 用户不关心该槽位的值
    """
    UNKNOWN = "?"
    DONTCARE = "dontcare"


@dataclass
class DialogueTurn:
    """
    单轮对话数据结构
    
    属性:
        system_utterance: 系统/助手的回复
        user_utterance: 用户的输入
        predicted_state: 本轮之后的累积对话状态
        turn_updates: 仅从本轮提取的槽位更新
        raw_llm_response: 解析前的原始 LLM 响应（可选）
    """
    system_utterance: str
    user_utterance: str
    predicted_state: Dict[str, str] = field(default_factory=dict)
    turn_updates: Dict[str, str] = field(default_factory=dict)
    raw_llm_response: Optional[str] = None


class PromptManager:
    """
    提示词管理器（零样本对话状态追踪）
    
    管理本体（槽位定义）、分类约束和提示词生成，
    符合 ACL 2023 论文图2的规范。
    
    提示词结构遵循论文设计：
    1. 槽位本体定义（描述每个槽位代表什么）
    2. 分类约束（某些槽位的预定义值列表）
    3. 对话格式说明
    4. 特殊值处理规则 (?, dontcare)
    5. JSON输出格式规范
    
    注意：所有验证和归一化都由LLM理解，不使用规则方法
    
    属性:
        domain: 对话领域（如 "general", "hotel", "restaurant"）
        ontology_slots: 槽位名称到描述的映射字典
        categorical_constraints: 槽位名称到允许值的映射字典（用于LLM理解）
        
    示例:
        >>> pm = PromptManager(domain="restaurant")
        >>> pm.add_slot("food_type", "菜系类型", ["中餐", "意大利菜", "日料"])
        >>> instruction = pm.get_system_instruction()
    """
    
    def __init__(self, domain: str = "general"):
        """
        初始化提示词管理器
        
        参数:
            domain: 对话领域，用于上下文相关的槽位定义
                   支持的领域: "general", "hotel", "restaurant", "taxi", "train"
        """
        self.domain = domain
        
        # 槽位本体 - 将槽位名称映射到语义描述
        # 对应论文图2中的 "slots"
        self.ontology_slots: Dict[str, str] = {
            # 通用意图和话题槽位
            "intent": "用户的主要意图",
            "topic": "当前讨论的话题",
            "entity": "提到的实体或对象",
            
            # 时间相关槽位
            "time": "时间信息",
            "date": "日期信息",
            "duration": "持续时间",
            
            # 位置相关槽位
            "location": "地点或位置",
            "departure": "出发地",
            "destination": "目的地",
            
            # 偏好相关槽位
            "preference": "用户偏好",
            "requirement": "特殊要求",
            
            # 数值相关槽位
            "price": "价格或费用",
            "quantity": "数量",
            "rating": "评分或等级",
        }
        
        # 分类约束 - 具有预定义值集的槽位
        # 对应论文图2中的 "categorical"
        # 注意：这些约束用于LLM理解，不用于规则验证
        self.categorical_constraints: Dict[str, List[str]] = {
            "intent": ["询问", "预订", "修改", "取消", "确认", "投诉", "其他"],
            "rating": ["1星", "2星", "3星", "4星", "5星"],
            "price": ["便宜", "中等", "昂贵"],
        }
    
    def add_slot(self, slot_name: str, description: str, 
                 categorical_values: Optional[List[str]] = None) -> None:
        """
        向本体添加自定义槽位
        
        允许领域特定的槽位模式自定义
        
        参数:
            slot_name: 槽位名称（如 "food_type", "hotel_stars"）
            description: 该槽位代表什么的语义描述
            categorical_values: 可选的允许值列表（如果这是分类槽位）
                               提供后，LLM会优先从这些值中选择
                               
        示例:
            >>> pm = PromptManager()
            >>> pm.add_slot("food_type", "菜系类型", 
            ...            ["中餐", "意大利菜", "日料"])
        """
        self.ontology_slots[slot_name] = description
        if categorical_values:
            self.categorical_constraints[slot_name] = categorical_values
            logger.debug(f"添加了分类槽位 '{slot_name}'，有 {len(categorical_values)} 个值")
        else:
            logger.debug(f"添加了自由形式槽位 '{slot_name}'")
    
    def remove_slot(self, slot_name: str) -> bool:
        """
        从本体中移除槽位
        
        参数:
            slot_name: 要移除的槽位名称
            
        返回:
            如果槽位被移除返回 True，如果不存在返回 False
        """
        removed = False
        if slot_name in self.ontology_slots:
            del self.ontology_slots[slot_name]
            removed = True
        if slot_name in self.categorical_constraints:
            del self.categorical_constraints[slot_name]
            removed = True
        return removed
    
    def get_slot_names(self) -> Set[str]:
        """
        获取所有定义的槽位名称
        
        返回:
            槽位名称的集合
        """
        return set(self.ontology_slots.keys())
    
    def get_system_instruction(self) -> str:
        """
        生成系统指令提示词（符合论文图2格式）
        
        构建完整的零样本DST提示词，包含：
        - 槽位本体定义
        - 分类约束（用于LLM理解）
        - 特殊值规则
        - 输出格式要求
        
        返回:
            完整的系统指令字符串
        """
        instruction = f"""你是一个智能的对话状态追踪助手。请从对话中提取结构化信息。

## 槽位定义（Slots）
以下是需要追踪的槽位及其含义：

{json.dumps(self.ontology_slots, ensure_ascii=False, indent=2)}

## 分类约束（Categorical）
某些槽位只能取特定的值（请优先使用这些值）：

{json.dumps(self.categorical_constraints, ensure_ascii=False, indent=2)}

## 特殊值规则
- 如果用户**询问**某个槽位的信息但没有提供值，请填入 "?"
- 如果用户明确表示**不关心**某个槽位，请填入 "dontcare"

## 输出格式
请以JSON格式输出本轮对话中**用户更新的槽位**：

```json
{{
  "slot_name": "value",
  "another_slot": "value"
}}
```

## 重要说明
1. **只输出用户在本轮对话中提到或更新的槽位**
2. **值归一化**：请将不同表述统一为标准形式（如"很便宜"→"便宜"，"挺贵的"→"昂贵"）
3. **分类值**：对于有分类约束的槽位，请尽量使用预定义的值
4. **理解语义**：请理解用户的真实意图，而不是机械匹配关键词
5. **如果本轮没有更新任何槽位，返回空对象 {{}}**

现在请分析以下对话：
"""
        return instruction
    
    def format_dialogue_turn(self, system_utterance: str, user_utterance: str) -> str:
        """
        格式化单轮对话（符合论文格式）
        
        参数:
            system_utterance: 系统的话语
            user_utterance: 用户的话语
            
        返回:
            格式化的对话轮次字符串
        """
        return f'system: "{system_utterance}"\nuser: "{user_utterance}"'


class ResponseParser:
    """
    响应解析器（完全基于LLM输出）
    
    从LLM的自然语言响应中提取JSON格式的槽位更新。
    使用多策略解析以处理各种输出格式，但不进行规则验证。
    
    解析策略（按优先级）：
    1. 直接JSON解析 - 适用于干净的输出
    2. 正则提取JSON - 处理嵌入式JSON
    3. 键值对提取 - 后备方案
    
    注意：所有过滤和验证都由LLM理解，解析器只负责提取结构
    
    方法:
        extract_json: 从文本中提取JSON对象
        filter_hallucinations: 基于LLM理解过滤（保留本体槽位）
    """
    
    def __init__(self, ontology_slots: Set[str]):
        """
        初始化响应解析器
        
        参数:
            ontology_slots: 本体中定义的有效槽位名称集合
        """
        self.ontology_slots = ontology_slots
    
    def extract_json(self, text: str) -> Dict[str, str]:
        """
        从LLM响应文本中提取JSON对象（多策略）
        
        尝试多种解析策略以处理不同格式的LLM输出。
        
        参数:
            text: LLM的原始响应文本
            
        返回:
            提取的槽位更新字典，如果解析失败则返回空字典
        """
        if not text or not text.strip():
            return {}
        
        # 策略1：直接JSON解析（最快，适用于干净的输出）
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
            elif isinstance(parsed, list) and len(parsed) > 0:
                if isinstance(parsed[0], dict):
                    # 处理字典列表：合并它们
                    result = {}
                    for item in parsed:
                        if isinstance(item, dict):
                            result.update(item)
                    return result
        except json.JSONDecodeError:
            pass
        
        # 策略2：基于正则的JSON提取（处理嵌入的JSON）
        extracted = self._extract_json_with_regex(text)
        if extracted:
            return extracted
        
        # 策略3：键值对提取（用于格式错误的JSON的后备方案）
        extracted = self._extract_key_value_pairs(text)
        if extracted:
            return extracted
        
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
    
    def filter_hallucinations(self, updates: Dict[str, str]) -> Dict[str, str]:
        """
        过滤幻觉（只保留本体中定义的槽位）
        
        虽然我们依赖LLM理解，但仍需基本的本体检查以过滤明显错误。
        
        参数:
            updates: 从LLM响应中提取的槽位更新
            
        返回:
            过滤后的槽位更新（只包含本体中定义的槽位）
        """
        filtered = {}
        for slot, value in updates.items():
            # 过滤1：只保留本体中定义的槽位
            if slot in self.ontology_slots:
                # 保留值（不进行规则归一化或验证，信任LLM理解）
                filtered[slot] = value
            else:
                logger.debug(f"过滤幻觉槽位: {slot}")
        
        return filtered


class DialogueStateTracker:
    """
    对话状态追踪器（完全基于LLM）
    
    实现完整的零样本对话状态追踪系统，符合ACL 2023论文规范。
    所有步骤（槽位提取、值归一化、分类验证）都由LLM理解，不使用规则方法。
    
    核心特性：
    - 完全零样本（无需训练或微调）
    - 基于提示词工程
    - 维护完整对话历史
    - 累积式状态更新
    - LLM理解所有语义（包括值归一化和分类）
    
    属性:
        prompt_manager: 提示词管理器
        llm_client: LLM客户端（用于所有推理）
        messages: 完整的对话历史
        current_state: 当前累积的对话状态
        dialogue_history: 所有轮次的对话历史
        
    示例:
        >>> from utils.llm_client import SimpleLLMClient
        >>> llm = SimpleLLMClient()
        >>> pm = PromptManager(domain="restaurant")
        >>> tracker = DialogueStateTracker(llm_client=llm, prompt_manager=pm)
        >>> tracker.reset_dialogue()
        >>> state = await tracker.process_turn("你好", "我想订一家中餐厅")
    """
    
    def __init__(self, 
                 llm_client=None,
                 prompt_manager: Optional[PromptManager] = None,
                 domain: str = "general"):
        """
        初始化对话状态追踪器
        
        参数:
            llm_client: LLM客户端实例（用于所有推理和理解）
            prompt_manager: 可选的提示词管理器。如果未提供，将创建默认实例
            domain: 对话领域（如果未提供prompt_manager）
        """
        self.llm_client = llm_client
        self.prompt_manager = prompt_manager or PromptManager(domain=domain)
        self.response_parser = ResponseParser(
            ontology_slots=self.prompt_manager.get_slot_names()
        )
        
        # 对话状态
        self.messages: List[Dict[str, str]] = []
        self.current_state: Dict[str, str] = {}
        self.dialogue_history: List[DialogueTurn] = []
        
        logger.info(f"初始化DialogueStateTracker (领域={domain}, 槽位数={len(self.prompt_manager.ontology_slots)})")
    
    def reset_dialogue(self) -> None:
        """
        重置对话状态（开始新对话）
        
        清空所有历史记录和状态，准备开始新的对话会话。
        """
        self.messages = [
            {"role": "system", "content": self.prompt_manager.get_system_instruction()}
        ]
        self.current_state = {}
        self.dialogue_history = []
        logger.info("对话状态已重置")
    
    async def process_turn(self, 
                          system_utterance: str, 
                          user_utterance: str) -> Dict[str, str]:
        """
        处理单轮对话（完全基于LLM）
        
        这是DST的核心方法，执行以下步骤（全部由LLM处理）：
        1. 格式化对话轮次
        2. 调用LLM提取槽位更新（LLM理解值归一化和分类）
        3. 解析LLM响应
        4. 基本幻觉过滤（只保留本体槽位）
        5. 更新累积状态
        
        参数:
            system_utterance: 系统的话语
            user_utterance: 用户的话语
            
        返回:
            更新后的累积对话状态
            
        示例:
            >>> state = await tracker.process_turn(
            ...     "请问需要什么帮助？",
            ...     "我想订一家价格不贵的中餐厅"
            ... )
            >>> print(state)
            {'intent': '预订', 'food_type': '中餐', 'price': '中等'}
        """
        # 格式化本轮对话
        turn_prompt = self.prompt_manager.format_dialogue_turn(
            system_utterance, user_utterance
        )
        
        # 添加到消息历史
        self.messages.append({"role": "user", "content": turn_prompt})
        
        # 调用LLM提取槽位（LLM处理所有语义理解）
        if self.llm_client:
            try:
                response = await self.llm_client.chat_async(
                    messages=self.messages,
                    temperature=0.0  # 确保输出确定性
                )
            except Exception as e:
                logger.error(f"LLM调用失败: {e}")
                response = "{}"
        else:
            logger.warning("未提供LLM客户端，使用空响应")
            response = "{}"
        
        # 解析LLM响应
        turn_updates = self.response_parser.extract_json(response)
        
        # 基本幻觉过滤（只保留本体槽位）
        turn_updates = self.response_parser.filter_hallucinations(turn_updates)
        
        # 累积更新状态（DS_t = update(DS_{t-1}, updates)）
        self.current_state.update(turn_updates)
        
        # 将助手响应添加到历史
        self.messages.append({"role": "assistant", "content": response})
        
        # 记录对话轮次
        dialogue_turn = DialogueTurn(
            system_utterance=system_utterance,
            user_utterance=user_utterance,
            predicted_state=self.current_state.copy(),
            turn_updates=turn_updates,
            raw_llm_response=response
        )
        self.dialogue_history.append(dialogue_turn)
        
        logger.info(f"轮次 {len(self.dialogue_history)}: 更新了 {len(turn_updates)} 个槽位")
        logger.debug(f"本轮更新: {turn_updates}")
        logger.debug(f"当前状态: {self.current_state}")
        
        return self.current_state.copy()
    
    def get_current_state(self) -> Dict[str, str]:
        """
        获取当前对话状态
        
        返回:
            当前累积的对话状态（副本）
        """
        return self.current_state.copy()
    
    @property
    def turns(self) -> List[DialogueTurn]:
        """
        获取对话历史（别名属性，用于向后兼容）
        
        返回:
            对话历史列表
        """
        return self.dialogue_history
    
    def get_slot_value(self, slot_name: str) -> Optional[str]:
        """
        获取特定槽位的值
        
        参数:
            slot_name: 槽位名称
            
        返回:
            槽位值，如果未设置则返回 None
        """
        return self.current_state.get(slot_name)
    
    def has_slot(self, slot_name: str) -> bool:
        """
        检查槽位是否已设置
        
        参数:
            slot_name: 槽位名称
            
        返回:
            如果槽位已设置返回 True
        """
        return slot_name in self.current_state
    
    def clear_slot(self, slot_name: str) -> bool:
        """
        清除特定槽位
        
        参数:
            slot_name: 槽位名称
            
        返回:
            如果槽位被清除返回 True
        """
        if slot_name in self.current_state:
            del self.current_state[slot_name]
            return True
        return False
    
    def get_dialogue_history(self) -> List[DialogueTurn]:
        """
        获取完整对话历史
        
        返回:
            所有对话轮次的列表
        """
        return self.dialogue_history.copy()
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取追踪统计信息
        
        返回:
            包含统计数据的字典
        """
        return {
            "total_turns": len(self.dialogue_history),
            "total_slots_filled": len(self.current_state),
            "ontology_size": len(self.prompt_manager.ontology_slots),
            "domain": self.prompt_manager.domain,
        }


# 版本信息
__version__ = "7.4.0"
__all__ = [
    "DialogueStateTracker",
    "PromptManager",
    "ResponseParser",
    "DialogueTurn",
    "SpecialValue",
]
