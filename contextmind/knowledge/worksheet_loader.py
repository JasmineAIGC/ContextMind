"""
WorksheetLoader — Genie Worksheets ↔ ContextMind ServiceSchema 格式转换器

将 Genie Worksheets 格式（CSV / JSON）的业务策略定义导入 ContextMind 的
``ServiceSchema``，并支持反向导出（``ServiceSchema`` → Worksheet CSV）。

Genie Worksheet 的每行（Field）对应一个槽位的策略注解，字段如下：

  name          槽位名称
  description   槽位语义描述
  type          数据类型（str / int / float / bool / enum）
  required      是否必填（true/false）
  confirm       是否需要二次确认（true/false）
  ask_by_system 是否由系统主动询问（true/false）
  depends_on    条件依赖字段名（空 = 无条件）
  possible_values 枚举值（逗号分隔，type=enum 时使用）
  on_success    填写成功后触发的动作名

CSV 示例（两个 Intent 的 Worksheet，以 # intent_name 分节）::

  # search_restaurant
  name,type,description,required,confirm,ask_by_system,possible_values,on_success
  cuisine,enum,菜系类型,true,false,true,"川菜,粤菜,日料",
  location,str,餐厅位置,true,false,true,,
  party_size,int,就餐人数,false,false,true,,

  # book_restaurant
  name,type,description,required,confirm,ask_by_system,possible_values,on_success
  restaurant_name,str,餐厅名称,true,false,true,,
  date_time,str,预订时间,true,true,true,,book_restaurant_api
  contact_phone,str,联系电话,true,false,true,,

JSON 示例::

  {
    "service_name": "餐厅服务",
    "description": "中文餐厅预订系统",
    "intents": [
      {
        "name": "search_restaurant",
        "description": "搜索餐厅",
        "policy_fields": [
          {"name": "cuisine", "type": "enum", "description": "菜系",
           "required": true, "confirm": false, "ask_by_system": true,
           "possible_values": ["川菜", "粤菜", "日料"]}
        ]
      }
    ]
  }

用法::

    from contextmind.knowledge.worksheet_loader import WorksheetLoader

    # 从 CSV 加载
    schema = WorksheetLoader.from_csv("worksheets/restaurant.csv",
                                      service_name="餐厅服务")

    # 从 JSON 加载（完整 Worksheet JSON）
    schema = WorksheetLoader.from_json("worksheets/restaurant_worksheet.json")

    # 从已有 ServiceSchema 反向导出为 Worksheet CSV（方便人工编辑策略）
    csv_text = WorksheetLoader.to_csv(schema)
    with open("export.csv", "w") as f:
        f.write(csv_text)
"""

from __future__ import annotations

import csv
import io
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from contextmind.modes.pytod.schemas import (
    IntentDefinition,
    PolicyField,
    ServiceSchema,
    SlotDefinition,
    _parse_bool,
    _parse_list,
)

logger = logging.getLogger(__name__)

# CSV 列定义（标准 Genie Worksheet 列顺序）
_WORKSHEET_COLUMNS = [
    "name",
    "type",
    "description",
    "required",
    "confirm",
    "ask_by_system",
    "depends_on",
    "possible_values",
    "on_success",
]


class WorksheetLoader:
    """Genie Worksheets 格式导入/导出工具。

    所有方法均为类方法，无需实例化。
    """

    # ------------------------------------------------------------------
    # 导入：Worksheet → ServiceSchema
    # ------------------------------------------------------------------

    @classmethod
    def from_csv(
        cls,
        path: Union[str, Path],
        service_name: str = "",
        service_description: str = "",
        encoding: str = "utf-8",
    ) -> ServiceSchema:
        """从 CSV 文件加载 Worksheet，返回 ``ServiceSchema``。

        CSV 文件格式说明：
        - 以 ``# intent_name`` 开头的行表示新 Intent 节的开始
        - 紧随其后的一行为列标题（可选，若缺失则使用 _WORKSHEET_COLUMNS 默认顺序）
        - 其余行为字段数据行

        Args:
            path:               CSV 文件路径。
            service_name:       服务名称（覆盖文件内 # service: 行）。
            service_description: 服务描述（覆盖文件内 # description: 行）。
            encoding:           文件编码（默认 utf-8）。

        Returns:
            包含 policy_fields 的 ``ServiceSchema``。
        """
        text = Path(path).read_text(encoding=encoding)
        return cls.from_csv_string(
            text,
            service_name=service_name,
            service_description=service_description,
        )

    @classmethod
    def from_csv_string(
        cls,
        text: str,
        service_name: str = "",
        service_description: str = "",
    ) -> ServiceSchema:
        """从 CSV 文本字符串加载 Worksheet，返回 ``ServiceSchema``。"""
        intents: List[IntentDefinition] = []
        all_slots: Dict[str, SlotDefinition] = {}  # 全局槽位去重

        current_intent_name: Optional[str] = None
        current_intent_desc: str = ""
        current_fields: List[PolicyField] = []
        header: Optional[List[str]] = None

        _svc_name = service_name
        _svc_desc = service_description

        def _flush_intent() -> None:
            """将当前 intent 缓冲区写入 intents 列表。"""
            nonlocal current_intent_name, current_intent_desc, current_fields, header
            if current_intent_name is None:
                return
            # 从 policy_fields 推导 required_slots / optional_slots
            required = [pf.name for pf in current_fields if pf.required]
            optional = [pf.name for pf in current_fields if not pf.required]
            intents.append(IntentDefinition(
                name=current_intent_name,
                description=current_intent_desc,
                required_slots=required,
                optional_slots=optional,
                policy_fields=list(current_fields),
            ))
            current_intent_name = None
            current_intent_desc = ""
            current_fields = []
            header = None

        lines = text.splitlines()
        i = 0
        while i < len(lines):
            raw = lines[i].strip()
            i += 1

            if not raw:
                continue

            # 元信息注释行
            if raw.startswith("#"):
                comment_body = raw[1:].strip()
                if comment_body.lower().startswith("service:"):
                    if not _svc_name:
                        _svc_name = comment_body[len("service:"):].strip()
                elif comment_body.lower().startswith("description:"):
                    if not _svc_desc:
                        _svc_desc = comment_body[len("description:"):].strip()
                else:
                    # Intent 节开始
                    _flush_intent()
                    # 格式: "# intent_name  描述文字"（空格分隔，第一个单词为名称）
                    parts = comment_body.split(None, 1)
                    current_intent_name = parts[0]
                    current_intent_desc = parts[1] if len(parts) > 1 else ""
                continue

            # 当前不在任何 Intent 节内时，跳过数据行
            if current_intent_name is None:
                continue

            # 尝试解析为 CSV 行
            reader = csv.reader([raw])
            row = next(reader, [])
            if not row:
                continue

            # 若 header 尚未设置，检查是否为标题行（首列为 "name"）
            if header is None:
                if row[0].strip().lower() == "name":
                    header = [c.strip().lower() for c in row]
                    continue
                else:
                    # 无标题行，使用默认列顺序
                    header = _WORKSHEET_COLUMNS

            # 解析字段行
            row_dict: Dict[str, str] = {}
            for j, col in enumerate(header):
                row_dict[col] = row[j].strip() if j < len(row) else ""

            if not row_dict.get("name"):
                continue  # 跳过空行

            pf = PolicyField.from_dict(row_dict)
            current_fields.append(pf)

            # 同步更新全局槽位表（供 ServiceSchema.slots 使用）
            slot_name = pf.name
            if slot_name not in all_slots:
                all_slots[slot_name] = SlotDefinition(
                    name=slot_name,
                    description=pf.description,
                    is_categorical=(pf.field_type == "enum"),
                    possible_values=pf.possible_values,
                    is_required=pf.required,
                )

        _flush_intent()

        schema = ServiceSchema(
            service_name=_svc_name or "WorksheetService",
            description=_svc_desc,
            slots=list(all_slots.values()),
            intents=intents,
        )
        logger.info(
            f"[WorksheetLoader] 从 CSV 加载完成: service={schema.service_name!r}, "
            f"意图数={len(intents)}, 槽位数={len(all_slots)}"
        )
        return schema

    @classmethod
    def from_json(
        cls,
        path: Union[str, Path],
        encoding: str = "utf-8",
    ) -> ServiceSchema:
        """从 Worksheet JSON 文件加载，返回 ``ServiceSchema``。

        支持两种 JSON 格式：
        1. 完整 Worksheet JSON（含 service_name、description、intents）
        2. 仅含字段列表的单 Intent JSON：``[{"name": "...", ...}, ...]``

        Args:
            path:     JSON 文件路径。
            encoding: 文件编码。

        Returns:
            ``ServiceSchema``。
        """
        data = json.loads(Path(path).read_text(encoding=encoding))
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> ServiceSchema:
        """从字典或字段列表加载 Worksheet，返回 ``ServiceSchema``。

        Args:
            data: Worksheet 字典（含 service_name / intents），或 PolicyField 字典列表。

        Returns:
            ``ServiceSchema``。
        """
        if isinstance(data, list):
            # 单 Intent：字段列表格式
            fields = [PolicyField.from_dict(d) for d in data]
            return cls._fields_to_schema(fields, service_name="WorksheetService")

        # 完整 Worksheet JSON
        service_name = data.get("service_name", data.get("name", "WorksheetService"))
        service_description = data.get("description", "")

        intents: List[IntentDefinition] = []
        all_slots: Dict[str, SlotDefinition] = {}

        raw_intents = data.get("intents", [])
        if not raw_intents and "policy_fields" in data:
            # 顶层直接有 policy_fields（单意图简写格式）
            raw_intents = [{"name": service_name, "policy_fields": data["policy_fields"]}]

        for raw_intent in raw_intents:
            raw_pf = raw_intent.get("policy_fields", [])
            fields = [PolicyField.from_dict(pf) for pf in raw_pf]
            required = [f.name for f in fields if f.required]
            optional = [f.name for f in fields if not f.required]
            intents.append(IntentDefinition(
                name=raw_intent.get("name", "default_intent"),
                description=raw_intent.get("description", ""),
                required_slots=required,
                optional_slots=optional,
                result_slots=raw_intent.get("result_slots", []),
                is_transactional=raw_intent.get("is_transactional", False),
                policy_fields=fields,
            ))
            for pf in fields:
                if pf.name not in all_slots:
                    all_slots[pf.name] = SlotDefinition(
                        name=pf.name,
                        description=pf.description,
                        is_categorical=(pf.field_type == "enum"),
                        possible_values=pf.possible_values,
                        is_required=pf.required,
                    )

        # 若 JSON 中还有顶层 slots 定义，与 policy_fields 推导的槽位合并
        for raw_slot in data.get("slots", []):
            slot = SlotDefinition.from_dict(raw_slot)
            if slot.name not in all_slots:
                all_slots[slot.name] = slot

        schema = ServiceSchema(
            service_name=service_name,
            description=service_description,
            slots=list(all_slots.values()),
            intents=intents,
        )
        logger.info(
            f"[WorksheetLoader] 从 JSON 加载完成: service={schema.service_name!r}, "
            f"意图数={len(intents)}, 槽位数={len(all_slots)}"
        )
        return schema

    # ------------------------------------------------------------------
    # 导出：ServiceSchema → Worksheet CSV
    # ------------------------------------------------------------------

    @classmethod
    def to_csv(cls, schema: ServiceSchema, encoding: str = "utf-8") -> str:
        """将 ``ServiceSchema`` 导出为 Worksheet CSV 文本。

        每个意图生成一个 ``# intent_name`` 节，包含该意图的所有策略字段。
        若意图无 policy_fields，则从 required_slots / optional_slots 自动推导。

        Args:
            schema:   要导出的 ServiceSchema。
            encoding: 目标编码（仅影响注释，CSV 本身为 unicode）。

        Returns:
            UTF-8 CSV 文本字符串。
        """
        lines: List[str] = []

        lines.append(f"# service: {schema.service_name}")
        if schema.description:
            lines.append(f"# description: {schema.description}")
        lines.append("")

        for intent in schema.intents:
            lines.append(f"# {intent.name}  {intent.description}")
            # 列标题
            lines.append(",".join(_WORKSHEET_COLUMNS))

            pf_list = intent.policy_fields
            if not pf_list:
                # 从 required_slots / optional_slots 自动推导 PolicyField
                pf_list = cls._infer_policy_fields(intent, schema)

            for pf in pf_list:
                row = [
                    pf.name,
                    pf.field_type,
                    pf.description,
                    str(pf.required).lower(),
                    str(pf.confirm).lower(),
                    str(pf.ask_by_system).lower(),
                    pf.depends_on or "",
                    ",".join(pf.possible_values),
                    pf.on_success,
                ]
                # CSV 转义（含逗号或换行的字段加引号）
                out = io.StringIO()
                w = csv.writer(out)
                w.writerow(row)
                lines.append(out.getvalue().rstrip("\r\n"))

            lines.append("")

        return "\n".join(lines)

    @classmethod
    def save_csv(
        cls,
        schema: ServiceSchema,
        path: Union[str, Path],
        encoding: str = "utf-8",
    ) -> None:
        """将 ``ServiceSchema`` 导出并写入 CSV 文件。"""
        csv_text = cls.to_csv(schema)
        Path(path).write_text(csv_text, encoding=encoding)
        logger.info(f"[WorksheetLoader] Worksheet CSV 已写入: {path}")

    @classmethod
    def to_worksheet_json(
        cls,
        schema: ServiceSchema,
        indent: int = 2,
    ) -> str:
        """将 ``ServiceSchema`` 导出为完整 Worksheet JSON 字符串。

        输出格式兼容 :meth:`from_json` 导入。
        """
        intents_out: List[Dict[str, Any]] = []
        for intent in schema.intents:
            pf_list = intent.policy_fields
            if not pf_list:
                pf_list = cls._infer_policy_fields(intent, schema)
            intents_out.append({
                "name": intent.name,
                "description": intent.description,
                "is_transactional": intent.is_transactional,
                "result_slots": intent.result_slots,
                "policy_fields": [pf.to_dict() for pf in pf_list],
            })
        data = {
            "service_name": schema.service_name,
            "description": schema.description,
            "intents": intents_out,
        }
        return json.dumps(data, ensure_ascii=False, indent=indent)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @classmethod
    def _fields_to_schema(
        cls,
        fields: List[PolicyField],
        service_name: str = "WorksheetService",
    ) -> ServiceSchema:
        """将 PolicyField 列表转换为含单意图的 ServiceSchema。"""
        required = [f.name for f in fields if f.required]
        optional = [f.name for f in fields if not f.required]
        intent = IntentDefinition(
            name="default_intent",
            description="",
            required_slots=required,
            optional_slots=optional,
            policy_fields=fields,
        )
        slots = [
            SlotDefinition(
                name=f.name,
                description=f.description,
                is_categorical=(f.field_type == "enum"),
                possible_values=f.possible_values,
                is_required=f.required,
            )
            for f in fields
        ]
        return ServiceSchema(
            service_name=service_name,
            description="",
            slots=slots,
            intents=[intent],
        )

    @classmethod
    def _infer_policy_fields(
        cls,
        intent: IntentDefinition,
        schema: ServiceSchema,
    ) -> List[PolicyField]:
        """从 intent 的 required_slots / optional_slots 推导 PolicyField 列表。

        用于当 intent.policy_fields 为空时（如从标准 SGD schema.json 加载的意图），
        以最小信息构建 PolicyField，使导出的 CSV/JSON 仍包含基本策略注解。
        """
        result: List[PolicyField] = []
        for slot_name in intent.required_slots:
            slot = schema.get_slot(slot_name)
            result.append(PolicyField(
                name=slot_name,
                description=slot.description if slot else "",
                required=True,
                field_type="enum" if (slot and slot.is_categorical) else "str",
                possible_values=slot.possible_values if slot else [],
            ))
        for slot_name in intent.optional_slots:
            slot = schema.get_slot(slot_name)
            result.append(PolicyField(
                name=slot_name,
                description=slot.description if slot else "",
                required=False,
                field_type="enum" if (slot and slot.is_categorical) else "str",
                possible_values=slot.possible_values if slot else [],
            ))
        return result
