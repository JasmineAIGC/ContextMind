"""
测试用例缓存工具。

提供 ``*_test_cases.json`` 文件的路径计算、序列化保存和反序列化加载，
使多个代码生成器（loop / alpha / sstar / ctree）可以共享同一份预生成的
测试用例，确保跨生成器对比评测的公平性。

缓存文件命名规则（与 companion_path 一致）::

    schema/foo_schema.json  →  schema/foo_test_cases.json
    schema/myservice.json   →  schema/myservice_test_cases.json

文件格式::

    {
        "<intent_name>": [
            {
                "input_slots":     { ... },
                "expected_keys":   [ ... ],
                "expected_values": { ... },
                "description":     "..."
            },
            ...
        ],
        ...
    }
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from contextmind.infra.logger import get_logger
from contextmind.schema_builder.pytod.shared.models import TestCaseItem

logger = get_logger(__name__)


def test_cases_path_for_schema(schema_path: Path) -> Path:
    """根据 schema 路径计算测试用例缓存文件路径。

    缓存文件始终与 schema 文件同目录，不受 output_dir 影响，
    以保证多次生成器运行共享同一个缓存文件。

    Args:
        schema_path: ``*_schema.json`` 文件路径。

    Returns:
        测试用例缓存文件路径（``*_test_cases.json``）。
    """
    stem = schema_path.stem
    base = stem[: -len("_schema")] if stem.endswith("_schema") else stem
    return schema_path.parent / f"{base}_test_cases.json"


def save_test_cases(
    cases_by_intent: Dict[str, List[TestCaseItem]],
    path: Path,
) -> None:
    """将测试用例字典序列化并写入 JSON 文件。

    Args:
        cases_by_intent: intent_name → TestCaseItem 列表 的映射。
        path:            目标 JSON 文件路径（父目录必须已存在）。
    """
    serialized = {
        intent_name: [tc.to_dict() for tc in cases]
        for intent_name, cases in cases_by_intent.items()
    }
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(serialized, fh, ensure_ascii=False, indent=2)
        logger.info(
            f"[test_cache] 已保存 {len(cases_by_intent)} 个意图的测试用例 → {path}"
        )
    except Exception as exc:
        logger.warning(f"[test_cache] 保存测试用例失败: {exc}")


def load_test_cases(path: Path) -> Optional[Dict[str, List[TestCaseItem]]]:
    """从 JSON 文件加载测试用例字典。

    Args:
        path: 测试用例 JSON 文件路径。

    Returns:
        intent_name → TestCaseItem 列表 的映射，加载失败时返回 None。
    """
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            raw: Dict[str, list] = json.load(fh)
        result: Dict[str, List[TestCaseItem]] = {}
        for intent_name, cases_data in raw.items():
            if not isinstance(cases_data, list):
                continue
            result[intent_name] = [
                TestCaseItem.from_dict(item)
                for item in cases_data
                if isinstance(item, dict)
            ]
        total = sum(len(v) for v in result.values())
        logger.info(
            f"[test_cache] 已加载 {len(result)} 个意图共 {total} 条测试用例 ← {path}"
        )
        return result
    except Exception as exc:
        logger.warning(f"[test_cache] 加载测试用例失败: {path} — {exc}")
        return None
