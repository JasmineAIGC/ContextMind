"""
Prompt Template System - 提示词模板系统（基线版本）

简化的模板系统，不依赖 contextmind 框架。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import re


@dataclass
class TemplateSlot:
    """
    模板槽位定义
    
    Attributes:
        name: 槽位名称
        description: 槽位描述
        default_value: 默认值
        required: 是否必填
        slot_type: 槽位类型 (intent/context/topic)
    """
    name: str
    description: str = ""
    default_value: str = ""
    required: bool = False
    slot_type: str = "intent"


@dataclass
class PromptTemplate:
    """
    提示词模板
    
    支持通过槽位动态填充内容。
    
    Attributes:
        template_id: 模板唯一标识
        name: 模板名称
        template_text: 模板文本（包含槽位占位符）
        slots: 槽位定义列表
        metadata: 模板元数据
    """
    template_id: str
    name: str
    template_text: str
    slots: List[TemplateSlot] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        """初始化后自动提取槽位"""
        if not self.slots:
            self.slots = self._extract_slots_from_template()
    
    def _extract_slots_from_template(self) -> List[TemplateSlot]:
        """从模板文本中自动提取槽位"""
        pattern = r'\{(\w+)\}'
        matches = re.findall(pattern, self.template_text)
        
        # 使用dict保持顺序并去重
        seen = {}
        for slot_name in matches:
            if slot_name not in seen:
                seen[slot_name] = TemplateSlot(
                    name=slot_name,
                    description=f"Auto-extracted slot: {slot_name}",
                    default_value="",
                    required=True
                )
        
        return list(seen.values())
    
    def fill_slots(self, slot_values: Dict[str, str], strict: bool = False) -> str:
        """
        填充模板槽位
        
        Args:
            slot_values: 槽位值字典 {slot_name: value}
            strict: 严格模式，如果有必填槽位未填充则抛出异常
            
        Returns:
            填充后的提示词文本
        """
        # 检查必填槽位
        if strict:
            missing_slots = [
                slot.name for slot in self.slots
                if slot.required and slot.name not in slot_values
            ]
            if missing_slots:
                raise ValueError(f"必填槽位缺失: {missing_slots}")
        
        # 准备最终的槽位值（包含默认值）
        final_values = {}
        for slot in self.slots:
            if slot.name in slot_values:
                value = slot_values[slot.name]
                final_values[slot.name] = str(value) if value is not None else slot.default_value
            else:
                final_values[slot.name] = slot.default_value
        
        # 填充模板
        filled_text = self.template_text
        for slot_name, value in final_values.items():
            placeholder = f"{{{slot_name}}}"
            if placeholder in filled_text:
                filled_text = filled_text.replace(placeholder, value)
        
        return filled_text
    
    def get_slot_names(self) -> List[str]:
        """获取所有槽位名称"""
        return [slot.name for slot in self.slots]


# 默认模板（用于基线实验）
DEFAULT_TEMPLATE = PromptTemplate(
    template_id="baseline_default",
    name="基线默认模板",
    template_text="""## 用户意图
{intent}

## 当前话题
{topic}

## 对话上下文
{context}

请基于用户意图和上下文信息，生成简洁准确的回复。""",
    slots=[
        TemplateSlot(
            name="intent",
            description="从对话历史中提取的用户意图",
            default_value="一般对话",
            required=False,
            slot_type="intent"
        ),
        TemplateSlot(
            name="topic",
            description="当前对话的主题",
            default_value="未识别",
            required=False,
            slot_type="topic"
        ),
        TemplateSlot(
            name="context",
            description="对话上下文摘要",
            default_value="暂无",
            required=False,
            slot_type="context"
        ),
    ],
    metadata={
        "version": "1.0",
        "description": "基线版本默认模板，用于对比实验"
    }
)


__all__ = [
    'TemplateSlot',
    'PromptTemplate',
    'DEFAULT_TEMPLATE',
]
