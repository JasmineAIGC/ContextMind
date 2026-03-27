"""
LLM-based Python function code generator for *_pytod_apis.py files.

:class:`PyTODApiCodeGenerator` drives the LLM-intensive phases of the
plan.md 5-phase pipeline:

- **Phase 2** (:meth:`~PyTODApiCodeGenerator.build_test_cases`):
  Per-intent test case generation using structured LLM prompts.
- **Phase 3** (:meth:`~PyTODApiCodeGenerator.generate_function_body`):
  Generates a single intent function body with optional few-shot examples.
- **Phase 4** (:meth:`~PyTODApiCodeGenerator.repair_function`):
  Iterative repair: re-generates a function body given failure details.

The module also exports the two LLM-output cleanup helpers used internally:

- :func:`clean_llm_function_body` — extract / normalize a single function body.
- :func:`clean_llm_module` — extract / normalize a full module's function block.
"""

from __future__ import annotations

import ast
import json
import re
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from contextmind.infra.logger import get_logger
from contextmind.modes.pytod.schemas import IntentDefinition, ServiceSchema

from .models import FuncValidation, TestCaseItem
from .prompts import (
    DIALOGUE_CONTEXT_SECTION,
    FUNCTION_GEN_SYSTEM,
    FUNCTION_GEN_USER_TEMPLATE,
    MODULE_GEN_SYSTEM,
    MODULE_GEN_USER_TEMPLATE,
    REPAIR_SYSTEM,
    REPAIR_USER_TEMPLATE,
    TEST_CASE_GEN_SYSTEM,
    TEST_CASE_GEN_USER_TEMPLATE,
)
from .rule_generator import function_def_header

logger = get_logger(__name__)


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
    ) -> Optional[str]:
        """一次 LLM 调用生成整个 ``*_pytod_apis.py`` 模块的函数定义区（不含 import 和工具函数）。

        Args:
            schema: 服务 schema。
            dialogue_data_path: 可选，真实对话数据文件路径（JSON 格式）。
                支持 resources/data/chat_test_100.json 等格式。
                传入后 LLM 将参考真实业务流程生成更准确的函数体。
            max_dialogue_samples: 从对话数据中最多取几条样本（避免 prompt 过长）。

        Returns:
            包含所有函数定义的 Python 代码字符串，失败时返回 None。
        """
        # Build intents summary
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

        # Build slots summary
        slot_lines: List[str] = []
        for slot in schema.slots:
            vals = f"  可选值: {', '.join(slot.possible_values)}" if slot.possible_values else ""
            slot_lines.append(f"- {slot.name}: {slot.description}{vals}")
        slots_summary = "\n".join(slot_lines) if slot_lines else "（无槽位）"

        # Build dialogue context section
        dialogue_context_section = ""
        if dialogue_data_path:
            samples = self._load_dialogue_samples(
                dialogue_data_path, max_samples=max_dialogue_samples
            )
            if samples:
                formatted = "\n\n".join(
                    f"【对话 {i+1}】\n{s}" for i, s in enumerate(samples)
                )
                dialogue_context_section = DIALOGUE_CONTEXT_SECTION.format(
                    dialogue_samples=formatted
                )
                logger.info(
                    f"[PyTODApiCodeGenerator] 已加载 {len(samples)} 条对话样本用于辅助生成"
                )

        user_msg = MODULE_GEN_USER_TEMPLATE.format(
            service_name=schema.service_name,
            service_description=schema.description or schema.service_name,
            intents_summary=intents_summary,
            slots_summary=slots_summary,
            dialogue_context_section=dialogue_context_section,
        )

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
    ) -> Optional[str]:
        """调用 LLM 生成单个意图函数的完整函数体代码（4空格缩进）。

        Args:
            intent: 意图定义。
            schema: 服务 schema。
            all_slot_descs: slot_name → description 映射。
            test_cases: 可选，该意图的测试用例列表（Phase 2 构建）。
                传入后 LLM 将把这些用例当作 few-shot 示例生成更准确的函数体。

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
            else "  （无专用 result_slots，返回输入参数即可）"
        )

        # Build few-shot section from test cases
        few_shot_section = ""
        if test_cases:
            example_lines = ["## 参考测试用例（few-shot 示例，用于校准函数输出）"]
            for i, tc in enumerate(test_cases[:3], 1):
                example_lines.append(
                    f"示例 {i}（{tc.description or '典型输入'}）: "
                    f"输入 = {json.dumps(tc.input_slots, ensure_ascii=False)}"
                )
            few_shot_section = "\n".join(example_lines) + "\n\n"

        user_msg = FUNCTION_GEN_USER_TEMPLATE.format(
            service_name=schema.service_name,
            service_description=schema.description or schema.service_name,
            func_name=intent.name,
            param_str=param_str,
            description=intent.description or intent.name,
            slot_descriptions=slot_desc_text,
            result_slots=result_slots_text,
            few_shot_section=few_shot_section,
        )

        messages = [
            {"role": "system", "content": FUNCTION_GEN_SYSTEM},
            {"role": "user", "content": user_msg},
        ]

        try:
            raw = self._chat_sync(messages)
            body = clean_llm_function_body(raw, intent.name, param_str)
            if body is None:
                logger.warning(
                    f"[PyTODApiCodeGenerator] {intent.name}: LLM 响应无法解析，回退到规则生成"
                )
            return body
        except Exception as exc:
            logger.warning(
                f"[PyTODApiCodeGenerator] {intent.name}: LLM 调用失败 ({exc})，回退到规则生成"
            )
            return None

    # ------------------------------------------------------------------
    # Phase 2: Test case generation
    # ------------------------------------------------------------------

    def build_test_cases(
        self,
        schema: ServiceSchema,
        dialogue_data_path: Optional[Union[str, Path]] = None,
        max_cases_per_intent: int = 5,
    ) -> Dict[str, List[TestCaseItem]]:
        """Phase 2：为 schema 中的每个意图生成测试用例（LLM 驱动）。

        每个意图独立调用 LLM，生成 ``max_cases_per_intent`` 条包含真实业务值的
        测试用例。可选传入对话数据文件提供业务背景，使生成的槽位值更贴近真实对话。

        Args:
            schema: 服务 schema，包含意图和槽位定义。
            dialogue_data_path: 可选，真实对话数据文件路径（提供业务背景）。
            max_cases_per_intent: 每个意图最多生成的测试用例数。

        Returns:
            字典，key 为 intent_name，value 为 ``TestCaseItem`` 列表。
        """
        # Load dialogue hint (brief context, not the full samples)
        dialogue_hint = ""
        if dialogue_data_path:
            samples = self._load_dialogue_samples(dialogue_data_path, max_samples=2)
            if samples:
                brief = samples[0][:300]
                dialogue_hint = f"## 真实对话片段（参考提炼真实槽位值）\n{brief}\n\n"

        all_slot_descs: Dict[str, str] = {s.name: s.description for s in schema.slots}
        result: Dict[str, List[TestCaseItem]] = {}

        for intent in schema.intents:
            params_req = list(intent.required_slots)
            params_opt = list(intent.optional_slots)
            params_all = list(dict.fromkeys(params_req + params_opt))
            param_str = ", ".join([f"{p}=None" for p in params_all]) if params_all else ""

            req_desc = "\n".join(
                f"  - {p}: {all_slot_descs.get(p, p)}" for p in params_req
            ) or "  （无必填槽位）"
            opt_desc = "\n".join(
                f"  - {p}: {all_slot_descs.get(p, p)}" for p in params_opt
            ) or "  （无可选槽位）"
            rs_desc = "\n".join(
                f"  - {rs}" for rs in intent.result_slots
            ) or "  （无 result_slots，返回输入参数即可）"

            user_msg = TEST_CASE_GEN_USER_TEMPLATE.format(
                service_name=schema.service_name,
                service_description=schema.description or schema.service_name,
                intent_name=intent.name,
                intent_description=intent.description or intent.name,
                func_name=intent.name,
                param_str=param_str,
                required_slots_desc=req_desc,
                optional_slots_desc=opt_desc,
                result_slots_desc=rs_desc,
                dialogue_hint=dialogue_hint,
                max_cases=max_cases_per_intent,
            )

            messages = [
                {"role": "system", "content": TEST_CASE_GEN_SYSTEM},
                {"role": "user", "content": user_msg},
            ]

            try:
                raw = self._chat_sync(messages)
                cases = self._parse_test_cases(raw, intent)
                if cases:
                    result[intent.name] = cases
                    logger.info(
                        f"[PyTODApiCodeGenerator] {intent.name}: 生成 {len(cases)} 条测试用例"
                    )
                else:
                    logger.warning(
                        f"[PyTODApiCodeGenerator] {intent.name}: 测试用例解析失败，跳过"
                    )
            except Exception as exc:
                logger.warning(
                    f"[PyTODApiCodeGenerator] {intent.name}: 测试用例生成失败 ({exc})"
                )

        logger.info(
            f"[PyTODApiCodeGenerator] 测试用例构建完成: "
            f"{len(result)}/{len(schema.intents)} 个意图有测试用例"
        )
        return result

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
    ) -> Optional[str]:
        """Phase 4：根据测试失败信息调用 LLM 修复函数体。

        Args:
            intent: 当前意图定义。
            schema: 服务 schema（提供上下文）。
            all_slot_descs: slot_name → description 映射。
            current_code: 当前（失败的）完整函数定义代码。
            failures: 失败用例列表，每条包含 input, expected, actual, error 字段。
            iteration: 当前修复轮次（从 1 开始）。
            total: 总测试用例数（用于显示通过率）。
            passed: 已通过的用例数。

        Returns:
            修复后的完整函数定义代码字符串，失败时返回 None。
        """
        params = list(dict.fromkeys(
            list(intent.required_slots) + list(intent.optional_slots)
        ))
        param_str = ", ".join([f"{p}=None" for p in params]) if params else ""

        rs_desc = "\n".join(
            f"  - {rs}: {all_slot_descs.get(rs, rs)}" for rs in intent.result_slots
        ) or "  （无专用 result_slots，返回输入参数即可）"

        # Format failure cases (limit to 5 for prompt length)
        fail_lines: List[str] = []
        for i, f in enumerate(failures[:5], 1):
            fail_lines.append(
                f"【失败 {i}】描述: {f.get('description', '')}  "
                f"输入: {json.dumps(f.get('input_slots', {}), ensure_ascii=False)}  "
                f"错误: {f.get('error', '返回值格式不符合预期')}"
            )
        pass_rate_str = f"{passed}/{total}" if total > 0 else "未知"

        user_msg = REPAIR_USER_TEMPLATE.format(
            service_name=schema.service_name,
            intent_name=intent.name,
            intent_description=intent.description or intent.name,
            result_slots_desc=rs_desc,
            current_code=current_code,
            iteration=iteration,
            fail_count=len(failures),
            pass_rate=pass_rate_str,
            failures_text="\n".join(fail_lines),
        )

        messages = [
            {"role": "system", "content": REPAIR_SYSTEM},
            {"role": "user", "content": user_msg},
        ]

        try:
            raw = self._chat_sync(messages)
            # Expect a full function definition
            cleaned = clean_llm_function_body(raw, intent.name, param_str)
            if cleaned is None:
                logger.warning(
                    f"[PyTODApiCodeGenerator] {intent.name}: 修复响应无法解析（轮次 {iteration}）"
                )
                return None
            # Return as full function definition (header + body)
            header = "\n".join(function_def_header(intent))
            return header + "\n" + cleaned
        except Exception as exc:
            logger.warning(
                f"[PyTODApiCodeGenerator] {intent.name}: 修复 LLM 调用失败 ({exc})"
            )
            return None

    # ------------------------------------------------------------------
    # Dialogue data loading
    # ------------------------------------------------------------------

    @staticmethod
    def _load_dialogue_samples(
        data_path: Union[str, Path],
        max_samples: int = 5,
    ) -> List[str]:
        """从对话数据文件中加载并格式化对话样本。

        支持以下 JSON 格式：
        - ``[{"session_id":..., "用户信息":..., "对话历史":[{"机器人":..., "用户":...},...]}]``
          （chat_test_100.json 格式）
        - ``[{"label":..., "query":{"用户信息":..., "对话历史":[...]}}]``
          （chat_test_500.json 格式）

        Returns:
            格式化后的对话文本列表（每条为一个对话的字符串表示）。
        """
        try:
            path = Path(data_path)
            if not path.exists():
                logger.warning(f"[PyTODApiCodeGenerator] 对话数据文件不存在: {path}")
                return []

            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)

            if not isinstance(data, list) or not data:
                return []

            samples: List[str] = []
            for item in data:
                if len(samples) >= max_samples:
                    break

                # Determine format and extract fields
                if "query" in item:
                    # chat_test_500 format: {label, query:{用户信息, 对话历史}}
                    q = item["query"]
                    user_info = q.get("用户信息", "")
                    history = q.get("对话历史", [])
                else:
                    # chat_test_100 format: {session_id, 用户信息, 对话历史}
                    user_info = item.get("用户信息", "")
                    history = item.get("对话历史", [])

                if not history:
                    continue

                lines: List[str] = []
                # Include a brief user info excerpt (first 3 fields)
                if user_info:
                    brief = "、".join(user_info.split("#")[1:4])
                    lines.append(f"[用户信息] {brief}")

                # Format dialogue turns
                for turn in history[:8]:  # limit to first 8 turns
                    if isinstance(turn, dict):
                        for speaker, text in turn.items():
                            lines.append(f"{speaker}：{text[:80]}")
                    elif isinstance(turn, str):
                        lines.append(turn[:100])

                if lines:
                    samples.append("\n".join(lines))

            return samples

        except Exception as exc:
            logger.warning(f"[PyTODApiCodeGenerator] 加载对话数据失败: {exc}")
            return []

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

        # Strip markdown code fences
        m = re.search(r"```(?:json|python)?\s*([\s\S]+?)\s*```", raw)
        if m:
            raw = m.group(1).strip()

        # Find first '[' — JSON array
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
            items.append(
                TestCaseItem(
                    input_slots=slots,
                    expected_keys=expected_keys,
                    description=desc,
                )
            )

        return items


# ---------------------------------------------------------------------------
# LLM output cleanup helpers
# ---------------------------------------------------------------------------

def clean_llm_function_body(raw: str, func_name: str, param_str: str) -> Optional[str]:
    """从 LLM 响应中提取并验证函数体代码。

    处理以下常见情况：
    - LLM 返回了完整的函数定义（包含 def 行）
    - LLM 用 markdown 代码块包裹了输出
    - LLM 在函数体前后有多余文字

    Returns:
        经过验证的 4 空格缩进函数体字符串，或 None（无法解析）。
    """
    # Strip markdown code fences
    raw = raw.strip()
    m = re.search(r"```(?:python)?\s*([\s\S]+?)\s*```", raw)
    if m:
        raw = m.group(1).strip()

    # If LLM included the def line, extract just the body
    if raw.startswith("def "):
        # Parse as full function, extract body
        try:
            tree = ast.parse(raw)
            func_def = None
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    func_def = node
                    break
            if func_def:
                lines = raw.splitlines()
                body_start = func_def.body[0].lineno - 1
                body_lines = lines[body_start:]
                raw = textwrap.dedent("\n".join(body_lines))
        except SyntaxError:
            pass

    # Normalize indentation to 4 spaces
    lines = raw.splitlines()
    if lines:
        raw = textwrap.dedent("\n".join(lines))

    # Ensure 4-space indent by re-indenting (empty lines remain empty)
    indented_lines = ["    " + line if line.strip() else "" for line in raw.splitlines()]
    body = "\n".join(indented_lines)

    # Validate: wrap in a function def and parse
    full_src = f"def {func_name}({param_str}):\n{body}\n"
    try:
        ast.parse(full_src)
    except SyntaxError as exc:
        logger.debug(f"[clean_llm_function_body] SyntaxError for {func_name}: {exc}")
        return None

    return body


def clean_llm_module(raw: str, schema: ServiceSchema) -> Optional[str]:
    """从 LLM 响应中提取并验证完整模块的函数定义区。

    处理 markdown 代码块、多余说明文字、重复工具函数定义等常见问题。

    Returns:
        包含所有函数定义的 Python 代码字符串，或 None（无法解析为合法 Python）。
    """
    raw = raw.strip()

    # Strip markdown code fences
    m = re.search(r"```(?:python)?\s*([\s\S]+?)\s*```", raw)
    if m:
        raw = m.group(1).strip()

    # Remove any re-definition of shared helpers that LLM shouldn't emit
    helper_names = ("_parse_amount", "_ticket_id", "_calc_monthly_payment", "_next_work_day")
    lines = raw.splitlines()
    filtered: List[str] = []
    skip_block = False
    for line in lines:
        stripped = line.strip()
        # Detect start of a helper function re-definition
        if stripped.startswith("def ") and any(
            stripped.startswith(f"def {h}") for h in helper_names
        ):
            skip_block = True
        # Detect INTENT_REGISTRY block (we generate it ourselves)
        elif stripped.startswith("INTENT_REGISTRY"):
            skip_block = True
        elif skip_block and stripped and not stripped.startswith(" ") and not stripped.startswith("\t"):
            skip_block = False

        if not skip_block:
            filtered.append(line)

    raw = "\n".join(filtered).strip()

    # Find where the first 'def ' function starts (skip any leading prose)
    first_def = re.search(r"^def ", raw, re.MULTILINE)
    if first_def:
        raw = raw[first_def.start():]

    # Validate as Python source
    minimal_preamble = "from __future__ import annotations\n"
    try:
        ast.parse(minimal_preamble + raw)
    except SyntaxError as exc:
        logger.debug(f"[clean_llm_module] SyntaxError: {exc}")
        return None

    # Warn if any expected intent functions are missing
    expected = {intent.name for intent in schema.intents}
    found = set(re.findall(r"^def (\w+)\(", raw, re.MULTILINE))
    missing = expected - found
    if missing:
        logger.warning(
            f"[clean_llm_module] LLM 生成的模块缺少以下函数: {missing}"
        )

    return raw
