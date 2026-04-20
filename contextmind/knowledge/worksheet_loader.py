"""
WorksheetLoader — 向后兼容入口（已迁移至 schema_builder.genie_worksheets）

本模块保留以维持现有调用方的兼容性。
新代码请直接从 ``contextmind.schema_builder.genie_worksheets`` 导入::

    from contextmind.schema_builder.genie_worksheets import WorksheetLoader
"""

from contextmind.schema_builder.genie_worksheets.loader import WorksheetLoader  # noqa: F401

__all__ = ["WorksheetLoader"]
