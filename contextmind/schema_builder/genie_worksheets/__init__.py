"""
Genie Worksheets Schema 子包 — contextmind.schema_builder.genie_worksheets

本子包是 Genie Worksheets 算法专用的 schema 定义与加载模块，与 PyTOD 完全独立。

模块结构
--------
::

    contextmind/schema_builder/genie_worksheets/
      __init__.py   — 顶层导出
      models.py     — PolicyField 数据模型及辅助函数
      loader.py     — WorksheetLoader（CSV / JSON 格式导入/导出）

典型用法::

    from contextmind.schema_builder.genie_worksheets import WorksheetLoader, PolicyField

    # 从 CSV 加载 Worksheet
    schema = WorksheetLoader.from_csv("worksheets/restaurant.csv",
                                      service_name="餐厅服务")

    # 从 JSON 加载
    schema = WorksheetLoader.from_json("worksheets/restaurant_worksheet.json")

    # 构造单个策略字段
    pf = PolicyField(name="cuisine", description="菜系", required=True,
                     field_type="enum", possible_values=["川菜", "粤菜"])
"""

from contextmind.schema_builder.genie_worksheets.models import (
    PolicyField,
    _parse_bool,
    _parse_list,
)
from contextmind.schema_builder.genie_worksheets.loader import WorksheetLoader

__all__ = [
    "PolicyField",
    "WorksheetLoader",
    "_parse_bool",
    "_parse_list",
]
