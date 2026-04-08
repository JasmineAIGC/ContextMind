"""
schema_builder 通用工具函数。

本模块包含与具体算法无关的公共工具，可供各算法子包（pytod/、fnctod/ 等）共同使用。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def companion_path(
    schema_path: Path,
    kind: str,
    suffix: str = ".json",
    *,
    output_dir: Optional[Path] = None,
) -> Path:
    """根据 schema 文件路径计算对应 companion 文件的路径。

    命名规则示例::

        schema/foo_schema.json  → schema/foo_{kind}{suffix}
        schema/myservice.json   → schema/myservice_{kind}{suffix}

    Args:
        schema_path: 原始 ``*_schema.json`` 文件路径。
        kind:        companion 文件类型标识，如 ``"pytod_apis"``、
                     ``"fnctod_domain"``、``"validation_report"``。
        suffix:      文件扩展名（含点号，默认 ``".json"``）。
        output_dir:  可选的输出目录。指定时输出到该目录，否则输出到 ``schema_path`` 同目录。

    Returns:
        companion 文件的路径。
    """
    stem = schema_path.stem
    # 去掉 _schema 后缀（若存在），作为 companion 文件名前缀
    base = stem[: -len("_schema")] if stem.endswith("_schema") else stem
    parent = output_dir if output_dir is not None else schema_path.parent
    return parent / f"{base}_{kind}{suffix}"
