"""
SchemaDataBuilder — 从 schema.json 预生成各算法 companion 数据文件

生成逻辑
--------

PyTOD companion (``*_pytod_apis.py``)
    对 schema 中的每个 intent，生成一个同名 Python 函数。函数：
    - 签名参数 = required_slots + optional_slots（全部带默认值 None）
    - 函数体返回含 result_slots 字段的语义化 mock 数据（不依赖 LLM）
    - 文件可直接被 importlib 加载，函数注册到 ExecutionEngine

    生成样例::

        def verify_identity(account_usage_status=None):
            \"\"\"核实用户身份信息\"\"\"
            return {
                "verified_identity": True,
                "account_usage_status": account_usage_status or "正常",
                "status": "success",
            }

FnCTOD companion (``*_fnctod_domain.json``)
    序列化 FunctionManager.add_domain_from_slots() 所需的 DomainSpec 字典，
    存储为可直接 json.load() 的格式，包含 domain_name / description / slots 等字段。

文件命名规则
------------
给定 ``data/foo_schema.json``：
  - PyTOD companion  → ``data/foo_pytod_apis.py``
  - FnCTOD companion → ``data/foo_fnctod_domain.json``
"""

from __future__ import annotations

import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from contextmind.infra.logger import get_logger
from contextmind.modes.pytod.schemas import IntentDefinition, ServiceSchema, load_schema_from_dict

logger = get_logger(__name__)


class SchemaDataBuilder:
    """从 schema.json 预生成各算法所需的 companion 数据文件。

    Args:
        overwrite: 目标文件已存在时是否覆盖（默认 True）。
    """

    def __init__(self, overwrite: bool = True) -> None:
        self.overwrite = overwrite

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def build_all(self, data_dir: Union[str, Path]) -> List[Path]:
        """处理目录下所有 ``*_schema.json`` 文件，生成全部 companion 文件。

        Args:
            data_dir: 包含 ``*_schema.json`` 文件的目录路径。

        Returns:
            成功写入的文件路径列表。
        """
        data_dir = Path(data_dir)
        if not data_dir.is_dir():
            raise ValueError(f"data_dir 不是有效目录: {data_dir}")

        schema_files = sorted(data_dir.glob("*_schema.json"))
        if not schema_files:
            logger.warning(f"[SchemaDataBuilder] 未在 {data_dir} 找到任何 *_schema.json 文件")
            return []

        written: List[Path] = []
        for schema_path in schema_files:
            logger.info(f"[SchemaDataBuilder] 处理: {schema_path.name}")
            written.extend(self.build_single(schema_path))

        logger.info(
            f"[SchemaDataBuilder] 完成: 处理 {len(schema_files)} 个 schema，写入 {len(written)} 个文件"
        )
        return written

    def build_single(self, schema_path: Union[str, Path]) -> List[Path]:
        """处理单个 schema.json，生成 PyTOD + FnCTOD companion 文件。

        Args:
            schema_path: ``*_schema.json`` 文件路径。

        Returns:
            成功写入的文件路径列表（最多 2 个）。
        """
        schema_path = Path(schema_path)
        written: List[Path] = []

        try:
            with open(schema_path, encoding="utf-8") as fh:
                raw = json.load(fh)
            schema = load_schema_from_dict(raw)
        except Exception as exc:
            logger.error(f"[SchemaDataBuilder] 加载 schema 失败: {schema_path} — {exc}")
            return []

        p = self.build_pytod_apis(schema_path, schema=schema)
        if p:
            written.append(p)

        p = self.build_fnctod_domain(schema_path, schema=schema)
        if p:
            written.append(p)

        return written

    def build_pytod_apis(
        self,
        schema_path: Union[str, Path],
        schema: Optional[ServiceSchema] = None,
    ) -> Optional[Path]:
        """从 schema.json 生成 PyTOD ``*_pytod_apis.py`` companion 文件。

        生成的 Python 文件包含每个 intent 对应的函数定义，函数：
        - 签名参数 = required_slots + optional_slots（全部带默认值 None）
        - 函数体返回含 result_slots 字段及语义化 mock 值的字典

        文件可通过 ``load_pytod_api_module(schema_path)`` 加载，
        返回的函数直接注册到 ExecutionEngine。

        Args:
            schema_path: ``*_schema.json`` 文件路径。
            schema:      已加载的 ServiceSchema（传入可省略重复 IO）。

        Returns:
            写入成功时返回文件路径，否则返回 None。
        """
        schema_path = Path(schema_path)
        out_path = _companion_path(schema_path, "pytod_apis", suffix=".py")

        if out_path.exists() and not self.overwrite:
            logger.debug(f"[SchemaDataBuilder] 跳过已存在文件: {out_path}")
            return None

        if schema is None:
            try:
                with open(schema_path, encoding="utf-8") as fh:
                    schema = load_schema_from_dict(json.load(fh))
            except Exception as exc:
                logger.error(f"[SchemaDataBuilder] 加载 schema 失败: {schema_path} — {exc}")
                return None

        lines: List[str] = [
            '"""',
            f'PyTOD API 函数集合 — 由 {schema_path.name} 生成',
            f'Service: {schema.service_name}',
            f'Generated at: {datetime.now(timezone.utc).isoformat()}',
            '',
            '每个函数对应 schema 中的一个意图（intent），函数签名参数来自',
            'required_slots + optional_slots，返回值包含 result_slots 字段。',
            '这些函数由 SchemaDataBuilder 预生成，运行时通过 load_pytod_api_module()',
            '加载并注册到 ExecutionEngine，供 PyTOD AP 生成的程序调用。',
            '"""',
            '',
            'from __future__ import annotations',
            '',
        ]

        if schema.intents:
            for intent in schema.intents:
                lines.extend(_generate_function_lines(intent))
                lines.append('')
        else:
            # No intents — generate one generic function using all slots
            lines.extend(_generate_generic_function_lines(schema))
            lines.append('')

        # Trailing newline
        source = '\n'.join(lines)

        try:
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write(source)
            logger.info(
                f"[SchemaDataBuilder] 已写入 PyTOD APIs: {out_path} ({len(schema.intents)} 个意图)"
            )
            return out_path
        except Exception as exc:
            logger.error(f"[SchemaDataBuilder] 写入失败: {out_path} — {exc}")
            return None

    def build_fnctod_domain(
        self,
        schema_path: Union[str, Path],
        schema: Optional[ServiceSchema] = None,
    ) -> Optional[Path]:
        """从 schema.json 生成 FnCTOD ``*_fnctod_domain.json`` companion 文件。

        文件格式（可直接被 FunctionManager 重新加载）::

            {
              "_schema_source": "anyihua_schema.json",
              "_generated_at": "...",
              "domain_name": "AnYiHua_OutboundCall",
              "description": "...",
              "slots": {"slot_name": "slot_description", ...},
              "categorical_slots": {"slot_name": ["val1", "val2"], ...},
              "required_slots": ["slot_name", ...]
            }

        Args:
            schema_path: ``*_schema.json`` 文件路径。
            schema:      已加载的 ServiceSchema（传入可省略重复 IO）。

        Returns:
            写入成功时返回文件路径，否则返回 None。
        """
        schema_path = Path(schema_path)
        out_path = _companion_path(schema_path, "fnctod_domain", suffix=".json")

        if out_path.exists() and not self.overwrite:
            logger.debug(f"[SchemaDataBuilder] 跳过已存在文件: {out_path}")
            return None

        if schema is None:
            try:
                with open(schema_path, encoding="utf-8") as fh:
                    schema = load_schema_from_dict(json.load(fh))
            except Exception as exc:
                logger.error(f"[SchemaDataBuilder] 加载 schema 失败: {schema_path} — {exc}")
                return None

        slots: Dict[str, str] = {slot.name: slot.description for slot in schema.slots}
        categorical_slots: Dict[str, List[str]] = {
            slot.name: slot.possible_values
            for slot in schema.slots
            if slot.possible_values
        }
        required_slots: List[str] = [
            slot.name for slot in schema.slots if slot.is_required
        ]

        domain_data: Dict[str, Any] = {
            "_schema_source": schema_path.name,
            "_generated_at": datetime.now(timezone.utc).isoformat(),
            "domain_name": schema.service_name,
            "description": schema.description,
            "slots": slots,
        }
        if categorical_slots:
            domain_data["categorical_slots"] = categorical_slots
        if required_slots:
            domain_data["required_slots"] = required_slots

        try:
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(domain_data, fh, ensure_ascii=False, indent=2)
            logger.info(
                f"[SchemaDataBuilder] 已写入 FnCTOD domain: {out_path} ({len(slots)} 个槽位)"
            )
            return out_path
        except Exception as exc:
            logger.error(f"[SchemaDataBuilder] 写入失败: {out_path} — {exc}")
            return None


# ---------------------------------------------------------------------------
# 内部工具函数
# ---------------------------------------------------------------------------

def _companion_path(schema_path: Path, kind: str, suffix: str = ".json") -> Path:
    """返回 companion 文件路径。

    ``data/foo_schema.json`` → ``data/foo_{kind}{suffix}``
    ``data/myservice.json``  → ``data/myservice_{kind}{suffix}``
    """
    stem = schema_path.stem
    base = stem[: -len("_schema")] if stem.endswith("_schema") else stem
    return schema_path.parent / f"{base}_{kind}{suffix}"


def _mock_value_for_result_slot(slot_name: str, intent: IntentDefinition) -> str:
    """为 result_slot 返回合理的 Python 字面量字符串表示。"""
    name_lower = slot_name.lower()
    intent_lower = intent.name.lower()

    is_confirm_like = any(
        intent_lower.startswith(p)
        for p in ("confirm_", "verify_", "close_", "decline_", "end_", "express_")
    )
    is_complaint_like = any(
        intent_lower.startswith(p)
        for p in ("complain_", "complaint_", "dispute_")
    )
    is_schedule_like = intent_lower.startswith("schedule_")

    if is_confirm_like:
        return "True"
    if is_complaint_like:
        return '"已记录，将在3个工作日内处理"'
    if is_schedule_like:
        if "time" in name_lower or "date" in name_lower:
            return '"明天上午10:00"'
        return "True"

    # Slot-name semantics
    if "status" in name_lower:
        return '"success"'
    if "verified" in name_lower or "confirmed" in name_lower or "declined" in name_lower:
        return "True"
    if "id" in name_lower or "number" in name_lower or "policy" in name_lower:
        return f'"{intent.name.upper()[:8]}-001"'
    if "amount" in name_lower or "quota" in name_lower or "limit" in name_lower:
        return '"5000元"'
    if "time" in name_lower or "date" in name_lower:
        return '"2024-01-15"'
    if "info" in name_lower or "result" in name_lower or "data" in name_lower:
        return f'"[{intent.name} 执行成功]"'
    # Default: intent name + "_completed"
    return f'"{intent.name}_completed"'


def _generate_function_lines(intent: IntentDefinition) -> List[str]:
    """为单个 intent 生成 Python 函数定义行列表。"""
    # Build parameter list: required + optional, all with default None
    params = list(dict.fromkeys(
        list(intent.required_slots) + list(intent.optional_slots)
    ))
    param_str = ", ".join([f"{p}=None" for p in params]) if params else ""

    lines: List[str] = []
    lines.append(f"def {intent.name}({param_str}):")
    # Docstring
    desc = intent.description.replace('"', '\\"') if intent.description else intent.name
    lines.append(f'    """{desc}"""')
    lines.append(f'    return {{')
    # result_slots first (output fields)
    for rs in intent.result_slots:
        val = _mock_value_for_result_slot(rs, intent)
        lines.append(f'        "{rs}": {val},')
    # Echo back non-None input args for business-relevant slots
    for slot in params:
        sl = slot.lower()
        if any(kw in sl for kw in ("amount", "quota", "limit", "date", "id", "number", "name")):
            lines.append(f'        "{slot}": {slot},')
    # Always include status
    lines.append(f'        "status": "success",')
    lines.append(f'    }}')
    return lines


def _generate_generic_function_lines(schema: ServiceSchema) -> List[str]:
    """无意图定义时生成一个以 service_name 命名的通用函数。"""
    slot_names = [s.name for s in schema.slots]
    param_str = ", ".join([f"{p}=None" for p in slot_names]) if slot_names else ""
    lines: List[str] = []
    lines.append(f"def {schema.service_name}({param_str}):")
    desc = schema.description.replace('"', '\\"') if schema.description else schema.service_name
    lines.append(f'    """{desc}"""')
    lines.append(f'    args = {{k: v for k, v in locals().items() if v is not None}}')
    lines.append(f'    return {{"status": "success", **args}}')
    return lines
