"""
安逸花外呼 · 任务三（Schema Extraction）· 部分字段 SGD Schema 定义

定义从安逸花外呼对话中提取的 Schema 数据结构。

设计原则：
    · 格式参考 SGD（Schema-Guided Dialogue）标准，但允许部分字段缺失：
      由于安逸花外呼数据中某些字段可能无法提取，所有非核心字段均为可选。
    · 仅 ServiceSchema.service_name 和 SlotDefinition.name /
      IntentDefinition.name 为必填项，其余字段均可为 None / 空。
    · 提供与 https://github.com/google/langextract 库的互操作接口：
      to_langextract_examples() 将标注好的 SGD 对话转换为 langextract
      ExampleData-兼容字典列表，供直接序列化后传入 lx.extract()。

典型使用::

    from contextmind.scenarios.anyihua.schema_extraction import (
        PartialServiceSchema, PartialSlot, PartialIntent,
        to_langextract_examples,
    )

    schema = PartialServiceSchema(
        service_name="AnYiHua_1",
        description="安逸花外呼促活服务",
        slots=[
            PartialSlot(name="customer_name", description="客户姓名"),
            PartialSlot(name="available_credit"),        # description 可缺失
        ],
        intents=[
            PartialIntent(name="verify_identity"),       # 其余字段可缺失
        ],
    )
    schema_dict = schema.to_sgd_dict()   # 序列化，跳过 None 字段
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# --------------------------------------------------------------------------- #
# 部分字段 SGD Schema 数据类
# --------------------------------------------------------------------------- #


@dataclass
class PartialSlot:
    """
    SGD 槽位定义（允许部分字段缺失）。

    仅 ``name`` 为必填项；其余字段若在安逸花数据中无法提取，可保留为 None。
    序列化时（to_sgd_dict / to_langextract_dict）将跳过值为 None 的字段。

    属性:
        name:            槽位名称（必填）
        description:     槽位描述（可选）
        is_categorical:  是否为分类槽位（可选；None 表示未知）
        possible_values: 可选值列表（可选；None 表示未确定）
    """

    name: str
    description: Optional[str] = None
    is_categorical: Optional[bool] = None
    possible_values: Optional[List[str]] = None

    def to_sgd_dict(self) -> Dict[str, Any]:
        """序列化为 SGD 格式字典，跳过值为 None 的可选字段。"""
        d: Dict[str, Any] = {"name": self.name}
        if self.description is not None:
            d["description"] = self.description
        if self.is_categorical is not None:
            d["is_categorical"] = self.is_categorical
        if self.possible_values is not None:
            d["possible_values"] = self.possible_values
        return d

    @classmethod
    def from_sgd_dict(cls, data: Dict[str, Any]) -> "PartialSlot":
        """从 SGD 格式字典反序列化（允许字段缺失）。"""
        return cls(
            name=data["name"],
            description=data.get("description"),
            is_categorical=data.get("is_categorical"),
            possible_values=data.get("possible_values"),
        )


@dataclass
class PartialIntent:
    """
    SGD 意图定义（允许部分字段缺失）。

    仅 ``name`` 为必填项；其余字段若在安逸花数据中无法提取，可保留为 None。
    ``optional_slots`` 在标准 SGD 中可能为 dict（slot → default value）或 list，
    此处统一为 ``Optional[List[str]]`` 以简化处理。

    属性:
        name:             意图名称（必填）
        description:      意图描述（可选）
        is_transactional: 是否为事务性意图（可选；None 表示未知）
        required_slots:   必填槽位列表（可选；None 表示未确定）
        optional_slots:   可选槽位列表（可选；None 表示未确定）
        result_slots:     结果槽位列表（可选；None 表示未确定）
    """

    name: str
    description: Optional[str] = None
    is_transactional: Optional[bool] = None
    required_slots: Optional[List[str]] = None
    optional_slots: Optional[List[str]] = None
    result_slots: Optional[List[str]] = None

    def to_sgd_dict(self) -> Dict[str, Any]:
        """序列化为 SGD 格式字典，跳过值为 None 的可选字段。"""
        d: Dict[str, Any] = {"name": self.name}
        if self.description is not None:
            d["description"] = self.description
        if self.is_transactional is not None:
            d["is_transactional"] = self.is_transactional
        if self.required_slots is not None:
            d["required_slots"] = self.required_slots
        if self.optional_slots is not None:
            d["optional_slots"] = self.optional_slots
        if self.result_slots is not None:
            d["result_slots"] = self.result_slots
        return d

    @classmethod
    def from_sgd_dict(cls, data: Dict[str, Any]) -> "PartialIntent":
        """从 SGD 格式字典反序列化（允许字段缺失）。"""
        # SGD 标准中 optional_slots 可以是 dict，这里只取 key 列表
        raw_optional = data.get("optional_slots")
        if isinstance(raw_optional, dict):
            optional_slots: Optional[List[str]] = list(raw_optional.keys())
        elif isinstance(raw_optional, list):
            optional_slots = raw_optional
        else:
            optional_slots = None
        return cls(
            name=data["name"],
            description=data.get("description"),
            is_transactional=data.get("is_transactional"),
            required_slots=data.get("required_slots"),
            optional_slots=optional_slots,
            result_slots=data.get("result_slots"),
        )


@dataclass
class PartialServiceSchema:
    """
    SGD 服务 Schema（允许部分字段缺失）。

    仅 ``service_name`` 为必填项；``description``、``slots``、``intents``
    均为可选（可以为空列表或 None）。允许此类字段缺失是为了适应安逸花外呼数据
    中部分字段无法提取或不存在的情况。

    属性:
        service_name: 服务名称（必填）
        description:  服务描述（可选）
        slots:        槽位定义列表（可选；默认空列表）
        intents:      意图定义列表（可选；默认空列表）
    """

    service_name: str
    description: Optional[str] = None
    slots: List[PartialSlot] = field(default_factory=list)
    intents: List[PartialIntent] = field(default_factory=list)

    # ------------------------------------------------------------------ #
    # 序列化 / 反序列化
    # ------------------------------------------------------------------ #

    def to_sgd_dict(self) -> Dict[str, Any]:
        """
        序列化为 SGD 格式字典，跳过值为 None 的可选字段。

        输出可直接嵌入 SGD schema.json 的服务条目列表中。
        """
        d: Dict[str, Any] = {"service_name": self.service_name}
        if self.description is not None:
            d["description"] = self.description
        if self.slots:
            d["slots"] = [s.to_sgd_dict() for s in self.slots]
        if self.intents:
            d["intents"] = [i.to_sgd_dict() for i in self.intents]
        return d

    @classmethod
    def from_sgd_dict(cls, data: Dict[str, Any]) -> "PartialServiceSchema":
        """
        从 SGD 格式字典反序列化（允许字段缺失）。

        兼容以下两种 service_name 键：
        - ``"service_name"``（内部格式）
        - ``"name"``（标准 SGD JSON 格式）
        """
        service_name = data.get("service_name") or data.get("name")
        if not service_name:
            raise ValueError(
                "Schema 字典缺少必填字段 'service_name'（或 'name'）"
            )
        slots = [PartialSlot.from_sgd_dict(s) for s in data.get("slots", [])]
        intents = [PartialIntent.from_sgd_dict(i) for i in data.get("intents", [])]
        return cls(
            service_name=service_name,
            description=data.get("description"),
            slots=slots,
            intents=intents,
        )

    def to_json(self, indent: int = 2) -> str:
        """导出为 JSON 字符串（跳过 None 字段）。"""
        return json.dumps(self.to_sgd_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> "PartialServiceSchema":
        """从 JSON 字符串反序列化。"""
        return cls.from_sgd_dict(json.loads(json_str))

    # ------------------------------------------------------------------ #
    # langextract 互操作
    # ------------------------------------------------------------------ #

    def to_langextract_schema_dict(self) -> Dict[str, Any]:
        """
        将 Schema 转换为 langextract ExampleData-兼容的字典格式。

        返回字典结构（与 langextract ExampleData 对应）：
        ::

            {
                "text": "<schema JSON 文本>",
                "extractions": [
                    {
                        "extraction_class": "slot",
                        "extraction_text": "<槽位名称>",
                        "attributes": {"description": "...", "is_categorical": "..."}
                    },
                    {
                        "extraction_class": "intent",
                        "extraction_text": "<意图名称>",
                        "attributes": {"description": "...", "required_slots": "..."}
                    },
                    ...
                ]
            }

        使用方式（不安装 langextract 时，直接用字典）::

            schema_ex = partial_schema.to_langextract_schema_dict()

        使用方式（安装 langextract 后转换为原生对象）::

            import langextract as lx
            example = lx.data.ExampleData(
                text=schema_ex["text"],
                extractions=[
                    lx.data.Extraction(
                        extraction_class=e["extraction_class"],
                        extraction_text=e["extraction_text"],
                        attributes=e.get("attributes"),
                    )
                    for e in schema_ex["extractions"]
                ],
            )
        """
        extractions = []
        for slot in self.slots:
            attrs: Dict[str, str] = {}
            if slot.description is not None:
                attrs["description"] = slot.description
            if slot.is_categorical is not None:
                attrs["is_categorical"] = str(slot.is_categorical).lower()
            if slot.possible_values is not None:
                attrs["possible_values"] = json.dumps(
                    slot.possible_values, ensure_ascii=False
                )
            extractions.append(
                {
                    "extraction_class": "slot",
                    "extraction_text": slot.name,
                    "attributes": attrs if attrs else None,
                }
            )

        for intent in self.intents:
            attrs = {}
            if intent.description is not None:
                attrs["description"] = intent.description
            if intent.is_transactional is not None:
                attrs["is_transactional"] = str(intent.is_transactional).lower()
            if intent.required_slots is not None:
                attrs["required_slots"] = json.dumps(
                    intent.required_slots, ensure_ascii=False
                )
            if intent.optional_slots is not None:
                attrs["optional_slots"] = json.dumps(
                    intent.optional_slots, ensure_ascii=False
                )
            if intent.result_slots is not None:
                attrs["result_slots"] = json.dumps(
                    intent.result_slots, ensure_ascii=False
                )
            extractions.append(
                {
                    "extraction_class": "intent",
                    "extraction_text": intent.name,
                    "attributes": attrs if attrs else None,
                }
            )

        return {
            "text": self.to_json(),
            "extractions": extractions,
        }

    def get_slot(self, name: str) -> Optional[PartialSlot]:
        """按名称查找槽位定义。"""
        for slot in self.slots:
            if slot.name == name:
                return slot
        return None

    def get_intent(self, name: str) -> Optional[PartialIntent]:
        """按名称查找意图定义。"""
        for intent in self.intents:
            if intent.name == name:
                return intent
        return None
