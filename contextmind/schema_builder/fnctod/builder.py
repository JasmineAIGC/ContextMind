"""
FnCTOD companion 文件构建器（待实现）。

本模块将实现 :func:`build_fnctod_domain` 函数，用于生成 FnCTOD 算法所需的
``*_fnctod_domain.json`` companion 文件。

当前状态：**占位符，功能尚未实现。**

预期输出格式（标准 OpenAI Function Calling JSON Schema）::

    {
      "_schema_source": "anyihua_schema.json",
      "_generated_at": "...",
      "name": "AnYiHua_OutboundCall",
      "description": "...",
      "parameters": {
        "type": "object",
        "properties": {
          "slot_name": {
            "type": "string",
            "description": "slot_description"
          },
          "categorical_slot": {
            "type": "string",
            "description": "...",
            "enum": ["val1", "val2", ...]
          }
        },
        "required": ["required_slot_name", ...]
      }
    }

与 FunctionManager 中 ``DomainSpec.to_json_schema()`` 的输出格式对应，
可通过 ``load_fnctod_domain_spec(path)`` 直接重建 ``DomainSpec`` 对象。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Union

from contextmind.infra.logger import get_logger
from contextmind.modes.pytod.schemas import ServiceSchema

logger = get_logger(__name__)


def build_fnctod_domain(
    schema_path: Union[str, Path],
    schema: Optional[ServiceSchema] = None,
    *,
    overwrite: bool = True,
) -> Optional[Path]:
    """从 schema.json 生成 FnCTOD ``*_fnctod_domain.json`` companion 文件。

    .. note::
        **当前为占位实现，功能尚未完成。** 调用此函数将记录一条警告日志并返回 None。
        待实现后将生成标准 OpenAI Function Calling JSON Schema 格式的文件。

    Args:
        schema_path: ``*_schema.json`` 文件路径。
        schema:      已加载的 ServiceSchema（传入可省略重复 IO）。
        overwrite:   目标文件已存在时是否覆盖（默认 True）。

    Returns:
        当前始终返回 None（功能未实现）。
    """
    logger.warning(
        f"[FnCTOD] build_fnctod_domain() 尚未实现，跳过: {schema_path}"
    )
    return None
