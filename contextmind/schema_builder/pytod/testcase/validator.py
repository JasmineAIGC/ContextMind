"""
PyTOD 生成函数的 Phase 4/5 验证模块。

:func:`validate_function`
    将生成的意图函数针对一组测试用例执行并报告通过/失败详情。
    通过 Python ``exec()`` 执行，并预先加载共享工具函数库，
    使函数可调用 ``_ticket_id()``、``_next_work_day()`` 等工具。

:func:`write_validation_report`
    将 :class:`~contextmind.schema_builder.pytod.testcase.models.FuncValidation`
    对象序列化为 ``*_validation_report.json`` 文件（与 schema 文件同目录）。

:func:`validate_pytod_apis_source`
    对组装完成的完整 .py 源码做最终模块级健壮性检查：编译执行整个模块，
    对每个意图函数执行零参数调用，返回 ``{func_name: error_or_None}`` 映射。

:func:`replace_function_in_source`
    在源码字符串中将指定名称的函数定义替换为新代码（用于将失败函数替换为安全存根）。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from contextmind.infra.logger import get_logger
from contextmind.modes.pytod.schemas import IntentDefinition

from contextmind.schema_builder.pytod.testcase.models import FuncValidation, TestCaseItem
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


def check_zero_arg_robustness(
    func_name: str,
    func_code: str,
    shared_helpers: str,
) -> Optional[str]:
    """零参数调用检查：验证函数在所有参数为 None 时能正常运行。

    与 ``tracker.py`` 中 ``load_pytod_api_module()`` 的运行时健壮性检查等价：
    捕获调用 ``func_name()``（无参数）时抛出的任何异常，包括但不限于：

    - **NameError / UnboundLocalError**：函数体引用了未在签名中声明的变量，
      或条件赋值模式（如 ``if x: x = float(x)``）导致局部变量在赋值前被读取。
    - **ZeroDivisionError**：``_parse_amount(None)`` 返回 ``0.0``，
      若代码将其用作除数会在 None 输入时崩溃。
    - **AttributeError**：对 None 参数调用字符串方法（如 ``value.strip()``）。
    - 其他任何运行时异常。

    在代码生成阶段提前捕获这些缺陷，可以避免函数在运行时被替换为安全存根。

    Args:
        func_name:      意图函数名称（与签名中 ``def func_name(...)`` 一致）。
        func_code:      完整函数定义代码字符串（含 ``def`` 行）。
        shared_helpers: 共享工具函数代码（``SHARED_HELPERS``）。

    Returns:
        函数调用抛出任何异常时返回错误描述字符串；
        调用成功时返回 ``None``。

        与 ``tracker.py`` 中 ``load_pytod_api_module()`` 的行为保持一致：
        所有参数均为 None 时函数必须能正常执行（不抛出任何异常），
        否则运行时会被替换为安全存根。
    """
    try:
        exec_source = "from __future__ import annotations\n" + shared_helpers + "\n" + func_code
        namespace: Dict[str, Any] = {}
        exec(compile(exec_source, "<zero_arg_check>", "exec"), namespace)  # noqa: S102
        func_obj = namespace.get(func_name)
        if func_obj is not None:
            func_obj()
        return None
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"


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


def validate_pytod_apis_source(
    source: str,
    intent_names: List[str],
    *,
    tag: str = "",
) -> Dict[str, Optional[str]]:
    """对组装完成的完整 .py 源码做最终模块级健壮性检查。

    编译并执行整个模块（含 SHARED_HELPERS + 所有意图函数），然后对每个意图函数
    执行零参数调用（与 ``tracker.py`` 中 ``load_pytod_api_module()`` 的运行时检查等价）。

    此函数在 Phase 5 写入磁盘后调用，可捕获在逐函数生成阶段漏过的缺陷，包括：

    - 模块编译失败（语法错误、名称引用错误等模块级问题）
    - 函数体在完整模块上下文中的运行时错误（NameError、UnboundLocalError、
      TypeError、ZeroDivisionError、AttributeError 等）

    Args:
        source:        组装完成的完整 Python 源码字符串（含 SHARED_HELPERS + 所有意图函数）。
        intent_names:  所有意图函数名称列表（与 ``schema.intents[*].name`` 对应）。
        tag:           日志前缀标签（如 ``"[loop]"``、``"[ACIA]"``），用于区分调用方。

    Returns:
        ``{func_name: None}`` 表示通过，``{func_name: error_msg}`` 表示失败。
        若模块本身编译失败，则所有函数均以同一编译错误标记为失败。
    """
    prefix = f"{tag} " if tag else ""
    results: Dict[str, Optional[str]] = {name: None for name in intent_names}

    # 1. 编译并执行整个模块源码
    namespace: Dict[str, Any] = {}
    try:
        exec(compile(source, "<final_validate>", "exec"), namespace)  # noqa: S102
    except Exception as exc:
        compile_err = f"{type(exc).__name__}: {exc}"
        logger.warning(f"{prefix}最终校验：模块编译失败 — {compile_err}")
        for name in intent_names:
            results[name] = f"模块编译失败: {compile_err}"
        return results

    # 2. 对每个意图函数执行零参数调用
    for name in intent_names:
        func_obj = namespace.get(name)
        if func_obj is None:
            results[name] = f"函数 '{name}' 在模块命名空间中未找到"
            continue
        try:
            func_obj()
        except Exception as exc:
            results[name] = f"{type(exc).__name__}: {exc}"

    return results


def replace_function_in_source(source: str, func_name: str, replacement_code: str) -> str:
    """在源码字符串中将指定名称的函数定义替换为新代码。

    用于将最终校验中仍失败的函数替换为安全存根，保证生成的 .py 文件中每个意图函数
    都能在零参数调用时正常返回，与 ``load_pytod_api_module()`` 的运行时行为一致。

    替换策略：
    - 在源码中定位 ``def func_name(`` 所在行
    - 向后查找下一个顶级 ``def ``、``class `` 定义或文件末尾作为函数结束边界
    - 用 ``replacement_code`` 完整替换该范围的代码

    Args:
        source:           待修改的完整 Python 源码字符串。
        func_name:        要替换的函数名称。
        replacement_code: 替换后的完整函数定义代码字符串（含 ``def`` 行）。

    Returns:
        替换后的源码字符串。若未找到目标函数则原样返回。
    """
    lines = source.splitlines(keepends=True)
    start_idx: Optional[int] = None
    end_idx = len(lines)

    func_def_re = re.compile(rf'^def {re.escape(func_name)}\s*\(')
    top_level_re = re.compile(r'^(def |class )')

    for i, line in enumerate(lines):
        if start_idx is None:
            if func_def_re.match(line):
                start_idx = i
        else:
            # 下一个顶级定义（不是当前函数自身的第一行）标志着当前函数结束
            if top_level_re.match(line) and i > start_idx:
                end_idx = i
                break

    if start_idx is None:
        logger.debug(f"replace_function_in_source: 未找到函数 '{func_name}'，跳过替换")
        return source

    prefix_str = ''.join(lines[:start_idx])
    suffix_str = ''.join(lines[end_idx:])
    # 确保替换代码以换行符结尾，并在函数间保留一个空行
    new_code = replacement_code.rstrip('\n') + '\n\n'
    return prefix_str + new_code + suffix_str
