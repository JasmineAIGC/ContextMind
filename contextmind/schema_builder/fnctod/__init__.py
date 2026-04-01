"""
FnCTOD 算法的 schema 数据构建子包。

本子包将 ``*_schema.json`` 文件转换为 FnCTOD 算法所需的 companion 文件。

已实现
------
- ``builder.py`` — :func:`build_fnctod_domain`：
  将 ServiceSchema 的所有槽位（slots）映射为 OpenAI Function Calling JSON Schema
  格式的 ``*_fnctod_domain.json`` companion 文件，符合 FnCTOD 论文原理
  （ACL 2024：*Large Language Models as Zero-shot Dialogue State Tracker
  through Function Calling*）。

公开 API
--------
- :func:`build_fnctod_domain` — 核心构建函数
"""

from contextmind.schema_builder.fnctod.builder import build_fnctod_domain

__all__ = ["build_fnctod_domain"]

