"""
schema_builder 通用工具函数。

本模块包含与具体算法无关的公共工具，可供各算法子包（pytod/、fnctod/ 等）共同使用。
"""

from __future__ import annotations

from pathlib import Path


def companion_path(schema_path: Path, kind: str, suffix: str = ".json") -> Path:
    """根据 schema 文件路径计算对应 companion 文件的路径。

    命名规则示例::

        schema/foo_schema.json  → schema/foo_{kind}{suffix}
        schema/myservice.json   → schema/myservice_{kind}{suffix}

    Args:
        schema_path: 原始 ``*_schema.json`` 文件路径。
        kind:        companion 文件类型标识，如 ``"pytod_apis"``、
                     ``"fnctod_domain"``、``"validation_report"``。
        suffix:      文件扩展名（含点号，默认 ``".json"``）。

    Returns:
        companion 文件的路径（与 ``schema_path`` 同目录）。
    """
    stem = schema_path.stem
    # 去掉 _schema 后缀（若存在），作为 companion 文件名前缀
    base = stem[: -len("_schema")] if stem.endswith("_schema") else stem
    return schema_path.parent / f"{base}_{kind}{suffix}"
