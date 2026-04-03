"""
AlphaCodium 风格代码合成器（AlphaSynthesizer）。

实现 ACIA 的四阶段改进流水线：

  Phase R — 反思（Reflection）：生成前分析函数业务语义
  Phase G — 骨架约束生成（Generation）：确保返回结构正确
  Phase A — 失败模式分析（Failure Analysis）：定向诊断问题
  Phase F — 定向修复（Targeted Repair）+ 收敛重启：跳出局部最优

单次合成（synthesize()）的流程：
  1. reflect()     → 业务理解 JSON（可选，失败时降级为空字符串）
  2. generate_body() → 骨架约束的初始函数体
  3. 验证 + 迭代修复循环：
     - 达到阈值 → 返回
     - 连续 2 轮无提升 → 全新重启（re-reflect + re-generate）
     - 有改善 → analyze_failures() + repair_body()

AlphaSynthesizer 不负责测试用例生成（Phase 2）和文件组装（Phase 5），
这些工作由 builder.py 调用现有的 PyTODApiCodeGenerator 和文件组装逻辑完成。
"""

from __future__ import annotations

import json
import re
import textwrap
from typing import Any, Dict, List, Optional, Tuple

from contextmind.infra.logger import get_logger
from contextmind.modes.pytod.schemas import IntentDefinition, ServiceSchema
from contextmind.schema_builder.pytod.models import FuncValidation, TestCaseItem

from contextmind.schema_builder.alpha.prompts import (
    ANALYZE_SYSTEM,
    ANALYZE_USER_TEMPLATE,
    GENERATE_SYSTEM,
    GENERATE_USER_TEMPLATE,
    REFLECT_SYSTEM,
    REFLECT_USER_TEMPLATE,
    REPAIR_SYSTEM,
    REPAIR_USER_TEMPLATE,
)

logger = get_logger(__name__)

# 连续无提升多少轮触发全新重启
_NO_IMPROVE_THRESHOLD = 2


def _extract_function_body(raw: str, intent_name: str) -> Optional[str]:
    """从 LLM 输出中提取函数体（不含 def 行和 docstring 行）。

    LLM 有时会意外输出 def 行、docstring、markdown 标记等，
    本函数做宽松清洗：
    1. 去除 markdown 代码块标记（```python … ```）
    2. 去除意外输出的 def 行
    3. 去除意外输出的 docstring（triple-quote 块）
    4. 统一调整为 4 空格缩进
    5. 保证以 return 语句结尾（否则视为无效）

    Args:
        raw: LLM 原始输出文本。
        intent_name: 意图名称（用于日志）。

    Returns:
        清洗后的函数体字符串（4 空格缩进），无法提取时返回 None。
    """
    if not raw or not raw.strip():
        return None

    # 1. 去除 markdown 代码块标记
    text = re.sub(r"```(?:python)?\s*\n?", "", raw)
    text = re.sub(r"\n?```", "", text)
    text = text.strip()

    lines = text.splitlines()

    # 2. 去除 def 行（包含函数名）
    filtered: List[str] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        # 跳过 def 行
        if stripped.startswith("def ") and "(" in stripped:
            i += 1
            continue

        # 跳过 triple-quote docstring（单行或多行）
        if stripped.startswith('"""') or stripped.startswith("'''"):
            quote = stripped[:3]
            # 多行 docstring：找到关闭的 quote
            if stripped.count(quote) >= 2 and len(stripped) > 3:
                # 单行 docstring，直接跳过
                i += 1
                continue
            else:
                # 多行：跳过直到关闭 quote
                i += 1
                while i < len(lines) and quote not in lines[i]:
                    i += 1
                i += 1  # 跳过关闭行
                continue

        filtered.append(lines[i])
        i += 1

    # 去除开头的空行
    while filtered and not filtered[0].strip():
        filtered.pop(0)

    if not filtered:
        return None

    # 3. 统一 4 空格缩进
    non_empty = [l for l in filtered if l.strip()]
    if not non_empty:
        return None

    min_indent = min(len(l) - len(l.lstrip()) for l in non_empty)
    normalized: List[str] = []
    for line in filtered:
        if line.strip():
            normalized.append("    " + line[min_indent:].rstrip())
        else:
            normalized.append("")

    body = "\n".join(normalized).rstrip()

    # 4. 验证包含 return 语句
    if "return " not in body:
        logger.warning(
            f"[AlphaSynthesizer] {intent_name}: 提取的函数体不含 return 语句"
        )
        return None

    return body


def _build_required_return_keys(intent: IntentDefinition) -> str:
    """构建骨架约束说明文本（列出必须出现在 return 字典中的所有键）。"""
    keys = list(intent.result_slots) if intent.result_slots else []
    if "status" not in keys:
        keys = ["status"] + keys

    lines = [f'  "{k}": ...' for k in keys]
    keys_str = "{\n" + ",\n".join(lines) + "\n}"
    return (
        f"{keys_str}\n\n"
        f"必须出现的键（缺少任何一个都算测试失败）：{', '.join(repr(k) for k in keys)}"
    )


def _format_test_cases_for_prompt(
    test_cases: List[TestCaseItem], max_cases: int = 5
) -> str:
    """将测试用例格式化为 LLM 友好的文本。"""
    if not test_cases:
        return "（暂无测试用例）"

    lines: List[str] = []
    for i, tc in enumerate(test_cases[:max_cases], 1):
        desc = f"【{tc.description}】" if tc.description else f"用例 {i}"
        input_str = json.dumps(tc.input_slots, ensure_ascii=False)
        ev_str = ""
        if tc.expected_values:
            ev_str = f"\n  期望输出值: {json.dumps(tc.expected_values, ensure_ascii=False)}"
        if tc.expected_keys:
            ev_str += f"\n  期望返回键: {tc.expected_keys}"
        lines.append(f"用例 {i} {desc}\n  输入: {input_str}{ev_str}")

    return "\n\n".join(lines)


def _format_failures_for_prompt(failures: List[Dict[str, Any]]) -> str:
    """将失败详情格式化为 LLM 友好的文本。"""
    if not failures:
        return "（无失败用例）"
    lines: List[str] = []
    for i, f in enumerate(failures, 1):
        lines.append(
            f"失败 {i}: 输入={json.dumps(f.get('input_slots', {}), ensure_ascii=False)}\n"
            f"  错误: {f.get('error', '未知')}"
        )
    return "\n\n".join(lines)


class AlphaSynthesizer:
    """AlphaCodium 风格的单函数代码合成器。

    负责 Phase R（反思）、Phase G（骨架约束生成）、Phase A（失败分析）、
    Phase F（定向修复 + 收敛重启）四个阶段，
    Phase 2（测试用例）和 Phase 5（文件组装）由外部 builder 负责。

    Args:
        llm_client: AdkLLMClient 实例。
    """

    def __init__(self, llm_client: Any) -> None:
        self._llm = llm_client

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def synthesize(
        self,
        intent: IntentDefinition,
        schema: ServiceSchema,
        all_slot_descs: Dict[str, str],
        test_cases: List[TestCaseItem],
        max_iterations: int = 10,
        pass_rate_threshold: float = 0.9,
        dialogue_hint: str = "",
    ) -> Tuple[str, FuncValidation]:
        """完整合成流水线：R → G → 验证 → 迭代（A + F，含收敛重启）。

        Args:
            intent: 当前意图定义。
            schema: 服务 schema（提供 service_name 等上下文）。
            all_slot_descs: 槽位名 → 描述的映射字典。
            test_cases: Phase 2 生成的测试用例列表。
            max_iterations: 最大迭代修复轮次。
            pass_rate_threshold: 通过率阈值（达到后提前终止）。
            dialogue_hint: 可选，KB 业务背景字符串。

        Returns:
            (func_code, validation) 元组：
            - func_code: 完整的函数代码字符串（含 def 行）
            - validation: 最终验证结果
        """
        from contextmind.schema_builder.pytod.helpers import SHARED_HELPERS
        from contextmind.schema_builder.pytod.validator import validate_function

        header = self._build_header(intent)

        # Phase R：反思（失败时降级，不阻塞后续生成）
        logger.info(f"[ACIA]   Phase R: {intent.name} — 业务反思...")
        reflection = self._reflect(intent, schema, all_slot_descs, test_cases)
        if reflection:
            logger.info(f"[ACIA]   Phase R: {intent.name} — 反思完成")
        else:
            logger.warning(f"[ACIA]   Phase R: {intent.name} — 反思失败，跳过")

        # Phase G：骨架约束生成
        logger.info(f"[ACIA]   Phase G: {intent.name} — 骨架约束生成...")
        body = self._generate_body(intent, schema, all_slot_descs, test_cases, reflection)
        if body is None:
            logger.warning(f"[ACIA]   Phase G: {intent.name} — 生成失败，回退到 stub")
            func_code = header + "\n    return {\"status\": \"success\"}"
        else:
            func_code = header + "\n" + body

        # 无测试用例时直接返回
        if not test_cases:
            return func_code, FuncValidation(intent_name=intent.name, total=0, passed=0)

        # 初始验证
        validation = validate_function(intent, func_code, test_cases, SHARED_HELPERS)
        logger.info(
            f"[ACIA]   Phase G 后: {intent.name} — "
            f"通过率 {validation.pass_rate:.1%} ({validation.passed}/{validation.total})"
        )

        best_code = func_code
        best_validation = validation
        no_improve_streak = 0
        total_iterations = 0

        # 迭代修复循环
        for iteration in range(1, max_iterations + 1):
            if best_validation.pass_rate >= pass_rate_threshold:
                break

            logger.info(
                f"[ACIA]   修复第 {iteration} 轮: {intent.name} "
                f"(通过率 {best_validation.pass_rate:.1%} < 阈值 {pass_rate_threshold:.1%})"
            )

            # 收敛检测：连续 2 轮无提升 → 全新重启
            if no_improve_streak >= _NO_IMPROVE_THRESHOLD:
                logger.info(
                    f"[ACIA]   ↻ {intent.name}: 连续 {no_improve_streak} 轮无提升，全新重启..."
                )
                # 全新反思（通知 LLM 换一种思路）
                reflection = self._reflect(
                    intent, schema, all_slot_descs, test_cases,
                    hint="请换一种完全不同的实现思路，上次的思路导致测试失败"
                )
                body = self._generate_body(
                    intent, schema, all_slot_descs, test_cases, reflection
                )
                total_iterations += 1
                if body is not None:
                    func_code = header + "\n" + body
                    validation = validate_function(
                        intent, func_code, test_cases, SHARED_HELPERS
                    )
                    logger.info(
                        f"[ACIA]   重启后: {intent.name} — "
                        f"通过率 {validation.pass_rate:.1%} ({validation.passed}/{validation.total})"
                    )
                    if validation.pass_rate > best_validation.pass_rate:
                        best_code = func_code
                        best_validation = validation
                no_improve_streak = 0
                continue

            # Phase A：失败模式分析
            failure_analysis = self._analyze_failures(intent, best_code, best_validation)

            # Phase F：定向修复
            body = self._repair_body(intent, schema, best_code, best_validation, failure_analysis)
            total_iterations += 1
            if body is None:
                logger.warning(f"[ACIA]   {intent.name}: 第 {iteration} 轮修复失败，跳过")
                no_improve_streak += 1
                continue

            repaired_code = header + "\n" + body
            new_validation = validate_function(
                intent, repaired_code, test_cases, SHARED_HELPERS
            )
            logger.info(
                f"[ACIA]   第 {iteration} 轮后: {intent.name} — "
                f"通过率 {new_validation.pass_rate:.1%} ({new_validation.passed}/{new_validation.total})"
            )

            if new_validation.pass_rate > best_validation.pass_rate:
                best_code = repaired_code
                best_validation = new_validation
                no_improve_streak = 0
            else:
                no_improve_streak += 1

        # 更新最终实际使用的迭代次数
        best_validation = FuncValidation(
            intent_name=best_validation.intent_name,
            total=best_validation.total,
            passed=best_validation.passed,
            failures=best_validation.failures,
            iterations=total_iterations,
            error=best_validation.error,
        )
        return best_code, best_validation

    # ------------------------------------------------------------------
    # Phase R：反思
    # ------------------------------------------------------------------

    def _reflect(
        self,
        intent: IntentDefinition,
        schema: ServiceSchema,
        all_slot_descs: Dict[str, str],
        test_cases: List[TestCaseItem],
        hint: str = "",
    ) -> str:
        """调用 LLM 分析意图业务语义，返回 JSON 字符串。失败时返回空字符串。"""
        params = list(dict.fromkeys(
            list(intent.required_slots) + list(intent.optional_slots)
        ))

        input_slots_desc = "\n".join(
            f"  - {p}: {all_slot_descs.get(p, p)}" for p in params
        ) or "  （无输入参数）"

        result_slots_desc = "\n".join(
            f"  - {rs}" for rs in intent.result_slots
        ) or "  （无专用 result_slots）"

        test_cases_preview = _format_test_cases_for_prompt(test_cases, max_cases=3)

        hint_section = f"\n\n提示：{hint}" if hint else ""
        user_content = REFLECT_USER_TEMPLATE.format(
            intent_name=intent.name,
            description=intent.description or intent.name,
            input_slots_desc=input_slots_desc,
            result_slots_desc=result_slots_desc,
            test_cases_preview=test_cases_preview,
        ) + hint_section

        messages = [
            {"role": "system", "content": REFLECT_SYSTEM},
            {"role": "user", "content": user_content},
        ]

        try:
            raw = self._chat_sync(messages)
            # 尝试验证 JSON 有效性
            cleaned = re.sub(r"```(?:json)?\s*\n?", "", raw)
            cleaned = re.sub(r"\n?```", "", cleaned).strip()
            json.loads(cleaned)  # 验证合法性，失败则走 except
            return cleaned
        except Exception as exc:
            logger.debug(f"[ACIA] {intent.name}: 反思 LLM 调用/解析失败 ({exc})")
            return ""

    # ------------------------------------------------------------------
    # Phase G：骨架约束生成
    # ------------------------------------------------------------------

    def _generate_body(
        self,
        intent: IntentDefinition,
        schema: ServiceSchema,
        all_slot_descs: Dict[str, str],
        test_cases: List[TestCaseItem],
        reflection: str = "",
    ) -> Optional[str]:
        """骨架约束生成：LLM 仅输出函数体，框架添加 def 行和 docstring。"""
        params = list(dict.fromkeys(
            list(intent.required_slots) + list(intent.optional_slots)
        ))
        param_str = ", ".join([f"{p}=None" for p in params]) if params else ""

        required_return_keys = _build_required_return_keys(intent)
        test_cases_str = _format_test_cases_for_prompt(test_cases)

        # 反思内容优化展示：只取关键字段
        if reflection:
            try:
                r = json.loads(reflection)
                reflection_display = (
                    f"业务动作: {r.get('business_action', '（未知）')}\n"
                    + "计算步骤:\n"
                    + "\n".join(f"  {s}" for s in r.get('computation_steps', []))
                    + f"\n关键陷阱: {r.get('key_pitfall', '（无）')}\n"
                    + "默认值: "
                    + json.dumps(r.get('default_values', {}), ensure_ascii=False)
                )
            except Exception:
                reflection_display = reflection
        else:
            reflection_display = "（跳过）"

        user_content = GENERATE_USER_TEMPLATE.format(
            reflection=reflection_display,
            intent_name=intent.name,
            param_str=param_str,
            description=intent.description or intent.name,
            required_return_keys=required_return_keys,
            test_cases_str=test_cases_str,
        )

        messages = [
            {"role": "system", "content": GENERATE_SYSTEM},
            {"role": "user", "content": user_content},
        ]

        try:
            raw = self._chat_sync(messages)
            body = _extract_function_body(raw, intent.name)
            if body is None:
                logger.warning(
                    f"[ACIA] {intent.name}: 生成的函数体无法解析\n"
                    f"  原始响应片段: {raw[:300]!r}"
                )
            return body
        except Exception as exc:
            logger.warning(f"[ACIA] {intent.name}: 生成阶段 LLM 调用失败 ({exc})")
            return None

    # ------------------------------------------------------------------
    # Phase A：失败模式分析
    # ------------------------------------------------------------------

    def _analyze_failures(
        self,
        intent: IntentDefinition,
        func_code: str,
        validation: FuncValidation,
    ) -> str:
        """分析失败的测试用例，返回结构化 JSON 分析（失败时返回原始文本）。"""
        if not validation.failures:
            return "（无失败用例）"

        failures_str = _format_failures_for_prompt(validation.failures)
        user_content = ANALYZE_USER_TEMPLATE.format(
            func_code=func_code,
            fail_count=validation.total - validation.passed,
            total_count=validation.total,
            failures_str=failures_str,
        )

        messages = [
            {"role": "system", "content": ANALYZE_SYSTEM},
            {"role": "user", "content": user_content},
        ]

        try:
            raw = self._chat_sync(messages)
            cleaned = re.sub(r"```(?:json)?\s*\n?", "", raw)
            cleaned = re.sub(r"\n?```", "", cleaned).strip()
            # 验证 JSON 合法性
            json.loads(cleaned)
            logger.debug(f"[ACIA] {intent.name}: 失败分析完成")
            return cleaned
        except Exception as exc:
            logger.debug(f"[ACIA] {intent.name}: 失败分析解析异常 ({exc})，使用原始文本")
            return raw[:1000] if raw else "（分析失败）"

    # ------------------------------------------------------------------
    # Phase F：定向修复
    # ------------------------------------------------------------------

    def _repair_body(
        self,
        intent: IntentDefinition,
        schema: ServiceSchema,
        current_code: str,
        validation: FuncValidation,
        failure_analysis: str,
    ) -> Optional[str]:
        """根据失败分析定向修复函数体，返回新函数体（不含 def 行）。"""
        params = list(dict.fromkeys(
            list(intent.required_slots) + list(intent.optional_slots)
        ))
        param_str = ", ".join([f"{p}=None" for p in params]) if params else ""

        # 提取当前函数体（去掉 def 行和 docstring，包括多行 docstring）
        current_body = _extract_function_body(current_code, intent.name) or current_code

        required_return_keys = _build_required_return_keys(intent)
        failures_str = _format_failures_for_prompt(validation.failures)

        user_content = REPAIR_USER_TEMPLATE.format(
            intent_name=intent.name,
            param_str=param_str,
            description=intent.description or intent.name,
            current_body=current_body,
            failure_analysis=failure_analysis,
            fail_count=validation.total - validation.passed,
            total_count=validation.total,
            failures_str=failures_str,
            required_return_keys=required_return_keys,
        )

        messages = [
            {"role": "system", "content": REPAIR_SYSTEM},
            {"role": "user", "content": user_content},
        ]

        try:
            raw = self._chat_sync(messages)
            body = _extract_function_body(raw, intent.name)
            if body is None:
                logger.warning(
                    f"[ACIA] {intent.name}: 修复后函数体无法解析\n"
                    f"  响应片段: {raw[:200]!r}"
                )
            return body
        except Exception as exc:
            logger.warning(f"[ACIA] {intent.name}: 修复阶段 LLM 调用失败 ({exc})")
            return None

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _build_header(self, intent: IntentDefinition) -> str:
        """构建函数 def 行 + docstring 行（不含函数体）。"""
        params = list(dict.fromkeys(
            list(intent.required_slots) + list(intent.optional_slots)
        ))
        param_str = ", ".join([f"{p}=None" for p in params]) if params else ""
        desc = intent.description.replace('"', '\\"') if intent.description else intent.name
        return f'def {intent.name}({param_str}):\n    """{desc}"""'

    def _chat_sync(self, messages: List[Dict[str, str]]) -> str:
        """同步调用 LLM，返回助手消息内容。"""
        if hasattr(self._llm, "chat_sync"):
            return self._llm.chat_sync(messages)
        if hasattr(self._llm, "chat"):
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self._llm.chat(messages))
            finally:
                loop.close()
        raise RuntimeError("LLM client 不支持 chat_sync 或 chat 方法")
