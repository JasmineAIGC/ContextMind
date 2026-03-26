"""
SchemaDataBuilder — 从 schema.json 预生成各算法 companion 数据文件

生成逻辑
--------

PyTOD companion (``*_pytod_mock.json``)
    对每个 intent，根据其 ``result_slots``、``required_slots``、``optional_slots``
    和意图名语义自动生成合理的 mock 返回值。生成规则优先级：
    1. 布尔类意图（confirm_/verify_/close_/decline_）→ ``{result_slot: True}``
    2. 投诉/回调意图 → 固定操作确认文本
    3. 其余意图 → 根据 result_slot 名称语义填充合理占位值

FnCTOD companion (``*_fnctod_domain.json``)
    序列化 FunctionManager.add_domain_from_slots() 生成的 DomainSpec，
    存储为可直接 json.load() 的字典，包含 domain_name / description / slots 等字段。

文件命名规则
------------
给定 ``data/foo_schema.json``：
  - PyTOD companion  → ``data/foo_pytod_mock.json``
  - FnCTOD companion → ``data/foo_fnctod_domain.json``

若 schema 文件名不含 ``_schema`` 后缀（如 ``myservice.json``），
则生成 ``myservice_pytod_mock.json`` / ``myservice_fnctod_domain.json``。
"""

from __future__ import annotations

import json
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

        p = self.build_pytod_mock(schema_path, schema=schema)
        if p:
            written.append(p)

        p = self.build_fnctod_domain(schema_path, schema=schema)
        if p:
            written.append(p)

        return written

    def build_pytod_mock(
        self,
        schema_path: Union[str, Path],
        schema: Optional[ServiceSchema] = None,
    ) -> Optional[Path]:
        """从 schema.json 生成 PyTOD ``*_pytod_mock.json`` companion 文件。

        文件格式::

            {
              "_schema_source": "anyihua_schema.json",
              "_generated_at": "2024-01-01T00:00:00+00:00",
              "intent_name": {
                "result_slot_1": "mock_value",
                ...
              },
              ...
            }

        Args:
            schema_path: ``*_schema.json`` 文件路径。
            schema:      已加载的 ServiceSchema（传入可省略重复 IO）。

        Returns:
            写入成功时返回文件路径，否则返回 None。
        """
        schema_path = Path(schema_path)
        out_path = _companion_path(schema_path, "pytod_mock")

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

        mock: Dict[str, Any] = {
            "_schema_source": schema_path.name,
            "_generated_at": datetime.now(timezone.utc).isoformat(),
        }

        for intent in schema.intents:
            mock[intent.name] = _generate_intent_mock(intent)

        try:
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(mock, fh, ensure_ascii=False, indent=2)
            logger.info(
                f"[SchemaDataBuilder] 已写入 PyTOD mock: {out_path} ({len(schema.intents)} 个意图)"
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
        out_path = _companion_path(schema_path, "fnctod_domain")

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

def _companion_path(schema_path: Path, suffix: str) -> Path:
    """返回 companion 文件路径。

    ``data/foo_schema.json`` → ``data/foo_{suffix}.json``
    ``data/myservice.json``  → ``data/myservice_{suffix}.json``
    """
    stem = schema_path.stem
    base = stem[: -len("_schema")] if stem.endswith("_schema") else stem
    return schema_path.parent / f"{base}_{suffix}.json"


def _generate_intent_mock(intent: IntentDefinition) -> Dict[str, Any]:
    """为单个 intent 生成合理的 mock 返回值。

    生成规则（按优先级）：
    1. 布尔类意图（名称以 confirm_/verify_/close_/decline_/end_ 开头）
       → result_slot = True
    2. 投诉/回调/建议类意图（complain_/schedule_/suggest_）
       → result_slot = 动作确认文本
    3. 所有 result_slots 均映射到语义化占位值，
       同时把 required_slots + optional_slots 中有业务语义的字段也加入返回，
       让 AP 在 ``say(xN.field)`` 时能引用到实际值。
    """
    mock: Dict[str, Any] = {}

    name_lower = intent.name.lower()
    is_confirm_like = any(
        name_lower.startswith(p)
        for p in ("confirm_", "verify_", "close_", "decline_", "end_", "express_")
    )
    is_complaint_like = any(
        name_lower.startswith(p)
        for p in ("complain_", "complaint_", "dispute_")
    )
    is_schedule_like = name_lower.startswith("schedule_")
    is_suggest_like = name_lower.startswith("suggest_")
    is_inform_like = name_lower.startswith("inform_")
    is_inquire_like = any(
        name_lower.startswith(p)
        for p in ("inquire_", "query_", "search_", "get_", "track_")
    )
    is_close_sale = "close_sale" in name_lower or "sale_completed" in name_lower

    # ---- result_slots (output fields) ----
    for rs in intent.result_slots:
        rs_lower = rs.lower()
        if is_confirm_like:
            mock[rs] = True
        elif is_complaint_like:
            mock[rs] = "已记录，将在3个工作日内处理"
        elif is_schedule_like:
            if "time" in rs_lower or "date" in rs_lower:
                mock[rs] = "明天上午10:00"
            else:
                mock[rs] = True
        elif is_suggest_like:
            mock[rs] = True
        elif is_inform_like:
            mock[rs] = True
        elif is_close_sale:
            if "number" in rs_lower or "id" in rs_lower or "policy" in rs_lower:
                mock[rs] = "POL-20240101-001"
            else:
                mock[rs] = True
        elif "status" in rs_lower:
            mock[rs] = "success"
        elif "id" in rs_lower:
            mock[rs] = f"{intent.name.upper()[:8]}-001"
        elif "amount" in rs_lower or "quota" in rs_lower or "limit" in rs_lower:
            mock[rs] = "5000元"
        elif "time" in rs_lower or "date" in rs_lower:
            mock[rs] = "2024-01-15"
        elif "info" in rs_lower or "result" in rs_lower:
            mock[rs] = f"[{intent.name} 执行成功]"
        elif "verified" in rs_lower or "confirmed" in rs_lower:
            mock[rs] = True
        else:
            mock[rs] = f"{intent.name}_completed"

    # ---- required/optional slots that carry business-relevant data ----
    # These are *input* parameters that the caller passes in; echo them back
    # so AP can reference them via say(xN.slot_name) for DM context.
    # Only add if not already in mock (result_slots take precedence).
    for slot in list(intent.required_slots) + list(intent.optional_slots):
        if slot in mock:
            continue
        slot_lower = slot.lower()
        if "amount" in slot_lower or "quota" in slot_lower or "limit" in slot_lower:
            mock[slot] = "5000"
        elif "date" in slot_lower:
            mock[slot] = "2024-01-15"
        elif "status" in slot_lower:
            mock[slot] = "正常"
        elif "id" in slot_lower or "number" in slot_lower:
            mock[slot] = f"ID-{intent.name[:6].upper()}"
        # Skip generic slot names that would add noise without value

    # Always include a status marker
    mock.setdefault("status", "success")

    return mock
