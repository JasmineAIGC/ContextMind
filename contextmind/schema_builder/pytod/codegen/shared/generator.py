"""
基于 LLM 的 PyTOD API 代码生成器（功能二：意图代码生成）。

负责函数体生成（含可选 few-shot 测试用例）与迭代修复，
向后兼容保留对 :func:`clean_llm_function_body` 和 :func:`clean_llm_module` 的再导出。
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from contextmind.infra.logger import get_logger
from contextmind.modes.pytod.schemas import IntentDefinition, ServiceSchema

from contextmind.schema_builder.pytod.codegen.shared.cleaner import (  # noqa: F401  (re-export for backward compat)
    clean_llm_function_body,
    clean_llm_module,
)
from contextmind.schema_builder.pytod.testcase.kb_loader import (
    load_dialogue_samples,
    load_discovery_samples,
    load_sgd_dialogue_samples,
)
from contextmind.schema_builder.pytod.testcase.models import FuncValidation, TestCaseItem
from contextmind.schema_builder.pytod.testcase.prompts import (
    DIALOGUE_CONTEXT_SECTION,
    FUNCTION_GEN_SYSTEM,
    FUNCTION_GEN_USER_TEMPLATE,
    FUNCTION_KB_CONTEXT_SECTION,
    MODULE_GEN_SYSTEM,
    MODULE_GEN_USER_TEMPLATE,
    REPAIR_SYSTEM,
    REPAIR_USER_TEMPLATE,
)
logger = get_logger(__name__)


def _escape_braces(text: str) -> str:
    """Escape ``{`` and ``}`` in *text* so it can be safely used in :meth:`str.format` calls.

    Dynamic content inserted into prompt templates (Python code, JSON data,
    dialogue samples, etc.) may contain ``{key}`` patterns that Python's
    ``str.format()`` would try to interpret as format placeholders, causing
    ``KeyError`` or ``ValueError``.  This helper prevents that by doubling the
    braces: ``{`` → ``{{`` and ``}`` → ``}}``.
    """
    return text.replace("{", "{{").replace("}", "}}")


def _function_def_header(intent: IntentDefinition) -> List[str]:
    """返回函数 def 行 + docstring 行（不含函数体）。"""
    params = list(dict.fromkeys(
        list(intent.required_slots) + list(intent.optional_slots)
    ))
    param_str = ", ".join([f"{p}: Optional[str] = None" for p in params]) if params else ""
    desc = intent.description.replace('"', '\\"') if intent.description else intent.name
    return [
        f"def {intent.name}({param_str}) -> dict:",
        f'    """{desc}"""',
    ]


def enrich_intent_from_test_cases(
    intent: IntentDefinition,
    test_cases: List[TestCaseItem],
) -> IntentDefinition:
    """Return a copy of *intent* with ``required_slots`` / ``result_slots`` merged from *test_cases*.

    Ensures the generated function signature and return dict cover every parameter / key used
    by the test cases, preventing two of the most common pass-rate killers:

    1. **TypeError: unexpected keyword argument** — a test case passes a slot that is not in
       the function signature because the schema only defined a subset of the slots actually
       used in practice.
    2. **Missing return keys** — the function omits a ``result_slot`` that appears in
       ``expected_keys``, failing the key-presence check in :func:`validate_function`.

    The enrichment **always merges** test-case-derived params / result keys with the schema
    definition (union semantics), so existing schema information is preserved while gaps are
    filled automatically.  Specifically:

    - When the schema has *no* ``required_slots`` / ``optional_slots`` at all, all test-case
      params become ``required_slots`` (previous behaviour).
    - When the schema *has* some params, any test-case slots not already present are appended
      as ``optional_slots`` (new behaviour — previously these were silently dropped).
    - ``result_slots`` are always merged: test-case keys not already in the schema list are
      appended, regardless of whether the schema was empty or partially populated.

    Args:
        intent:     The original :class:`IntentDefinition` from the schema.
        test_cases: Pre-built test cases for this intent (Phase 2 output).

    Returns:
        A (possibly new) :class:`IntentDefinition` with ``required_slots``,
        ``optional_slots``, and ``result_slots`` that are supersets of what the test cases
        require.  Returns *intent* unchanged when *test_cases* is empty or when no gap is
        found.
    """
    if not test_cases:
        return intent

    current_params = list(intent.required_slots) + list(intent.optional_slots)
    current_result = list(intent.result_slots)
    current_param_set = set(current_params)
    current_result_set = set(current_result)

    # Derive parameters from the union of all input_slots keys (preserving first-seen order).
    tc_params: List[str] = []
    seen_p: set = set()
    for tc in test_cases:
        for k in tc.input_slots:
            if k not in seen_p:
                seen_p.add(k)
                tc_params.append(k)

    # Derive result keys from the union of all expected_keys (excluding "status").
    tc_result: List[str] = []
    seen_r: set = set()
    for tc in test_cases:
        for k in tc.expected_keys:
            if k != "status" and k not in seen_r:
                seen_r.add(k)
                tc_result.append(k)

    # Compute what the merged signature and result list should look like.
    if not current_params and tc_params:
        # Schema has no params at all: promote all test-case params to required_slots.
        new_required: List[str] = tc_params
        new_optional: List[str] = []
    else:
        # Schema already has params: keep required/optional split and append any extras
        # from test cases as optional_slots (they are legitimate but schema-underdeclared).
        extra_params = [p for p in tc_params if p not in current_param_set]
        new_required = list(intent.required_slots)
        new_optional = list(intent.optional_slots) + extra_params

    # Always merge result_slots: append test-case keys not already declared in the schema.
    extra_results = [r for r in tc_result if r not in current_result_set]
    new_result = current_result + extra_results

    # Only rebuild the dataclass when something actually changed.
    new_all_params = set(new_required + new_optional)
    new_result_set = set(new_result)
    if new_all_params == current_param_set and new_result_set == current_result_set:
        return intent

    return dataclasses.replace(
        intent,
        required_slots=new_required,
        optional_slots=new_optional,
        result_slots=new_result,
    )


class PyTODApiCodeGenerator:
    """使用 LLM 为 PyTOD API 模块生成真实业务逻辑代码。

    支持两种生成模式：

    1. **全模块生成**（推荐，:meth:`generate_module`）：一次 LLM 调用生成整个
       ``*_pytod_apis.py`` 模块，包含所有意图函数。可选传入真实对话数据文件路径
       （``dialogue_data_path``）使 LLM 参考真实业务流程生成更贴近生产环境的代码。

    2. **单函数生成**（:meth:`generate_function_body`）：逐个意图调用 LLM。
       用于 fallback 场景和 Phase 3 的逐函数生成流程。

    Args:
        llm_client: AdkLLMClient 实例。若为 None 则从环境变量加载。
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
    ) -> None:
        if llm_client is None:
            from contextmind.infra.llm_client import AdkLLMClient, LLMConfig
            llm_client = AdkLLMClient(config=LLMConfig.from_env())
        self._llm = llm_client

    # ------------------------------------------------------------------
    # Full-module generation (preferred)
    # ------------------------------------------------------------------

    def generate_module(
        self,
        schema: ServiceSchema,
        dialogue_data_path: Optional[Union[str, Path]] = None,
        max_dialogue_samples: int = 5,
        sgd_dialogue_data_path: Optional[Union[str, Path]] = None,
        discovery_data_path: Optional[Union[str, Path]] = None,
    ) -> Optional[str]:
        """一次 LLM 调用生成整个 ``*_pytod_apis.py`` 模块的函数定义区（不含 import 和工具函数）。

        Args:
            schema: 服务 schema。
            dialogue_data_path: 可选，chat_test_100/500 格式对话数据文件路径。
                传入后 LLM 将参考真实业务流程生成更准确的函数体。
            max_dialogue_samples: 从对话数据中最多取几条样本（避免 prompt 过长）。
            sgd_dialogue_data_path: 可选，dialogues_001.json（SGD 格式）路径。
            discovery_data_path: 可选，discovery_raw.json 路径，提供真实槽位示例。

        Returns:
            包含所有函数定义的 Python 代码字符串，失败时返回 None。
        """
        # 构建意图摘要
        intents_lines: List[str] = []
        for intent in schema.intents:
            params = list(dict.fromkeys(
                list(intent.required_slots) + list(intent.optional_slots)
            ))
            param_str = ", ".join([f"{p}=None" for p in params]) if params else ""
            rs = ", ".join(intent.result_slots) if intent.result_slots else "（无）"
            intents_lines.append(
                f"- def {intent.name}({param_str})  # {intent.description or intent.name}"
            )
            intents_lines.append(f"  result_slots: {rs}")
        intents_summary = "\n".join(intents_lines)

        # 构建槽位摘要
        slot_lines: List[str] = []
        for slot in schema.slots:
            vals = f"  可选值: {', '.join(slot.possible_values)}" if slot.possible_values else ""
            slot_lines.append(f"- {slot.name}: {slot.description}{vals}")
        slots_summary = "\n".join(slot_lines) if slot_lines else "（无槽位）"

        # 构建对话背景章节（dialogue_data_path 优先；其次 sgd_dialogue_data_path）
        dialogue_context_section = ""
        samples: List[str] = []
        if dialogue_data_path:
            samples = load_dialogue_samples(
                dialogue_data_path, max_samples=max_dialogue_samples
            )
        elif sgd_dialogue_data_path:
            samples = load_sgd_dialogue_samples(
                sgd_dialogue_data_path, max_samples=max_dialogue_samples
            )
        if samples:
            formatted = "\n\n".join(
                f"【对话 {i+1}】\n{s}" for i, s in enumerate(samples)
            )
            # 附加 discovery_raw 摘要（若有）
            disc_summary = ""
            if discovery_data_path:
                disc_summary = load_discovery_samples(discovery_data_path)
            if disc_summary:
                formatted += f"\n\n{disc_summary}"
            dialogue_context_section = DIALOGUE_CONTEXT_SECTION.format(
                dialogue_samples=_escape_braces(formatted)
            )
            logger.info(
                f"[PyTODApiCodeGenerator] 已加载 {len(samples)} 条对话样本用于辅助生成"
            )
        elif discovery_data_path:
            # 即便无对话样本，也可以单独注入 discovery 摘要
            disc_summary = load_discovery_samples(discovery_data_path)
            if disc_summary:
                dialogue_context_section = DIALOGUE_CONTEXT_SECTION.format(
                    dialogue_samples=_escape_braces(disc_summary)
                )

        try:
            user_msg = MODULE_GEN_USER_TEMPLATE.format(
                service_name=schema.service_name,
                service_description=schema.description or schema.service_name,
                intents_summary=intents_summary,
                slots_summary=slots_summary,
                dialogue_context_section=dialogue_context_section,
            )
        except (KeyError, ValueError) as exc:
            logger.warning(
                f"[PyTODApiCodeGenerator] generate_module: 构建 prompt 失败 ({exc})，"
                "将回退到规则生成"
            )
            return None

        messages = [
            {"role": "system", "content": MODULE_GEN_SYSTEM},
            {"role": "user", "content": user_msg},
        ]

        try:
            raw = self._chat_sync(messages)
            cleaned = clean_llm_module(raw, schema)
            if cleaned is None:
                logger.warning(
                    "[PyTODApiCodeGenerator] generate_module: LLM 响应无法解析为合法模块，"
                    "将回退到规则生成"
                )
            return cleaned
        except Exception as exc:
            logger.warning(
                f"[PyTODApiCodeGenerator] generate_module: LLM 调用失败 ({exc})，"
                "将回退到规则生成"
            )
            return None

    # ------------------------------------------------------------------
    # Phase 3: Single-function generation with few-shot test cases
    # ------------------------------------------------------------------

    def generate_function_body(
        self,
        intent: IntentDefinition,
        schema: ServiceSchema,
        all_slot_descs: Dict[str, str],
        test_cases: Optional[List[TestCaseItem]] = None,
        dialogue_hint: str = "",
    ) -> Optional[str]:
        """调用 LLM 生成单个意图函数的完整函数体代码（4空格缩进）。

        Args:
            intent: 意图定义。
            schema: 服务 schema。
            all_slot_descs: slot_name → description 映射。
            test_cases: 可选，该意图的测试用例列表（Phase 2 构建）。
                传入后 LLM 将把这些用例当作 few-shot 示例生成更准确的函数体。
            dialogue_hint: 可选，KB 业务背景字符串（由 _prepare_dialogue_hint 构建）。
                传入后 LLM 可参考真实对话数据深入理解意图语义，生成更贴近业务的函数体。

        Returns:
            函数体字符串（可直接拼接到 def 行之后），失败时返回 None。
        """
        params = list(dict.fromkeys(
            list(intent.required_slots) + list(intent.optional_slots)
        ))
        param_str = ", ".join([f"{p}=None" for p in params]) if params else ""

        slot_desc_lines: List[str] = []
        for p in params:
            desc = all_slot_descs.get(p, p)
            slot_desc_lines.append(f"  - {p}: {desc}")
        slot_desc_text = "\n".join(slot_desc_lines) if slot_desc_lines else "  （无输入参数）"

        result_slots_text = (
            "\n".join(f"  - {rs}" for rs in intent.result_slots)
            if intent.result_slots
            else "  （无专用 result_slots，返回输入参数及计算结果即可）"
        )

        # 注入 KB 业务背景章节（仅当有背景数据时）
        kb_context_section = ""
        if dialogue_hint:
            kb_context_section = FUNCTION_KB_CONTEXT_SECTION.format(
                kb_context=_escape_braces(dialogue_hint.rstrip())
            )

        # 从测试用例构建 few-shot 示例章节（含 expected_values 帮助 LLM 校准输出）
        few_shot_section = ""
        if test_cases:
            example_lines = ["## 参考测试用例（few-shot 示例，校准函数对不同对话阶段输入的处理）"]
            for i, tc in enumerate(test_cases[:3], 1):
                ev_hint = ""
                if tc.expected_values:
                    ev_hint = f", 预期关键输出 = {json.dumps(tc.expected_values, ensure_ascii=False)}"
                example_lines.append(
                    f"示例 {i}（{tc.description or '典型输入'}）: "
                    f"输入 = {json.dumps(tc.input_slots, ensure_ascii=False)}{ev_hint}"
                )
            few_shot_section = "\n".join(example_lines) + "\n\n"

        try:
            user_msg = FUNCTION_GEN_USER_TEMPLATE.format(
                service_name=schema.service_name,
                service_description=schema.description or schema.service_name,
                func_name=intent.name,
                param_str=param_str,
                description=intent.description or intent.name,
                slot_descriptions=slot_desc_text,
                result_slots=result_slots_text,
                kb_context_section=kb_context_section,
                few_shot_section=_escape_braces(few_shot_section),
            )
        except (KeyError, ValueError) as exc:
            logger.warning(
                f"[PyTODApiCodeGenerator] {intent.name}: 构建 prompt 失败，回退到规则生成 ({exc})"
            )
            return None

        messages = [
            {"role": "system", "content": FUNCTION_GEN_SYSTEM},
            {"role": "user", "content": user_msg},
        ]

        try:
            raw = self._chat_sync(messages)
            body = clean_llm_function_body(raw, intent.name, param_str)
            if body is None:
                # 记录原始响应前 300 字符，辅助诊断解析失败原因
                logger.warning(
                    f"[PyTODApiCodeGenerator] {intent.name}: LLM 响应无法解析，回退到规则生成\n"
                    f"  响应片段: {raw[:300]!r}"
                )
            return body
        except Exception as exc:
            logger.warning(
                f"[PyTODApiCodeGenerator] {intent.name}: LLM 调用失败 ({exc})，回退到规则生成"
            )
            return None

    # ------------------------------------------------------------------
    # Phase 4: Function repair
    # ------------------------------------------------------------------

    def repair_function(
        self,
        intent: IntentDefinition,
        schema: ServiceSchema,
        all_slot_descs: Dict[str, str],
        current_code: str,
        failures: List[Dict[str, Any]],
        iteration: int,
        total: int = 0,
        passed: int = 0,
        dialogue_hint: str = "",
    ) -> Optional[str]:
        """Phase 4：根据测试失败信息调用 LLM 从语义理解出发重新生成函数体。

        Args:
            intent: 当前意图定义。
            schema: 服务 schema（提供上下文）。
            all_slot_descs: slot_name → description 映射。
            current_code: 当前（失败的）完整函数定义代码。
            failures: 失败用例列表，每条包含 input, expected, actual, error 字段。
            iteration: 当前修复轮次（从 1 开始）。
            total: 总测试用例数（用于显示通过率）。
            passed: 已通过的用例数。
            dialogue_hint: 可选，KB 业务背景字符串（由 _prepare_dialogue_hint 构建）。
                传入后 LLM 可参考真实对话数据重新理解意图语义。

        Returns:
            修复后的完整函数定义代码字符串，失败时返回 None。
        """
        params = list(dict.fromkeys(
            list(intent.required_slots) + list(intent.optional_slots)
        ))
        param_str = ", ".join([f"{p}=None" for p in params]) if params else ""

        rs_desc = "\n".join(
            f"  - {rs}: {all_slot_descs.get(rs, rs)}" for rs in intent.result_slots
        ) or "  （无专用 result_slots，返回输入参数及计算结果即可）"

        # 格式化失败用例（最多 5 条，控制 prompt 长度）
        fail_lines: List[str] = []
        for i, f in enumerate(failures[:5], 1):
            fail_lines.append(
                f"【失败 {i}】描述: {f.get('description', '')}  "
                f"输入: {json.dumps(f.get('input_slots', {}), ensure_ascii=False)}  "
                f"错误: {f.get('error', '返回值格式不符合预期')}"
            )
        pass_rate_str = f"{passed}/{total}" if total > 0 else "未知"

        # 注入 KB 业务背景（若有）
        service_description = schema.description or schema.service_name
        if dialogue_hint:
            service_description = (
                f"{service_description}\n\n## 真实对话业务背景参考\n{dialogue_hint.rstrip()}"
            )

        try:
            user_msg = REPAIR_USER_TEMPLATE.format(
                service_name=schema.service_name,
                service_description=_escape_braces(service_description),
                intent_name=intent.name,
                intent_description=intent.description or intent.name,
                result_slots_desc=rs_desc,
                current_code=_escape_braces(current_code),
                iteration=iteration,
                fail_count=len(failures),
                pass_rate=pass_rate_str,
                failures_text=_escape_braces("\n".join(fail_lines)),
            )
        except (KeyError, ValueError) as exc:
            logger.warning(
                f"[PyTODApiCodeGenerator] {intent.name}: 构建修复 prompt 失败 ({exc})"
            )
            return None

        messages = [
            {"role": "system", "content": REPAIR_SYSTEM},
            {"role": "user", "content": user_msg},
        ]

        try:
            raw = self._chat_sync(messages)
            # 期望收到完整的函数定义
            cleaned = clean_llm_function_body(raw, intent.name, param_str)
            if cleaned is None:
                logger.warning(
                    f"[PyTODApiCodeGenerator] {intent.name}: 修复响应无法解析（轮次 {iteration}）"
                )
                return None
            # 返回完整函数定义（def 行 + 函数体）
            header = "\n".join(_function_def_header(intent))
            return header + "\n" + cleaned
        except Exception as exc:
            logger.warning(
                f"[PyTODApiCodeGenerator] {intent.name}: 修复 LLM 调用失败 ({exc})"
            )
            return None

    # ------------------------------------------------------------------
    # Internal LLM call
    # ------------------------------------------------------------------

    def _chat_sync(self, messages: List[Dict[str, Any]]) -> str:
        """同步调用 LLM chat 接口（兼容有/无运行中事件循环两种场景）。"""
        import asyncio
        import concurrent.futures

        async def _run() -> str:
            return await self._llm.chat_async(messages)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _run())
                return future.result()
        else:
            return asyncio.run(_run())

    # ------------------------------------------------------------------
    # Test case JSON parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_test_cases(
        raw: str,
        intent: IntentDefinition,
    ) -> List[TestCaseItem]:
        """将 LLM 返回的 JSON 文本解析为 ``TestCaseItem`` 列表。"""
        raw = raw.strip()

        # 去除 markdown 代码块标记
        m = re.search(r"```(?:json|python)?\s*([\s\S]+?)\s*```", raw)
        if m:
            raw = m.group(1).strip()

        # 找到 JSON 数组起始位置
        start = raw.find("[")
        end = raw.rfind("]")
        if start == -1 or end == -1:
            return []

        try:
            data = json.loads(raw[start: end + 1])
        except json.JSONDecodeError:
            return []

        if not isinstance(data, list):
            return []

        expected_keys = list(intent.result_slots) + ["status"]
        items: List[TestCaseItem] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            slots = entry.get("input_slots", {})
            if not isinstance(slots, dict):
                continue
            desc = entry.get("description", "")
            # 提取预期计算值（expected_values），用于验证业务逻辑正确性
            ev = entry.get("expected_values", {})
            if not isinstance(ev, dict):
                ev = {}
            items.append(
                TestCaseItem(
                    input_slots=slots,
                    expected_keys=expected_keys,
                    expected_values=ev,
                    description=desc,
                )
            )

        return items

