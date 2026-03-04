"""
PyTOD Schema 数据模型

定义 PyTOD 风格的 schema 数据结构：ServiceSchema / IntentDefinition / SlotDefinition。
不依赖 PyTOD 官方代码，仅保留 schema 格式定义。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Union


@dataclass
class SlotDefinition:
    """对应 PyTOD schema 中的 slot 对象。"""

    name: str
    description: str
    is_categorical: bool = False
    possible_values: List[str] = field(default_factory=list)
    is_required: bool = False

    def to_prompt_text(self) -> str:
        """生成适合嵌入 prompt 的槽位说明文本。"""
        required_mark = "必填" if self.is_required else "可选"
        line = f"  - {self.name} ({required_mark}): {self.description}"
        if self.is_categorical and self.possible_values:
            values_str = ", ".join(self.possible_values)
            line += f" [可选值: {values_str}]"
        return line

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SlotDefinition":
        """从字典（如 JSON 解析结果）构造 SlotDefinition。"""
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
    """对应 PyTOD schema 中的 intent 对象。"""

    name: str
    description: str
    required_slots: List[str] = field(default_factory=list)
    optional_slots: List[str] = field(default_factory=list)

    def to_prompt_text(self) -> str:
        """生成适合嵌入 prompt 的意图说明文本。"""
        lines = [f"  - {self.name}: {self.description}"]
        if self.required_slots:
            lines.append(f"    必填槽位: {', '.join(self.required_slots)}")
        if self.optional_slots:
            lines.append(f"    可选槽位: {', '.join(self.optional_slots)}")
        return "\n".join(lines)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IntentDefinition":
        """从字典构造 IntentDefinition。"""
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
    """对应 PyTOD schema 中的 service 对象，包含该服务的所有槽位和意图定义。"""

    service_name: str
    description: str
    slots: List[SlotDefinition] = field(default_factory=list)
    intents: List[IntentDefinition] = field(default_factory=list)

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

    def to_prompt_text(self) -> str:
        """将服务 schema 转换为适合嵌入 prompt 的文本块。"""
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

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServiceSchema":
        """从字典构造 ServiceSchema，支持 PyTOD 原始 JSON 格式。"""
        slots = [SlotDefinition.from_dict(s) for s in data.get("slots", [])]
        intents = [IntentDefinition.from_dict(i) for i in data.get("intents", [])]

        # 从意图定义而非槽位定义中推导 is_required，
        # 因为 PyTOD JSON schema 将必填槽位存储在意图下。
        required_set: Set[str] = set()
        for intent in intents:
            required_set.update(intent.required_slots)
        for slot in slots:
            if slot.name in required_set:
                slot.is_required = True

        # 同时支持 "service_name"（内部格式）和 "name"（PyTOD JSON 格式）。
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


def load_schema_from_dict(data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> ServiceSchema:
    """
    从字典加载 ServiceSchema（便捷函数）。

    When passed a list (the standard PyTOD per-dialogue schema format, which
    can contain multiple service entries), only the first service is used.
    Multi-service dialogues should call ServiceSchema.from_dict per service.

    Args:
        data: service 定义字典，或包含多个 service 字典的列表

    Raises:
        ValueError: 传入列表为空时抛出
    """
    if isinstance(data, list):
        if not data:
            raise ValueError("Schema 列表为空，至少需要一个 service 定义")
        data = data[0]
    return ServiceSchema.from_dict(data)
