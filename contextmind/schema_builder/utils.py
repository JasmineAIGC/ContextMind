"""
Utility helpers for the schema_builder package.

Currently contains the ``companion_path()`` helper that maps a ``*_schema.json``
path to its corresponding companion file path.
"""

from __future__ import annotations

from pathlib import Path


def companion_path(schema_path: Path, kind: str, suffix: str = ".json") -> Path:
    """返回 companion 文件路径。

    Examples::

        schema/foo_schema.json  → schema/foo_{kind}{suffix}
        schema/myservice.json   → schema/myservice_{kind}{suffix}

    Args:
        schema_path: 原始 ``*_schema.json`` 文件路径。
        kind: companion 文件的类型标识（如 ``"pytod_apis"``、``"fnctod_domain"``、
            ``"validation_report"``）。
        suffix: 文件扩展名（含点号，默认 ``".json"``）。

    Returns:
        companion 文件的绝对/相对路径（与 ``schema_path`` 同目录）。
    """
    stem = schema_path.stem
    base = stem[: -len("_schema")] if stem.endswith("_schema") else stem
    return schema_path.parent / f"{base}_{kind}{suffix}"
