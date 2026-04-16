"""
.. deprecated::
    此模块已迁移到 :mod:`contextmind.schema_builder.pytod.testcase.kb_loader`。
    本文件仅为向后兼容保留，所有符号均从 testcase.kb_loader 再导出。
"""

from contextmind.schema_builder.pytod.testcase.kb_loader import (  # noqa: F401
    load_conversion_summary_context,
    load_dialogue_samples,
    load_discovery_samples,
    load_kb_context,
    load_sgd_dialogue_samples,
)

__all__ = [
    "load_conversion_summary_context",
    "load_dialogue_samples",
    "load_discovery_samples",
    "load_kb_context",
    "load_sgd_dialogue_samples",
]
