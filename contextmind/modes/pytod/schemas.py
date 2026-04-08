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

    def to_sgd_dict(self) -> Dict[str, Any]:
        """导出为标准 SGD 格式字典（不含 is_required，与 SGD 规范对齐）。"""
        return {
            "name": self.name,
            "description": self.description,
            "is_categorical": self.is_categorical,
            "possible_values": self.possible_values,
        }


@dataclass
class IntentDefinition:
    """对应 PyTOD schema 中的 intent 对象。"""

    name: str
    description: str
    required_slots: List[str] = field(default_factory=list)
    optional_slots: List[str] = field(default_factory=list)
    result_slots: List[str] = field(default_factory=list)
    is_transactional: bool = False

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
        """从字典构造 IntentDefinition。

        支持两种 optional_slots 格式：
        - SGD 原始格式：dict {slot_name: default_value}
        - 内部列表格式：list [slot_name, ...]
        """
        raw_optional = data.get("optional_slots", [])
        if isinstance(raw_optional, dict):
            optional_slots: List[str] = list(raw_optional.keys())
        else:
            optional_slots = list(raw_optional)
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            required_slots=data.get("required_slots", []),
            optional_slots=optional_slots,
            result_slots=data.get("result_slots", []),
            is_transactional=data.get("is_transactional", False),
        )

    def to_dict(self) -> Dict[str, Any]:
        """导出为内部字典格式（可序列化为 JSON）。"""
        return {
            "name": self.name,
            "description": self.description,
            "is_transactional": self.is_transactional,
            "required_slots": self.required_slots,
            "optional_slots": self.optional_slots,
            "result_slots": self.result_slots,
        }

    def to_sgd_dict(self) -> Dict[str, Any]:
        """导出为标准 SGD 格式字典。

        与 to_dict() 的区别：optional_slots 输出为 dict {slot_name: ""}
        （SGD 规范要求），而非 list。

        使用场景：
        - 需要输出标准 SGD schema.json 时使用本方法
        - 需要保持内部 list 格式时使用 to_dict()
        """
        return {
            "name": self.name,
            "description": self.description,
            "is_transactional": self.is_transactional,
            "required_slots": self.required_slots,
            "optional_slots": {s: "" for s in self.optional_slots},
            "result_slots": self.result_slots,
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

    def to_sgd_dict(self) -> Dict[str, Any]:
        """导出为标准 SGD 格式字典。

        与 to_dict() 的区别：
        - slots 使用 to_sgd_dict()（不含 is_required）
        - intents 使用 to_sgd_dict()（optional_slots 为 dict 格式）
        输出可直接嵌入 SGD schema.json 的服务条目列表中。
        """
        return {
            "service_name": self.service_name,
            "description": self.description,
            "slots": [s.to_sgd_dict() for s in self.slots],
            "intents": [i.to_sgd_dict() for i in self.intents],
        }

    def to_sgd_json(self, indent: int = 2) -> str:
        """导出为 SGD 格式 JSON 字符串（顶层为数组，符合 schema.json 规范）。

        SGD 的 schema.json 即使只有一个服务，也必须使用 JSON 数组格式：
        ``[{"service_name": "...", ...}]``。这一约定来自 SGD 官方数据集规范，
        允许一个 schema 文件中包含多个服务定义（训练集包含 26 个服务）。
        """
        return json.dumps([self.to_sgd_dict()], ensure_ascii=False, indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> "ServiceSchema":
        """从 JSON 字符串构造 ServiceSchema。"""
        return cls.from_dict(json.loads(json_str))

    def to_json(self, indent: int = 2) -> str:
        """导出为 JSON 字符串。"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def merge(self, other: "ServiceSchema") -> "ServiceSchema":
        """将另一个 ServiceSchema 合并到本 schema，返回合并后的新实例。

        合并规则：
        - ``service_name`` / ``description``：若 ``other`` 的字段非空则覆盖。
        - slots：同名槽位以 ``other`` 的定义为准；``other`` 中新增的槽位追加到末尾。
        - intents：同名意图以 ``other`` 的定义为准；``other`` 中新增的意图追加到末尾。

        示例::

            base = pipeline.schema           # 代码内置默认 schema
            patch = ServiceSchema.from_json(open("data/anyihua_schema.json").read())
            pipeline.schema = base.merge(patch)  # patch 中的字段覆盖默认值
        """
        merged_service_name = other.service_name or self.service_name
        merged_description = other.description or self.description

        # 合并槽位：以 self 为基础，other 中同名者覆盖，其余追加
        slot_map: Dict[str, SlotDefinition] = {s.name: s for s in self.slots}
        for slot in other.slots:
            slot_map[slot.name] = slot
        merged_slots = list(slot_map.values())

        # 合并意图：同规则
        intent_map: Dict[str, IntentDefinition] = {i.name: i for i in self.intents}
        for intent in other.intents:
            intent_map[intent.name] = intent
        merged_intents = list(intent_map.values())

        return ServiceSchema(
            service_name=merged_service_name,
            description=merged_description,
            slots=merged_slots,
            intents=merged_intents,
        )


def load_schema_from_dict(data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> ServiceSchema:
    """
    从字典加载 ServiceSchema（便捷函数）。

    当传入列表时（标准 SGD schema.json 格式，或 LLM 将 schema 拆分为多个服务对象的情况），
    将所有服务条目合并为一个 ServiceSchema：
    - service_name / description 取第一个条目
    - slots / intents 跨所有条目合并，同名条目以后出现的定义为准

    Args:
        data: service 定义字典，或包含一个或多个 service 字典的列表

    Raises:
        ValueError: 传入列表为空时抛出
    """
    if isinstance(data, list):
        if not data:
            raise ValueError("Schema 列表为空，至少需要一个 service 定义")
        schema = ServiceSchema.from_dict(data[0])
        for item in data[1:]:
            schema = schema.merge(ServiceSchema.from_dict(item))
        return schema
    return ServiceSchema.from_dict(data)
