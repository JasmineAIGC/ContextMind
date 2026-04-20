"""
Genie Worksheets 独立 Schema 类型

本模块定义 Genie Worksheets 专属的 schema 数据结构，与 PyTOD **完全独立**，
不导入 ``contextmind.modes.pytod`` 的任何代码。

类层次：
    GenieSlot    — 槽位定义（含枚举值、是否必填等）
    GenieIntent  — 意图定义（含策略字段列表）
    GenieSchema  — 服务级 schema（含槽位 + 意图，供 WorksheetLoader / PolicyExecutor 使用）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class GenieSlot:
    """Genie Worksheet 中的槽位定义。"""

    name: str
    description: str = ""
    is_categorical: bool = False
    possible_values: List[str] = field(default_factory=list)
    is_required: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GenieSlot":
        """从字典构造 GenieSlot。"""
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            is_categorical=data.get("is_categorical", False),
            possible_values=data.get("possible_values", []),
            is_required=data.get("is_required", False),
        )

    def to_dict(self) -> Dict[str, Any]:
        """导出为字典。"""
        return {
            "name": self.name,
            "description": self.description,
            "is_categorical": self.is_categorical,
            "possible_values": self.possible_values,
            "is_required": self.is_required,
        }


@dataclass
class GenieIntent:
    """Genie Worksheet 中的意图定义（含策略字段）。"""

    name: str
    description: str = ""
    required_slots: List[str] = field(default_factory=list)
    optional_slots: List[str] = field(default_factory=list)
    result_slots: List[str] = field(default_factory=list)
    is_transactional: bool = False
    # List[PolicyField]；此处声明为 List[Any] 避免循环导入
    policy_fields: List[Any] = field(default_factory=list)


@dataclass
class GenieSchema:
    """Genie Worksheets 服务级 schema（完全独立于 PyTOD）。

    由 ``WorksheetLoader`` 构造，传递给 ``PolicyExecutor`` 和 ``GenieTracker``。
    """

    service_name: str
    description: str = ""
    slots: List[GenieSlot] = field(default_factory=list)
    intents: List[GenieIntent] = field(default_factory=list)

    def get_slot(self, name: str) -> Optional[GenieSlot]:
        """按名称查找槽位。"""
        for slot in self.slots:
            if slot.name == name:
                return slot
        return None

    def get_intent(self, name: str) -> Optional[GenieIntent]:
        """按名称查找意图。"""
        for intent in self.intents:
            if intent.name == name:
                return intent
        return None

    def get_slot_names(self) -> List[str]:
        """返回所有槽位名称列表。"""
        return [s.name for s in self.slots]

    def get_intent_names(self) -> List[str]:
        """返回所有意图名称列表。"""
        return [i.name for i in self.intents]


__all__ = ["GenieSlot", "GenieIntent", "GenieSchema"]
