"""
Genie Worksheets 策略字段数据模型

本模块定义 Genie Worksheets 专用的 schema 数据结构，与 PyTOD 完全独立：

- ``PolicyField``  — Worksheet 中每行字段的策略注解
- ``_parse_bool``  — 多格式布尔解析工具
- ``_parse_list``  — 逗号分隔字符串或列表解析工具
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PolicyField:
    """来自 Genie Worksheets 的字段级策略注解。

    每个 PolicyField 对应 Worksheet 中的一行，描述某个槽位在对话策略层面
    的行为约束（必填性、是否需要确认、是否由系统主动询问、条件依赖等）。

    Attributes:
        name:          对应的槽位名称（与 ``SlotDefinition.name`` 一致）。
        description:   槽位语义描述（注入 LLM 提示词用）。
        required:      是否必填（True = 未填时 EE 阻断 API 调用）。
        confirm:       是否需要用户二次确认（True = EE 触发确认流程后再调用 API）。
        ask_by_system: 是否由系统主动询问（True = 可进入 AgentTracker 主动询问队列）。
        depends_on:    条件依赖字段名；不为 None 时，仅当该字段已填时本字段才生效。
        field_type:    数据类型字符串（"str" / "int" / "float" / "bool" / "enum"）。
        possible_values: 枚举类型的合法值列表（field_type="enum" 时使用）。
        on_success:    填写成功后触发的动作名（如 API 函数名），供 GenieTracker 使用。
    """

    name: str
    description: str = ""
    required: bool = True
    confirm: bool = False
    ask_by_system: bool = True
    depends_on: Optional[str] = None
    field_type: str = "str"
    possible_values: List[str] = field(default_factory=list)
    on_success: str = ""

    def to_prompt_text(self) -> str:
        """生成适合注入 LLM 提示词的字段描述文本。"""
        parts = [f"  - {self.name}"]
        if self.description:
            parts.append(f"({self.description})")
        tags: List[str] = []
        if self.required:
            tags.append("必填")
        if self.confirm:
            tags.append("需确认")
        if self.depends_on:
            tags.append(f"依赖:{self.depends_on}")
        if self.possible_values:
            tags.append(f"可选值:{'/'.join(self.possible_values)}")
        if tags:
            parts.append(f"[{', '.join(tags)}]")
        return " ".join(parts)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PolicyField":
        """从字典构造 PolicyField（兼容 Worksheet JSON/CSV 导入格式）。"""
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            required=_parse_bool(data.get("required", True)),
            confirm=_parse_bool(data.get("confirm", False)),
            ask_by_system=_parse_bool(data.get("ask_by_system", True)),
            depends_on=data.get("depends_on") or None,
            field_type=data.get("type", data.get("field_type", "str")),
            possible_values=_parse_list(data.get("possible_values", [])),
            on_success=data.get("on_success", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        """导出为字典（可序列化为 JSON / CSV 行）。"""
        return {
            "name": self.name,
            "description": self.description,
            "required": self.required,
            "confirm": self.confirm,
            "ask_by_system": self.ask_by_system,
            "depends_on": self.depends_on or "",
            "type": self.field_type,
            "possible_values": self.possible_values,
            "on_success": self.on_success,
        }


def _parse_bool(val: Any) -> bool:
    """将多种格式（bool/str/int）统一解析为 bool。"""
    if isinstance(val, bool):
        return val
    if isinstance(val, int):
        return bool(val)
    if isinstance(val, str):
        return val.strip().lower() in ("true", "yes", "1", "是")
    return bool(val)


def _parse_list(val: Any) -> List[str]:
    """将逗号分隔字符串或列表统一解析为 List[str]。"""
    if isinstance(val, list):
        return [str(v) for v in val if v]
    if isinstance(val, str) and val.strip():
        return [v.strip() for v in val.split(",") if v.strip()]
    return []


__all__ = [
    "PolicyField",
    "_parse_bool",
    "_parse_list",
]
