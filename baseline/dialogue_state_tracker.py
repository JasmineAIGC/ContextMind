"""
Dialogue State Tracker - 对话状态追踪器

基于 ACL 2023 论文《ChatGPT for Zero-shot Dialogue State Tracking》实现
采用 Zero-shot 方式，通过精心设计的 Prompt 实现对话状态追踪

核心思想：
1. 完全不进行微调（Zero-shot）
2. 仅通过 Prompt 和 ChatGPT 的对话上下文能力
3. 从自然语言响应中提取结构化状态
"""

import json
import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class DialogueTurn:
    """对话轮次"""
    system_utterance: str
    user_utterance: str
    predicted_state: Dict[str, str] = field(default_factory=dict)


class PromptManager:
    """
    提示词管理器
    
    根据论文 Figure 2 设计，包含：
    1. 槽位定义 (ontology_slots)
    2. 分类约束 (categorical_constraints)
    3. 系统指令构建
    """
    
    def __init__(self, domain: str = "general"):
        """
        初始化提示词管理器
        
        Args:
            domain: 对话领域 (general, hotel, restaurant, taxi, train 等)
        """
        self.domain = domain
        
        # 槽位本体定义 - 对应论文 Figure 2 的 "slots"
        # 这里提供通用槽位，可根据具体领域扩展
        self.ontology_slots = {
            # 通用槽位
            "intent": "用户的主要意图",
            "topic": "当前讨论的话题",
            "entity": "提到的实体或对象",
            
            # 时间相关
            "time": "时间信息",
            "date": "日期信息",
            "duration": "持续时间",
            
            # 地点相关
            "location": "地点或位置",
            "departure": "出发地",
            "destination": "目的地",
            
            # 偏好相关
            "preference": "用户偏好",
            "requirement": "特殊要求",
            
            # 数值相关
            "price": "价格或费用",
            "quantity": "数量",
            "rating": "评分或等级",
        }
        
        # 分类约束 - 对应论文 Figure 2 的 "categorical"
        # 某些槽位只能取预定义的值
        self.categorical_constraints = {
            "intent": ["询问", "预订", "修改", "取消", "确认", "投诉", "其他"],
            "rating": ["1星", "2星", "3星", "4星", "5星"],
            "price": ["便宜", "中等", "昂贵"],
        }
        
        # 值归一化映射
        self.value_normalization = {
            "便宜的": "便宜",
            "贵的": "昂贵",
            "很贵": "昂贵",
            "不贵": "中等",
            "一般": "中等",
        }
    
    def add_slot(self, slot_name: str, description: str, 
                 categorical_values: Optional[List[str]] = None):
        """
        添加自定义槽位
        
        Args:
            slot_name: 槽位名称
            description: 槽位描述
            categorical_values: 分类值列表（可选）
        """
        self.ontology_slots[slot_name] = description
        if categorical_values:
            self.categorical_constraints[slot_name] = categorical_values
    
    def get_system_instruction(self) -> str:
        """
        构建系统指令 Prompt
        
        根据论文 Figure 2 的格式构建初始指令
        
        Returns:
            系统指令字符串
        """
        instruction = f"""请考虑以下槽位（"slots"）列表，以 JSON 格式提供：

"slots": {json.dumps(self.ontology_slots, indent=2, ensure_ascii=False)}

某些槽位只能从预定义列表中取值：

"categorical": {json.dumps(self.categorical_constraints, indent=2, ensure_ascii=False)}

现在考虑以下系统（"system"）和用户（"user"）之间的对话。

请告诉我用户在最新回复中更新了哪些槽位？
以 JSON 格式呈现更新内容。如果没有槽位被更新，返回空的 JSON 对象。

特殊规则：
1. 如果用户请求某个槽位信息（但未提供具体值），用 "?" 填充
2. 如果用户表示不关心某个槽位，用 "dontcare" 填充
3. 只更新明确提到或可从上下文推断的槽位
4. 保持与之前对话的一致性，注意共指消解

请直接返回 JSON 格式的槽位更新，不要包含其他解释。"""
        
        return instruction
    
    def normalize_value(self, value: str) -> str:
        """
        值归一化处理
        
        Args:
            value: 原始值
            
        Returns:
            归一化后的值
        """
        # 去除多余空格
        value = value.strip()
        
        # 应用归一化映射
        if value in self.value_normalization:
            return self.value_normalization[value]
        
        # 统一小写（对英文）
        # value = value.lower()
        
        return value


class ResponseParser:
    """
    响应解析器
    
    从 ChatGPT 的自然语言回复中提取 JSON 格式的状态更新
    处理论文中提到的解析不稳定性问题
    """
    
    def __init__(self, prompt_manager: PromptManager):
        """
        初始化响应解析器
        
        Args:
            prompt_manager: 提示词管理器实例
        """
        self.prompt_manager = prompt_manager
    
    def extract_json(self, text: str) -> Dict[str, str]:
        """
        使用鲁棒的方法从文本中提取 JSON
        
        对应论文 Section 4 提到的正则表达式提取方法
        
        Args:
            text: ChatGPT 的响应文本
            
        Returns:
            提取的槽位更新字典
        """
        try:
            # 方法 1: 尝试直接解析整个文本
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
            
            # 方法 2: 使用正则表达式查找 JSON 块
            # 匹配最外层的花括号或方括号
            json_patterns = [
                r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',  # 嵌套花括号
                r'\{.*?\}',  # 简单花括号
                r'\[.*?\]',  # 方括号
            ]
            
            for pattern in json_patterns:
                match = re.search(pattern, text, re.DOTALL)
                if match:
                    json_str = match.group(0)
                    try:
                        parsed = json.loads(json_str)
                        # 确保返回字典格式
                        if isinstance(parsed, dict):
                            return parsed
                        elif isinstance(parsed, list) and len(parsed) > 0:
                            # 如果是列表，尝试合并
                            result = {}
                            for item in parsed:
                                if isinstance(item, dict):
                                    result.update(item)
                            return result
                    except json.JSONDecodeError:
                        continue
            
            # 方法 3: 尝试提取键值对
            # 格式: "key": "value"
            kv_pattern = r'"([^"]+)"\s*:\s*"([^"]*)"'
            matches = re.findall(kv_pattern, text)
            if matches:
                return dict(matches)
            
            # 如果所有方法都失败，返回空字典
            return {}
            
        except Exception as e:
            # 发生任何异常，返回空字典
            return {}
    
    def filter_hallucinations(self, updates: Dict[str, str]) -> Dict[str, str]:
        """
        过滤幻觉 - 只保留本体中定义的槽位
        
        对应论文中提到的约 90.4% 有效预测，9.6% 为幻觉
        
        Args:
            updates: 原始更新字典
            
        Returns:
            过滤后的更新字典
        """
        filtered = {}
        valid_slots = set(self.prompt_manager.ontology_slots.keys())
        
        for slot, value in updates.items():
            # 只保留在本体中定义的槽位
            if slot in valid_slots:
                # 应用值归一化
                normalized_value = self.prompt_manager.normalize_value(value)
                filtered[slot] = normalized_value
        
        return filtered


class DialogueStateTracker:
    """
    对话状态追踪器
    
    实现完整的 Zero-shot 对话状态追踪流程
    
    工作流程：
    1. 维护对话历史（messages）
    2. 构建 Prompt 发送给 ChatGPT
    3. 解析响应提取状态更新
    4. 累积更新到当前状态
    """
    
    def __init__(self, 
                 llm_client: Optional[Any] = None,
                 prompt_manager: Optional[PromptManager] = None,
                 domain: str = "general"):
        """
        初始化对话状态追踪器
        
        Args:
            llm_client: LLM 客户端（可选）
            prompt_manager: 提示词管理器（可选）
            domain: 对话领域
        """
        self.llm_client = llm_client
        self.prompt_manager = prompt_manager or PromptManager(domain)
        self.response_parser = ResponseParser(self.prompt_manager)
        
        # 对话历史（用于 ChatGPT API）
        self.messages: List[Dict[str, str]] = []
        
        # 当前累积的对话状态
        self.current_state: Dict[str, str] = {}
        
        # 对话轮次历史
        self.turns: List[DialogueTurn] = []
    
    def reset_dialogue(self):
        """开始新对话前重置"""
        self.messages = [
            {
                "role": "system",
                "content": self.prompt_manager.get_system_instruction()
            }
        ]
        self.current_state = {}
        self.turns = []
    
    async def process_turn(self, 
                          system_utterance: str, 
                          user_utterance: str) -> Dict[str, str]:
        """
        处理一轮对话
        
        对应论文的核心流程：
        1. 构建当前轮次的 Prompt
        2. 调用 ChatGPT API
        3. 解析响应
        4. 更新状态
        
        Args:
            system_utterance: 系统（助手）的话语
            user_utterance: 用户的话语
            
        Returns:
            当前累积的对话状态
        """
        # 1. 构建当前轮次的输入
        # 格式: system: "..." \n user: "..."
        turn_prompt = f'system: "{system_utterance}"\nuser: "{user_utterance}"'
        
        # 2. 添加到消息历史
        self.messages.append({
            "role": "user",
            "content": turn_prompt
        })
        
        # 3. 调用 LLM API（如果有客户端）
        if self.llm_client:
            raw_output = await self._call_llm()
            
            # 4. 将模型的回复加入历史，保持上下文连贯
            self.messages.append({
                "role": "assistant",
                "content": raw_output
            })
            
            # 5. 解析响应提取状态更新
            turn_update = self.response_parser.extract_json(raw_output)
            
            # 6. 过滤幻觉
            turn_update = self.response_parser.filter_hallucinations(turn_update)
        else:
            # 无 LLM 客户端时，使用规则提取（降级方案）
            turn_update = self._extract_with_rules(user_utterance)
            raw_output = json.dumps(turn_update, ensure_ascii=False)
        
        # 7. 更新累积状态
        self._update_state(turn_update)
        
        # 8. 记录本轮对话
        turn = DialogueTurn(
            system_utterance=system_utterance,
            user_utterance=user_utterance,
            predicted_state=self.current_state.copy()
        )
        self.turns.append(turn)
        
        return self.current_state.copy()
    
    async def _call_llm(self) -> str:
        """
        调用 LLM API
        
        Returns:
            LLM 的响应文本
        """
        try:
            # 假设 llm_client 有 chat_async 或类似方法
            if hasattr(self.llm_client, 'chat_async'):
                response = await self.llm_client.chat_async(
                    messages=self.messages,
                    temperature=0.0  # 保持输出确定性
                )
            elif hasattr(self.llm_client, 'chat'):
                response = self.llm_client.chat(
                    messages=self.messages,
                    temperature=0.0
                )
            else:
                # 尝试直接调用
                response = await self.llm_client(
                    messages=self.messages,
                    temperature=0.0
                )
            
            # 提取响应内容
            if isinstance(response, str):
                return response
            elif hasattr(response, 'content'):
                return response.content
            elif hasattr(response, 'choices'):
                return response.choices[0].message.content
            else:
                return str(response)
                
        except Exception as e:
            # 发生错误时返回空 JSON
            return "{}"
    
    def _extract_with_rules(self, user_utterance: str) -> Dict[str, str]:
        """
        基于规则的简单提取（降级方案）
        
        Args:
            user_utterance: 用户话语
            
        Returns:
            提取的槽位更新
        """
        updates = {}
        
        # 简单的关键词匹配示例
        if any(word in user_utterance for word in ["想要", "需要", "预订", "订"]):
            updates["intent"] = "预订"
        elif any(word in user_utterance for word in ["什么", "哪", "怎么", "如何"]):
            updates["intent"] = "询问"
        elif any(word in user_utterance for word in ["取消", "不要"]):
            updates["intent"] = "取消"
        
        # 提取地点
        location_keywords = ["在", "去", "到", "从"]
        for keyword in location_keywords:
            if keyword in user_utterance:
                # 简单提取
                parts = user_utterance.split(keyword)
                if len(parts) > 1:
                    location = parts[1].split("，")[0].split("。")[0].strip()[:20]
                    if len(location) > 0:
                        if keyword in ["去", "到"]:
                            updates["destination"] = location
                        elif keyword == "从":
                            updates["departure"] = location
                        else:
                            updates["location"] = location
        
        return updates
    
    def _update_state(self, updates: Dict[str, str]):
        """
        更新累积状态
        
        对应论文: DS_t = update(DS_{t-1}, predicted_updates)
        
        Args:
            updates: 本轮的槽位更新
        """
        for slot, value in updates.items():
            # 特殊值处理
            if value == "?":
                # 用户在询问，不更新状态
                continue
            elif value == "dontcare":
                # 用户不关心，记录这个状态
                self.current_state[slot] = "dontcare"
            elif value:
                # 正常更新
                self.current_state[slot] = value
    
    def get_current_state(self) -> Dict[str, str]:
        """获取当前累积的对话状态"""
        return self.current_state.copy()
    
    def get_turn_history(self) -> List[DialogueTurn]:
        """获取对话轮次历史"""
        return self.turns.copy()
