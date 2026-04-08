"""
FnCTOD companion 文件构建器。

本模块实现 :func:`build_fnctod_domain` 函数，用于生成 FnCTOD 算法所需的
``*_fnctod_domain.json`` companion 文件。

**FnCTOD 原论文原理**（ACL 2024 — *Large Language Models as Zero-shot Dialogue
State Tracker through Function Calling*）：

  每个服务/业务域被建模为一个**函数（function）**，该服务的所有对话槽位（slot）
  被映射为函数参数（parameter）。LLM 通过调用该函数从当前对话中提取槽位值，
  实现零样本对话状态追踪（DST）。

  函数签名以**标准 OpenAI Function Calling JSON Schema** 格式描述，可直接供
  ``FunctionManager.add_domain()`` 或 ADK FunctionTool 使用。

输出格式示例::

    {
      "_schema_source": "anyihua_schema.json",
      "_generated_at": "2024-01-01T00:00:00+00:00",
      "name": "AnYiHua_OutboundCall",
      "description": "安逸花外呼促活服务...",
      "parameters": {
        "type": "object",
        "properties": {
          "loan_amount": {
            "type": "string",
            "description": "用户申请或已借款金额"
          },
          "loan_type": {
            "type": "string",
            "description": "借款类型",
            "enum": ["信用贷", "抵押贷"]
          }
        },
        "required": []
      }
    }

与 ``DomainSpec.to_json_schema()`` 的输出格式完全对应，可通过
``load_domain_spec_from_file(path)`` 直接重建 ``DomainSpec`` 对象。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from contextmind.infra.logger import get_logger
from contextmind.modes.pytod.schemas import ServiceSchema, SlotDefinition, load_schema_from_dict
from contextmind.schema_builder.utils import companion_path

logger = get_logger(__name__)


def _slot_to_property(slot: SlotDefinition) -> Dict[str, Any]:
    """将 SlotDefinition 转换为 OpenAI JSON Schema property 字典。

    FnCTOD 中所有槽位均以 ``"string"`` 类型表示（与 FnCTOD 官方实现一致）。
    分类槽位（categorical slot）额外携带 ``"enum"`` 字段，帮助 LLM 选择合法值。

    Args:
        slot: SlotDefinition 对象。

    Returns:
        符合 OpenAI JSON Schema property 规范的字典。
    """
    prop: Dict[str, Any] = {
        "type": "string",
        "description": slot.description,
    }
    if slot.is_categorical and slot.possible_values:
        prop["enum"] = slot.possible_values
    return prop


def _build_domain_json_schema(schema: ServiceSchema) -> Dict[str, Any]:
    """将 ServiceSchema 转换为 OpenAI Function Calling JSON Schema。

    FnCTOD 论文将整个服务/业务域建模为**一个函数**：

    - 函数名 = ``service_name``
    - 函数描述 = ``description``
    - 参数 = 服务下**所有**槽位（含分类槽位的枚举值）
    - required 参数 = ``is_required=True`` 的槽位

    Args:
        schema: 已解析的 ServiceSchema 对象。

    Returns:
        符合 OpenAI Function Calling 规范的 JSON Schema 字典。
    """
    properties: Dict[str, Any] = {}
    required: List[str] = []

    for slot in schema.slots:
        properties[slot.name] = _slot_to_property(slot)
        if slot.is_required:
            required.append(slot.name)

    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        parameters["required"] = required

    return {
        "name": schema.service_name,
        "description": schema.description,
        "parameters": parameters,
    }


def build_fnctod_domain(
    schema_path: Union[str, Path],
    schema: Optional[ServiceSchema] = None,
    *,
    overwrite: bool = True,
) -> Optional[Path]:
    """从 schema.json 生成 FnCTOD ``*_fnctod_domain.json`` companion 文件。

    依据 FnCTOD 原论文将服务/域整体建模为一个 OpenAI Function Calling 函数：
    所有槽位（slots）成为函数参数，分类槽位携带 ``"enum"`` 枚举值列表，
    ``is_required=True`` 的槽位进入 ``"required"`` 数组。

    生成的 JSON 文件可通过以下方式直接加载：

    * ``load_domain_spec_from_file(path)``（重建 DomainSpec）
    * ``FunctionManager.add_domain()``（注册到 FunctionManager）
    * FnCTOD tracker 的 ``from_scenario(..., domain_spec=...)`` 参数

    输出路径命名规则::

        schema/foo_schema.json  →  schema/foo_fnctod_domain.json

    Args:
        schema_path: ``*_schema.json`` 文件路径。
        schema:      已加载的 ServiceSchema（传入可省略重复 IO）。
        overwrite:   目标文件已存在时是否覆盖（默认 True）。

    Returns:
        写入成功时返回生成的文件路径；加载/写入失败时返回 None。
    """
    schema_path = Path(schema_path)
    out_path = companion_path(schema_path, "fnctod_domain", suffix=".json")

    # 目标文件已存在且不覆盖时跳过
    if out_path.exists() and not overwrite:
        logger.debug(f"[FnCTOD] 跳过已存在文件: {out_path}")
        return None

    # 加载 ServiceSchema（若未传入）
    if schema is None:
        try:
            with open(schema_path, encoding="utf-8") as fh:
                schema = load_schema_from_dict(json.load(fh))
        except Exception as exc:
            logger.error(f"[FnCTOD] 加载 schema 失败: {schema_path} — {exc}")
            return None

    if not schema.slots:
        logger.warning(
            f"[FnCTOD] schema '{schema_path.name}' 未定义任何槽位，"
            "生成的 fnctod_domain.json 参数列表为空"
        )

    # 转换为 OpenAI Function Calling JSON Schema
    domain_schema = _build_domain_json_schema(schema)

    # 添加 companion 文件元数据
    output: Dict[str, Any] = {
        "_schema_source": schema_path.name,
        "_generated_at": datetime.now(timezone.utc).isoformat(),
    }
    output.update(domain_schema)

    # 写入 JSON 文件
    try:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(output, fh, ensure_ascii=False, indent=2)
        logger.info(
            f"[FnCTOD] 已生成: {out_path} "
            f"(service={schema.service_name}, {len(schema.slots)} 个槽位)"
        )
    except Exception as exc:
        logger.error(f"[FnCTOD] 写入失败: {out_path} — {exc}")
        return None

    return out_path

