"""
PyTOD 生成函数的 Phase 4/5 验证模块。

:func:`validate_function`
    将生成的意图函数针对一组测试用例执行并报告通过/失败详情。
    通过 Python ``exec()`` 执行，并预先加载共享工具函数库，
    使函数可调用 ``_ticket_id()``、``_next_work_day()`` 等工具。

:func:`write_validation_report`
    将 :class:`~contextmind.schema_builder.pytod.models.FuncValidation`
    对象序列化为 ``*_validation_report.json`` 文件（与 schema 文件同目录）。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from contextmind.infra.logger import get_logger
from contextmind.modes.pytod.schemas import IntentDefinition

from contextmind.schema_builder.pytod.models import FuncValidation, TestCaseItem
from contextmind.schema_builder.utils import companion_path

logger = get_logger(__name__)


def _values_match(actual: Any, expected: Any) -> bool:
    """判断实际值是否与预期值匹配。

    支持以下比较策略：
    - ``bool``：精确匹配
    - ``int`` / ``float``：精确匹配（int 允许与 float 比较，如 5 == 5.0）
    - ``str``：精确匹配（忽略首尾空白）
    - 预期为 None：actual 为 None 或空字符串均算匹配
    - 其他类型：转为字符串后比较
    """
    if expected is None:
        return actual is None or actual == ""
    if isinstance(expected, bool):
        return actual == expected
    if isinstance(expected, (int, float)):
        try:
            return float(actual) == float(expected)
        except (TypeError, ValueError):
            return str(actual) == str(expected)
    if isinstance(expected, str):
        return str(actual).strip() == expected.strip()
    return actual == expected


def validate_function(
    intent: IntentDefinition,
    func_code: str,
    test_cases: List[TestCaseItem],
    shared_helpers: str,
) -> FuncValidation:
    """Phase 4：使用测试用例执行生成的函数并验证输出格式。

    验证标准（全部通过才算通过）：
    1. 函数执行无异常
    2. 返回值是一个 dict
    3. 返回值中 ``status`` 字段值为 ``"success"``
    4. 所有 ``expected_keys``（包含 result_slots）在返回值中都存在

    Args:
        intent: 意图定义（用于报告和 expected_keys 推断）。
        func_code: 完整的函数定义代码字符串（包含 def 行）。
        test_cases: 测试用例列表（Phase 2 构建）。
        shared_helpers: 共享工具函数代码（``SHARED_HELPERS``），
            提供 ``_ticket_id`` 等工具给被测函数调用。

    Returns:
        :class:`~contextmind.schema_builder.models.FuncValidation` 对象，
        包含通过率和失败用例详情。
    """
    if not test_cases:
        return FuncValidation(intent_name=intent.name, total=0, passed=0)

    # 将共享工具函数 + 意图函数代码编译到同一命名空间
    exec_source = "from __future__ import annotations\n" + shared_helpers + "\n" + func_code

    namespace: Dict[str, Any] = {}
    try:
        exec(compile(exec_source, "<generated>", "exec"), namespace)  # noqa: S102
    except SyntaxError as exc:
        return FuncValidation(
            intent_name=intent.name,
            total=len(test_cases),
            passed=0,
            error=f"SyntaxError: {exc}",
        )
    except Exception as exc:
        return FuncValidation(
            intent_name=intent.name,
            total=len(test_cases),
            passed=0,
            error=f"CompileError: {exc}",
        )

    func_obj = namespace.get(intent.name)
    if func_obj is None:
        return FuncValidation(
            intent_name=intent.name,
            total=len(test_cases),
            passed=0,
            error=f"函数 {intent.name} 未在生成代码中找到",
        )

    passed = 0
    failures: List[Dict[str, Any]] = []

    for tc in test_cases:
        error_msg: Optional[str] = None
        result: Optional[Any] = None

        try:
            result = func_obj(**tc.input_slots)
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"

        # 验证返回值格式
        if error_msg is None:
            if not isinstance(result, dict):
                error_msg = f"返回值不是 dict，实际类型: {type(result).__name__}"
            elif result.get("status") != "success":
                error_msg = (
                    f"status != 'success'，实际值: {result.get('status')!r}  "
                    f"（完整返回: {json.dumps(result, ensure_ascii=False, default=str)[:200]}）"
                )
            else:
                missing = [k for k in tc.expected_keys if k not in result]
                if missing:
                    error_msg = (
                        f"返回值缺少字段: {missing}  "
                        f"（实际字段: {list(result.keys())}）"
                    )
                elif tc.expected_values:
                    # 验证预期计算值（仅当 expected_values 非空时，校验完整/边界场景的输出）
                    value_errors: List[str] = []
                    for field_name, expected in tc.expected_values.items():
                        actual = result.get(field_name)
                        if actual is None and field_name not in result:
                            value_errors.append(
                                f"字段 {field_name!r} 不存在于返回值中"
                            )
                        elif not _values_match(actual, expected):
                            value_errors.append(
                                f"字段 {field_name!r}: 期望 {expected!r}，实际 {actual!r}"
                            )
                    if value_errors:
                        error_msg = (
                            f"返回值业务计算结果不符: {'; '.join(value_errors)}  "
                            f"（完整返回: {json.dumps(result, ensure_ascii=False, default=str)[:300]}）"
                        )

        if error_msg is None:
            passed += 1
        else:
            failures.append({
                "description": tc.description,
                "input_slots": tc.input_slots,
                "error": error_msg,
            })

    return FuncValidation(
        intent_name=intent.name,
        total=len(test_cases),
        passed=passed,
        failures=failures,
    )


def write_validation_report(
    schema_path: Path,
    validations: Dict[str, FuncValidation],
    test_cases_by_intent: Dict[str, List[TestCaseItem]],
    *,
    output_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Phase 5：将验证结果写入 ``xxx_validation_report.json`` 文件。

    报告结构::

        {
          "schema": "anyihua_schema.json",
          "generated_at": "...",
          "summary": {"total_intents": 10, "validated": 8, "avg_pass_rate": 0.95},
          "intents": {
            "verify_identity": {
              "total_cases": 5, "passed": 5, "pass_rate": 1.0,
              "iterations": 0, "failures": []
            },
            ...
          }
        }

    Args:
        schema_path: schema 文件路径（用于命名报告文件和填充元数据）。
        validations: intent_name → :class:`~contextmind.schema_builder.models.FuncValidation` 映射。
        test_cases_by_intent: intent_name → :class:`~contextmind.schema_builder.models.TestCaseItem`
            列表映射。
        output_dir:  可选的输出目录。指定时报告文件写入该目录，否则与 schema 文件同目录。

    Returns:
        报告文件路径，写入失败时返回 None。
    """
    report_path = companion_path(schema_path, "validation_report", suffix=".json", output_dir=output_dir)

    intent_report: Dict[str, Any] = {}
    for name, v in validations.items():
        intent_report[name] = {
            "total_cases": v.total,
            "passed": v.passed,
            "pass_rate": round(v.pass_rate, 4),
            "iterations": v.iterations,
            "error": v.error,
            "failures": v.failures[:3],   # 最多保留 3 条失败样本
        }

    total = len(validations)
    validated = sum(1 for v in validations.values() if v.total > 0)
    avg_rate = (
        sum(v.pass_rate for v in validations.values() if v.total > 0) / validated
        if validated > 0 else 0.0
    )

    report: Dict[str, Any] = {
        "schema": schema_path.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_intents": total,
            "validated": validated,
            "skipped": total - validated,
            "avg_pass_rate": round(avg_rate, 4),
        },
        "intents": intent_report,
    }

    try:
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        logger.info(f"[SchemaDataBuilder] 已写入验证报告: {report_path}")
        return report_path
    except Exception as exc:
        logger.warning(f"[SchemaDataBuilder] 写入验证报告失败: {exc}")
        return None
