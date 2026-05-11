"""
LLM 输出清洗辅助函数。

本模块专门处理 LLM 返回的原始文本，将其解析并规范化为合法的 Python 代码：

- :func:`clean_llm_function_body` — 提取并规范化单个函数体（支持多种 LLM 输出格式）。
- :func:`clean_llm_module`        — 提取并规范化完整模块的函数定义区。

内部辅助函数（仅在本模块内使用）：

- :func:`_fix_body_first_line_indent` — 修复 LLM 常见 quirk：第一语句行缺少前导缩进。
- :func:`_truncate_to_first_function` — 截取到第一个完整函数定义（语法错误时的 fallback）。
"""

from __future__ import annotations

import ast
import re
import textwrap
from typing import List, Optional

from contextmind.infra.logger import get_logger
from contextmind.modes.pytod.schemas import ServiceSchema

logger = get_logger(__name__)


def clean_llm_function_body(raw: str, func_name: str, param_str: str) -> Optional[str]:
    """从 LLM 响应中提取并验证函数体代码（支持多种 LLM 输出格式）。

    处理 LLM 常见的各种输出模式：
    - 仅输出函数体（无 def 行）
    - 输出完整函数定义（包含 def 行）
    - 用 markdown 代码块包裹
    - def 行前有说明文字（如 "以下是实现：" 或模块级 import）
    - 包含多个函数定义

    Returns:
        经过验证的 4 空格缩进函数体字符串，或 None（无法解析）。
    """
    # 1. 规范化缩进后去除首尾空白
    #    先 dedent 再 strip，确保多行内容缩进一致（避免 strip() 仅移除第一行前导空格
    #    导致后续行出现额外缩进的问题）
    raw = textwrap.dedent(raw).strip()

    # 2. 去除 markdown 代码块标记（```python ... ``` 或 ``` ... ```）
    m = re.search(r"```(?:python)?\s*([\s\S]+?)\s*```", raw)
    if m:
        raw = textwrap.dedent(m.group(1)).strip()

    # 3. 在文本中定位函数定义（支持 LLM 在代码前加说明文字或 import 语句的情况）
    #    优先精确匹配函数名，次之匹配任意 def 行
    def_match = re.search(
        r"^def\s+" + re.escape(func_name) + r"\s*\(", raw, re.MULTILINE
    )
    if def_match is None:
        # 兜底：匹配文本中任意 def 行（覆盖 LLM 使用了不同名称的情况）
        def_match = re.search(r"^def\s+\w+\s*\(", raw, re.MULTILINE)

    if def_match:
        # 截取从 def 行开始的部分，丢弃前置说明文字 / import 语句
        raw = raw[def_match.start():]

        # 先尝试直接 parse；若失败则截取到第一个完整函数后重试
        try:
            tree = ast.parse(raw)
        except SyntaxError:
            raw = _truncate_to_first_function(raw)
            try:
                tree = ast.parse(raw)
            except SyntaxError as exc:
                logger.debug(
                    f"[clean_llm_function_body] {func_name}: 函数定义语法错误 ({exc})，"
                    f"原始片段: {raw[:300]!r}"
                )
                return None

        # 找到目标函数节点（先按名称精确匹配，再取第一个）
        func_def = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                func_def = node
                break
        if func_def is None:
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    func_def = node
                    break

        if func_def:
            lines = raw.splitlines()
            # Skip leading docstring(s): _function_def_header already adds a docstring,
            # so any string-expression at the start of the LLM body is redundant.
            # Find the first non-docstring statement to use as body_start.
            first_code_stmt = next(
                (
                    s for s in func_def.body
                    if not (
                        isinstance(s, ast.Expr)
                        and isinstance(s.value, ast.Constant)
                        and isinstance(s.value.value, str)
                    )
                ),
                None,
            )
            if first_code_stmt is not None:
                body_start = first_code_stmt.lineno - 1
            else:
                # Body consists only of docstrings (no real code) — fall back so the
                # caller receives an empty body and can issue a warning / fallback.
                body_start = func_def.body[0].lineno - 1
            # 用 end_lineno（Python 3.8+）精确截止，避免把后续函数定义包进来
            body_end = (
                func_def.end_lineno
                if hasattr(func_def, "end_lineno") and func_def.end_lineno
                else len(lines)
            )
            body_lines = lines[body_start:body_end]
            raw = textwrap.dedent("\n".join(body_lines))
    else:
        # 无 def 行 —— LLM 直接输出函数体；修复第一行缺失缩进的问题。
        raw = _fix_body_first_line_indent(raw)

    # 4. 规范化缩进 → 重新缩进为 4 空格
    raw = textwrap.dedent("\n".join(raw.splitlines()))
    indented_lines = [
        "    " + line if line.strip() else "" for line in raw.splitlines()
    ]
    body = "\n".join(indented_lines)

    if not body.strip():
        logger.debug(f"[clean_llm_function_body] {func_name}: 提取的函数体为空")
        return None

    # 5. 校验：包装为完整函数定义后解析
    full_src = f"def {func_name}({param_str}):\n{body}\n"
    try:
        ast.parse(full_src)
    except SyntaxError as exc:
        logger.debug(
            f"[clean_llm_function_body] {func_name}: 语法校验失败: {exc}\n"
            f"代码片段:\n{full_src[:400]}"
        )
        return None

    return body


def _fix_body_first_line_indent(raw: str) -> str:
    """修复 LLM 常见 quirk：函数体第一语句行缺少前导缩进。

    某些 LLM 输出纯函数体（无 def 行）时，第一个非空行的缩进为 0，
    而其余非空行均保有 4 空格（或更多）的缩进，导致整体缩进不一致。

    检测条件：
    - 第一个非空行缩进为 0
    - 其余非空行的最小缩进 >= 4

    修复方案：将第一行的缩进补齐到其余行的最小缩进级别，
    之后 textwrap.dedent 即可正确归一化所有行。

    若函数体只有一行（len(nonempty) < 2），则不需要修复，直接返回原内容。
    只有当上述条件严格满足时才修复，否则原样返回，不影响其他格式。
    """
    lines = raw.splitlines()
    nonempty = [(i, line) for i, line in enumerate(lines) if line.strip()]
    if len(nonempty) < 2:
        return raw

    first_idx, first_line = nonempty[0]
    first_indent = len(first_line) - len(first_line.lstrip())
    other_indents = [len(line) - len(line.lstrip()) for _, line in nonempty[1:]]
    min_other = min(other_indents)

    if first_indent == 0 and min_other >= 4:
        fixed = list(lines)
        fixed[first_idx] = " " * min_other + first_line
        return "\n".join(fixed)

    return raw


def _truncate_to_first_function(raw: str) -> str:
    """将 raw 截取到第一个完整函数定义结束处（遇到顶层语法错误时的 fallback）。

    逐行扫描：遇到第二个顶层 def 或 class 定义时停止，
    以此隔离出第一个函数的内容供单独 parse。
    """
    lines = raw.splitlines()
    result: List[str] = []
    in_func = False
    for line in lines:
        is_toplevel_def = bool(re.match(r"^def\s+", line) or re.match(r"^class\s+", line))
        if is_toplevel_def:
            if in_func:
                # 遇到第二个顶层定义：停止采集
                break
            in_func = True
        result.append(line)
    return "\n".join(result)


def clean_llm_module(raw: str, schema: ServiceSchema) -> Optional[str]:
    """从 LLM 响应中提取并验证完整模块的函数定义区。

    处理 markdown 代码块、多余说明文字、重复工具函数定义等常见问题。

    Returns:
        包含所有函数定义的 Python 代码字符串，或 None（无法解析为合法 Python）。
    """
    raw = raw.strip()

    # 去除 markdown 代码块标记
    m = re.search(r"```(?:python)?\s*([\s\S]+?)\s*```", raw)
    if m:
        raw = m.group(1).strip()

    # 移除 LLM 不应输出的共享工具函数重定义
    helper_names = ("_parse_amount", "_ticket_id", "_calc_monthly_payment", "_next_work_day")
    lines = raw.splitlines()
    filtered: List[str] = []
    skip_block = False
    for line in lines:
        stripped = line.strip()
        # 检测共享工具函数重定义的开始
        if stripped.startswith("def ") and any(
            stripped.startswith(f"def {h}") for h in helper_names
        ):
            skip_block = True
        # 检测 INTENT_REGISTRY（由生成器自动追加，LLM 不应输出）
        elif stripped.startswith("INTENT_REGISTRY"):
            skip_block = True
        elif skip_block and stripped and not stripped.startswith(" ") and not stripped.startswith("\t"):
            skip_block = False

        if not skip_block:
            filtered.append(line)

    raw = "\n".join(filtered).strip()

    # 找到第一个 def 函数的起始位置（跳过前置说明文字）
    first_def = re.search(r"^def ", raw, re.MULTILINE)
    if first_def:
        raw = raw[first_def.start():]

    # 校验为合法 Python 源码
    minimal_preamble = "from __future__ import annotations\n"
    try:
        ast.parse(minimal_preamble + raw)
    except SyntaxError as exc:
        logger.debug(f"[clean_llm_module] SyntaxError: {exc}")
        return None

    # 若有意图函数缺失则发出警告
    expected = {intent.name for intent in schema.intents}
    found = set(re.findall(r"^def (\w+)\(", raw, re.MULTILINE))
    missing = expected - found
    if missing:
        logger.warning(
            f"[clean_llm_module] LLM 生成的模块缺少以下函数: {missing}"
        )

    return raw
