"""
PyTOD Schema 数据模型

定义 PyTOD 风格的 schema 数据结构：Service / Intent / Slot。
不依赖 PyTOD 官方代码，仅保留 schema 格式定义。

PyTOD schema 标准参考:
    https://github.com/google-research/schema-guided-dialogue

数据结构层次:
    ServiceSchema
    ├── slots: List[SlotDefinition]
    └── intents: List[IntentDefinition]
              └── required_slots / optional_slots (引用 slot 名称)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class SlotDefinition:
    """
    槽位定义

    对应 PyTOD schema 中的 slot 对象。

    属性:
        name:            槽位名称（唯一标识）
        description:     槽位语义描述，用于 prompt 生成
        is_categorical:  是否为枚举类型槽位
        possible_values: 枚举类型槽位的候选值列表
        is_required:     是否为必填槽位（由 intent 引用时设置）
    """

    name: str
    description: str
    is_categorical: bool = False
    possible_values: List[str] = field(default_factory=list)
    is_required: bool = False

    def to_prompt_text(self) -> str:
        """
        生成适合嵌入 prompt 的槽位说明文本。

        返回:
            单行格式的槽位说明，例如：
            "  - date_time (必填): 预约日期时间 [可选值: 今天, 明天, 后天]"
        """
        required_mark = "必填" if self.is_required else "可选"
        line = f"  - {self.name} ({required_mark}): {self.description}"
        if self.is_categorical and self.possible_values:
            values_str = ", ".join(self.possible_values)
            line += f" [可选值: {values_str}]"
        return line

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SlotDefinition":
        """
        从字典（如 JSON 解析结果）构造 SlotDefinition。

        参数:
            data: 包含 slot 信息的字典，支持 PyTOD 原始格式：
                  {"name": ..., "description": ..., "is_categorical": ...,
                   "possible_values": [...]}

        返回:
            SlotDefinition 实例
        """
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            is_categorical=data.get("is_categorical", False),
            possible_values=data.get("possible_values", []),
            is_required=data.get("is_required", False),
        )

    def to_dict(self) -> Dict[str, Any]:
        """导出为字典（可序列化为 JSON）。"""
        return {
            "name": self.name,
            "description": self.description,
            "is_categorical": self.is_categorical,
            "possible_values": self.possible_values,
            "is_required": self.is_required,
        }


@dataclass
class IntentDefinition:
    """
    意图定义

    对应 PyTOD schema 中的 intent 对象。

    属性:
        name:            意图名称（唯一标识）
        description:     意图语义描述
        required_slots:  该意图的必填槽位名称列表
        optional_slots:  该意图的可选槽位名称列表
    """

    name: str
    description: str
    required_slots: List[str] = field(default_factory=list)
    optional_slots: List[str] = field(default_factory=list)

    def to_prompt_text(self) -> str:
        """
        生成适合嵌入 prompt 的意图说明文本。

        返回:
            多行格式的意图说明
        """
        lines = [f"  - {self.name}: {self.description}"]
        if self.required_slots:
            lines.append(f"    必填槽位: {', '.join(self.required_slots)}")
        if self.optional_slots:
            lines.append(f"    可选槽位: {', '.join(self.optional_slots)}")
        return "\n".join(lines)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IntentDefinition":
        """
        从字典构造 IntentDefinition。

        参数:
            data: 包含 intent 信息的字典，支持 PyTOD 原始格式：
                  {"name": ..., "description": ...,
                   "required_slots": [...], "optional_slots": [...]}

        返回:
            IntentDefinition 实例
        """
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            required_slots=data.get("required_slots", []),
            optional_slots=data.get("optional_slots", []),
        )

    def to_dict(self) -> Dict[str, Any]:
        """导出为字典（可序列化为 JSON）。"""
        return {
            "name": self.name,
            "description": self.description,
            "required_slots": self.required_slots,
            "optional_slots": self.optional_slots,
        }


@dataclass
class ServiceSchema:
    """
    服务 Schema 定义

    对应 PyTOD schema 中的 service 对象，包含该服务的所有
    槽位和意图定义。

    属性:
        service_name: 服务名称（唯一标识）
        description:  服务语义描述
        slots:        槽位定义列表
        intents:      意图定义列表
    """

    service_name: str
    description: str
    slots: List[SlotDefinition] = field(default_factory=list)
    intents: List[IntentDefinition] = field(default_factory=list)

    # ------------------------------------------------------------------ #
    # 查询接口
    # ------------------------------------------------------------------ #

    def get_slot(self, name: str) -> Optional[SlotDefinition]:
        """按名称查找槽位定义。"""
        for slot in self.slots:
            if slot.name == name:
                return slot
        return None

    def get_intent(self, name: str) -> Optional[IntentDefinition]:
        """按名称查找意图定义。"""
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

    # ------------------------------------------------------------------ #
    # Prompt 文本生成
    # ------------------------------------------------------------------ #

    def to_prompt_text(self) -> str:
        """
        将服务 schema 转换为适合嵌入 prompt 的文本块。

        返回:
            格式化的 schema 说明文本，例如：

            ## 服务: RestaurantReservation
            描述: 餐厅预约服务

            ### 意图列表
              - Reserve: 预约餐厅
                必填槽位: restaurant_name, date_time, party_size
                可选槽位: cuisine_type

            ### 槽位列表
              - restaurant_name (必填): 餐厅名称
              - date_time (必填): 预约日期时间
              ...
        """
        lines = [
            f"## 服务: {self.service_name}",
            f"描述: {self.description}",
            "",
            "### 意图列表",
        ]
        for intent in self.intents:
            lines.append(intent.to_prompt_text())

        lines += ["", "### 槽位列表"]
        for slot in self.slots:
            lines.append(slot.to_prompt_text())

        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # 序列化 / 反序列化
    # ------------------------------------------------------------------ #

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServiceSchema":
        """
        从字典构造 ServiceSchema，支持 PyTOD 原始 JSON 格式。

        参数:
            data: PyTOD service 字典，格式示例::

                {
                    "service_name": "RestaurantReservation",
                    "description": "餐厅预约服务",
                    "slots": [...],
                    "intents": [...]
                }

        返回:
            ServiceSchema 实例
        """
        slots = [SlotDefinition.from_dict(s) for s in data.get("slots", [])]
        intents = [IntentDefinition.from_dict(i) for i in data.get("intents", [])]

        # 根据意图引用，标记槽位的 is_required 属性
        required_set: Set[str] = set()
        for intent in intents:
            required_set.update(intent.required_slots)
        for slot in slots:
            if slot.name in required_set:
                slot.is_required = True

        return cls(
            service_name=data.get("service_name", data.get("name", "")),
            description=data.get("description", ""),
            slots=slots,
            intents=intents,
        )

    def to_dict(self) -> Dict[str, Any]:
        """导出为字典（可序列化为 JSON）。"""
        return {
            "service_name": self.service_name,
            "description": self.description,
            "slots": [s.to_dict() for s in self.slots],
            "intents": [i.to_dict() for i in self.intents],
        }

    @classmethod
    def from_json(cls, json_str: str) -> "ServiceSchema":
        """从 JSON 字符串构造 ServiceSchema。"""
        return cls.from_dict(json.loads(json_str))

    def to_json(self, indent: int = 2) -> str:
        """导出为 JSON 字符串。"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


def load_schema_from_dict(data: Dict[str, Any]) -> ServiceSchema:
    """
    从字典加载 ServiceSchema（便捷函数）。

    支持两种格式：
    1. 单个 service 字典：{"service_name": ..., "slots": [...], "intents": [...]}
    2. PyTOD 标准格式列表中的第一个元素（取第一个 service）

    参数:
        data: service 定义字典

    返回:
        ServiceSchema 实例

    示例::

        schema = load_schema_from_dict({
            "service_name": "RestaurantReservation",
            "description": "餐厅预约服务",
            "slots": [
                {"name": "restaurant_name", "description": "餐厅名称", "is_categorical": False},
                {"name": "date_time", "description": "预约时间", "is_categorical": False},
                {"name": "party_size", "description": "就餐人数", "is_categorical": True,
                 "possible_values": ["1", "2", "3", "4", "5", "6+"]},
            ],
            "intents": [
                {"name": "Reserve", "description": "预约餐厅",
                 "required_slots": ["restaurant_name", "date_time", "party_size"],
                 "optional_slots": ["cuisine_type"]},
            ]
        })
    """
    return ServiceSchema.from_dict(data)
