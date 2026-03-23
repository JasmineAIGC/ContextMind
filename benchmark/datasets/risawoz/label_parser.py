"""
RiSAWOZ 标签解析器

用于解析 RiSAWOZ 数据集中的标签格式："意图+领域+槽位+值"
"""

from dataclasses import dataclass
from typing import List, Dict, Optional


@dataclass
class RiSAWOZLabel:
    """
    RiSAWOZ 标签数据结构
    
    Attributes:
        intent: 意图类型（如 "Greeting", "Request", "Inform"）
        domain: 领域（如 "旅游景点", "酒店", "餐厅"）
        slot: 槽位名称（如 "名称", "区域", "价格"）
        value: 槽位值（如 "希尔顿", "苏州"）
    """
    intent: str
    domain: str
    slot: str
    value: str
    
    def has_slot(self) -> bool:
        """检查是否有槽位"""
        return bool(self.slot)
    
    def has_value(self) -> bool:
        """检查是否有值"""
        return bool(self.value)
    
    def to_dict(self) -> Dict[str, str]:
        """转换为字典"""
        return {
            "intent": self.intent,
            "domain": self.domain,
            "slot": self.slot,
            "value": self.value
        }
    
    def __str__(self) -> str:
        """格式化输出"""
        parts = [self.intent, self.domain]
        if self.has_slot():
            parts.append(f"槽位:{self.slot}")
        if self.has_value():
            parts.append(f"值:{self.value}")
        return " - ".join(parts)


class RiSAWOZLabelParser:
    """
    RiSAWOZ 标签解析器
    
    用于解析 "意图+领域+槽位+值" 格式的标签字符串
    
    示例:
        >>> parser = RiSAWOZLabelParser()
        >>> label = parser.parse_label("Inform+酒店+名称+希尔顿")
        >>> print(label.intent)  # "Inform"
        >>> print(label.domain)  # "酒店"
        >>> print(label.slot)    # "名称"
        >>> print(label.value)   # "希尔顿"
    """
    
    @staticmethod
    def parse_label(label_str: str) -> RiSAWOZLabel:
        """
        解析单个标签字符串
        
        Args:
            label_str: 标签字符串，格式为 "意图+领域+槽位+值"
            
        Returns:
            RiSAWOZLabel 对象
            
        Examples:
            >>> label = RiSAWOZLabelParser.parse_label("Greeting+旅游景点++")
            >>> print(label.intent)  # "Greeting"
            >>> print(label.domain)  # "旅游景点"
            >>> print(label.slot)    # ""
            >>> print(label.value)   # ""
            
            >>> label = RiSAWOZLabelParser.parse_label("Inform+酒店+名称+希尔顿")
            >>> print(label.intent)  # "Inform"
            >>> print(label.domain)  # "酒店"
            >>> print(label.slot)    # "名称"
            >>> print(label.value)   # "希尔顿"
        """
        # 使用 + 分隔标签字符串
        parts = label_str.split('+')
        
        # 确保至少有4个部分（不足的补空字符串）
        while len(parts) < 4:
            parts.append("")
        
        return RiSAWOZLabel(
            intent=parts[0],
            domain=parts[1],
            slot=parts[2],
            value=parts[3]
        )
    
    @staticmethod
    def parse_labels(label_strings: List[str]) -> List[RiSAWOZLabel]:
        """
        批量解析标签字符串列表
        
        Args:
            label_strings: 标签字符串列表
            
        Returns:
            RiSAWOZLabel 对象列表
            
        Examples:
            >>> labels = RiSAWOZLabelParser.parse_labels([
            ...     "Greeting+旅游景点++",
            ...     "Request+旅游景点+区域+"
            ... ])
            >>> print(len(labels))  # 2
            >>> print(labels[0].intent)  # "Greeting"
            >>> print(labels[1].slot)    # "区域"
        """
        return [RiSAWOZLabelParser.parse_label(label_str) for label_str in label_strings]
    
    @staticmethod
    def extract_slot_values(labels: List[RiSAWOZLabel]) -> Dict[str, str]:
        """
        从标签列表中提取槽位-值对
        
        Args:
            labels: RiSAWOZLabel 对象列表
            
        Returns:
            槽位-值字典，键为槽位名，值为槽位值
            
        Examples:
            >>> labels = RiSAWOZLabelParser.parse_labels([
            ...     "Request+旅游景点+区域+",
            ...     "Inform+酒店+名称+希尔顿",
            ...     "Inform+酒店+价格+500"
            ... ])
            >>> slots = RiSAWOZLabelParser.extract_slot_values(labels)
            >>> print(slots)  # {"区域": "", "名称": "希尔顿", "价格": "500"}
        """
        slot_values = {}
        for label in labels:
            if label.has_slot():
                slot_values[label.slot] = label.value
        return slot_values
    
    @staticmethod
    def validate_label(label_str: str) -> bool:
        """
        验证标签字符串格式是否正确
        
        Args:
            label_str: 标签字符串
            
        Returns:
            如果格式正确返回 True，否则返回 False
            
        Examples:
            >>> RiSAWOZLabelParser.validate_label("Greeting+旅游景点++")
            True
            >>> RiSAWOZLabelParser.validate_label("InvalidFormat")
            False
        """
        if not label_str:
            return False
        
        parts = label_str.split('+')
        
        # 至少要有意图和领域
        if len(parts) < 2:
            return False
        
        # 第一部分（意图）不能为空
        if not parts[0]:
            return False
        
        return True
