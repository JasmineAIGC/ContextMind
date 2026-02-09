"""
数据集适配器基类

定义标准化的对话数据结构和适配器接口，用于将不同格式的数据集
转换为统一的格式供 DST 和 FnCTOD 模式测试使用。
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any
from dataclasses import dataclass, field


@dataclass
class DialogueTurn:
    """
    标准化的对话轮次
    
    属性:
        turn_id: 轮次编号（从0开始）
        system_utterance: 系统/助手的回复
        user_utterance: 用户的输入
        expected_slots: 本轮期望提取的槽位-值对（用于评估）
    """
    turn_id: int
    system_utterance: str
    user_utterance: str
    expected_slots: Dict[str, Any]


@dataclass
class DialogueInstance:
    """
    标准化的对话实例
    
    属性:
        dialogue_id: 对话唯一标识符
        domain: 对话所属领域（如"酒店"、"餐厅"等）
        description: 对话描述或摘要
        turns: 对话轮次列表
        final_state: 对话结束时的完整状态
        metadata: 额外的元数据（可选）
    """
    dialogue_id: str
    domain: str
    description: str
    turns: List[DialogueTurn]
    final_state: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)


class DatasetAdapter(ABC):
    """
    数据集适配器抽象基类
    
    所有具体的数据集适配器都应继承此类并实现其抽象方法。
    适配器负责将原始数据集格式转换为标准化的 DialogueInstance 格式。
    """
    
    @abstractmethod
    def load_dialogue(self, dialogue_id: str) -> DialogueInstance:
        """
        加载单个对话实例
        
        Args:
            dialogue_id: 对话唯一标识符
            
        Returns:
            标准化的对话实例
            
        Raises:
            FileNotFoundError: 找不到指定的对话数据
            ValueError: 对话数据格式错误
        """
        pass
    
    @abstractmethod
    def get_all_dialogue_ids(self) -> List[str]:
        """
        获取所有对话ID列表
        
        Returns:
            所有可用的对话ID列表
        """
        pass
    
    @abstractmethod
    def get_domain_schema(self, domain: str) -> Dict[str, Any]:
        """
        获取指定领域的槽位Schema
        
        Args:
            domain: 领域名称
            
        Returns:
            领域的Schema定义，格式为:
            {
                "domain": "领域名称",
                "slots": {
                    "槽位名称": {
                        "type": "string|number|boolean|...",
                        "description": "槽位描述",
                        ...
                    },
                    ...
                }
            }
        """
        pass
