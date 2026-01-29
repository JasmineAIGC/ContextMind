"""
Template Manager - 模板管理器

管理槽位模板的定义和填充
"""

from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class SlotTemplate:
    """槽位模板定义"""
    
    # 槽位名称
    name: str
    
    # 槽位描述
    description: str
    
    # 默认值
    default_value: str = ""
    
    # 是否必填
    required: bool = False


class TemplateManager:
    """模板管理器 - 管理预定义的槽位模板"""
    
    def __init__(self):
        """初始化模板管理器"""
        # 定义标准槽位模板
        self.slots = {
            "user_intent": SlotTemplate(
                name="user_intent",
                description="用户当前意图（从对话历史中提取）",
                default_value="用户正在进行日常对话",
                required=True
            ),
            "conversation_context": SlotTemplate(
                name="conversation_context",
                description="对话上下文摘要（最近几轮对话的简要总结）",
                default_value="暂无对话历史",
                required=False
            ),
            "key_info": SlotTemplate(
                name="key_info",
                description="关键信息（用户提到的重要实体、偏好等）",
                default_value="暂无关键信息",
                required=False
            ),
        }
        
        self.slot_values: Dict[str, str] = {}
    
    def get_slot(self, slot_name: str) -> Optional[SlotTemplate]:
        """获取槽位定义"""
        return self.slots.get(slot_name)
    
    def set_slot_value(self, slot_name: str, value: str) -> None:
        """设置槽位值"""
        if slot_name in self.slots:
            self.slot_values[slot_name] = value
    
    def get_slot_value(self, slot_name: str) -> str:
        """获取槽位值（如果未设置则返回默认值）"""
        slot = self.slots.get(slot_name)
        if not slot:
            return ""
        
        return self.slot_values.get(slot_name, slot.default_value)
    
    def fill_template(self, template: str) -> str:
        """填充模板
        
        Args:
            template: 包含槽位占位符的模板字符串，例如：
                     "用户意图：{slot_user_intent}\n上下文：{slot_conversation_context}"
        
        Returns:
            填充后的字符串
        """
        result = template
        
        for slot_name, slot_def in self.slots.items():
            placeholder = f"{{slot_{slot_name}}}"
            value = self.get_slot_value(slot_name)
            result = result.replace(placeholder, value)
        
        return result
    
    def get_all_slot_values(self) -> Dict[str, str]:
        """获取所有槽位值"""
        return {
            name: self.get_slot_value(name)
            for name in self.slots.keys()
        }
    
    def clear(self) -> None:
        """清空所有槽位值"""
        self.slot_values.clear()
