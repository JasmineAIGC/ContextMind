"""
基于 LLM 的 PyTOD API 代码生成器。

:class:`PyTODApiCodeGenerator` 驱动 plan.md 5 阶段流水线中需要 LLM 的各阶段：

- **Phase 2** (:meth:`~PyTODApiCodeGenerator.build_test_cases`)：
  使用结构化提示词为每个意图生成测试用例。
- **Phase 3** (:meth:`~PyTODApiCodeGenerator.generate_function_body`)：
  可选带 few-shot 测试用例的单函数体生成。
- **Phase 4** (:meth:`~PyTODApiCodeGenerator.repair_function`)：
  迭代修复：根据失败详情重新生成函数体。

LLM 输出清洗辅助函数已迁移至 :mod:`~contextmind.schema_builder.pytod.codegen.shared.cleaner`。
KB 上下文数据加载已迁移至 :mod:`~contextmind.schema_builder.pytod.codegen.shared.kb_loader`。
本模块为向后兼容保留对 :func:`clean_llm_function_body` 和 :func:`clean_llm_module` 的再导出。
"""

from __future__ import annotations

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
from contextmind.schema_builder.pytod.codegen.shared.kb_loader import (
    load_conversion_summary_context,
    load_dialogue_samples,
    load_discovery_samples,
    load_kb_context as _load_kb_context,
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
    TEST_CASE_GEN_SYSTEM,
    TEST_CASE_GEN_USER_TEMPLATE,
)
logger = get_logger(__name__)


def _function_def_header(intent: IntentDefinition) -> List[str]:
    """返回函数 def 行 + docstring 行（不含函数体）。"""
    params = list(dict.fromkeys(
        list(intent.required_slots) + list(intent.optional_slots)
    ))
    param_str = ", ".join([f"{p}=None" for p in params]) if params else ""
    desc = intent.description.replace('"', '\\"') if intent.description else intent.name
    return [
        f"def {intent.name}({param_str}):",
        f'    """{desc}"""',
    ]


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
                dialogue_samples=formatted
            )
            logger.info(
                f"[PyTODApiCodeGenerator] 已加载 {len(samples)} 条对话样本用于辅助生成"
            )
        elif discovery_data_path:
            # 即便无对话样本，也可以单独注入 discovery 摘要
            disc_summary = load_discovery_samples(discovery_data_path)
            if disc_summary:
                dialogue_context_section = DIALOGUE_CONTEXT_SECTION.format(
                    dialogue_samples=disc_summary
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
                kb_context=dialogue_hint.rstrip()
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

        user_msg = FUNCTION_GEN_USER_TEMPLATE.format(
            service_name=schema.service_name,
            service_description=schema.description or schema.service_name,
            func_name=intent.name,
            param_str=param_str,
            description=intent.description or intent.name,
            slot_descriptions=slot_desc_text,
            result_slots=result_slots_text,
            kb_context_section=kb_context_section,
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
    # Phase 2: Test case generation
    # ------------------------------------------------------------------

    def _prepare_dialogue_hint(
        self,
        dialogue_data_path: Optional[Union[str, Path]] = None,
        sgd_dialogue_data_path: Optional[Union[str, Path]] = None,
        discovery_data_path: Optional[Union[str, Path]] = None,
        summary_data_path: Optional[Union[str, Path]] = None,
    ) -> str:
        """构建对话提示字符串（仅需计算一次，供各意图共用）。

        综合利用 KB 输出的 4 个 JSON 文件：
        - dialogues_001.json：真实对话样本（含槽位注解）
        - discovery_raw.json：逐轮槽位提取示例
        - conversion_summary.json：发现的意图/槽位统计摘要
        - chat_test_100/500 格式对话（若提供 dialogue_data_path）

        Args:
            dialogue_data_path: 可选，chat_test_100/500 格式对话数据文件路径。
            sgd_dialogue_data_path: 可选，dialogues_001.json（SGD 格式）路径。
            discovery_data_path: 可选，discovery_raw.json 路径，提供真实槽位示例。
            summary_data_path: 可选，conversion_summary.json 路径，提供发现统计摘要。

        Returns:
            格式化好的对话提示字符串，无数据时返回空字符串。
        """
        hint_parts: List[str] = []

        # 1. 对话样本（优先 chat_test 格式，次之 SGD 格式）
        if dialogue_data_path:
            samples = load_dialogue_samples(dialogue_data_path, max_samples=3)
            if samples:
                formatted = "\n\n".join(f"【对话 {i+1}】\n{s}" for i, s in enumerate(samples))
                hint_parts.append(f"## 真实对话样本（参考提炼多轮对话场景和槽位值）\n{formatted}")
                logger.info(
                    f"[PyTODApiCodeGenerator] 对话数据: 从 {Path(dialogue_data_path).name} 加载 {len(samples)} 条样本"
                )
            else:
                logger.warning(
                    f"[PyTODApiCodeGenerator] 对话数据文件无可用样本，已忽略: {dialogue_data_path}"
                )
        elif sgd_dialogue_data_path:
            samples = load_sgd_dialogue_samples(sgd_dialogue_data_path, max_samples=3)
            if samples:
                formatted = "\n\n".join(f"【对话 {i+1}】\n{s}" for i, s in enumerate(samples))
                hint_parts.append(f"## 真实对话样本（参考提炼多轮对话场景和槽位值）\n{formatted}")
                logger.info(
                    f"[PyTODApiCodeGenerator] 对话数据(SGD): 从 {Path(sgd_dialogue_data_path).name} 加载 {len(samples)} 条样本"
                )
            else:
                logger.warning(
                    f"[PyTODApiCodeGenerator] SGD 对话数据文件无可用样本，已忽略: {sgd_dialogue_data_path}"
                )

        # 2. 逐轮槽位提取示例（discovery_raw.json）
        if discovery_data_path:
            disc_summary = load_discovery_samples(discovery_data_path)
            if disc_summary:
                hint_parts.append(disc_summary)

        # 3. 知识库构建统计摘要（conversion_summary.json）
        if summary_data_path:
            summary_ctx = load_conversion_summary_context(summary_data_path)
            if summary_ctx:
                hint_parts.append(summary_ctx)

        return "\n\n".join(hint_parts) + "\n\n" if hint_parts else ""

    def build_test_cases_for_intent(
        self,
        intent: IntentDefinition,
        schema: ServiceSchema,
        all_slot_descs: Dict[str, str],
        dialogue_hint: str = "",
        max_cases: int = 5,
    ) -> List[TestCaseItem]:
        """Phase 2：为单个意图生成测试用例（LLM 驱动）。

        ``build_test_cases`` 的单意图版本。调用方（builder 逐函数循环）先通过
        :meth:`_prepare_dialogue_hint` 准备好对话提示，再对每个意图单独调用本方法，
        从而实现「一个函数完整处理完再进入下一个」的流式处理。

        Args:
            intent: 当前处理的意图定义。
            schema: 完整服务 schema（用于 service_name、description 等字段）。
            all_slot_descs: 槽位名到描述的映射字典。
            dialogue_hint: 已准备好的对话提示字符串（由 :meth:`_prepare_dialogue_hint` 生成）。
            max_cases: 最多生成的测试用例数。

        Returns:
            ``TestCaseItem`` 列表；生成或解析失败时返回空列表。
        """
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
            max_cases=max_cases,
        )

        messages = [
            {"role": "system", "content": TEST_CASE_GEN_SYSTEM},
            {"role": "user", "content": user_msg},
        ]

        try:
            raw = self._chat_sync(messages)
            cases = self._parse_test_cases(raw, intent)
            if cases:
                logger.info(
                    f"[PyTODApiCodeGenerator] {intent.name}: 生成 {len(cases)} 条测试用例"
                )
                return cases
            else:
                logger.warning(
                    f"[PyTODApiCodeGenerator] {intent.name}: 测试用例解析失败，跳过"
                )
                return []
        except Exception as exc:
            logger.warning(
                f"[PyTODApiCodeGenerator] {intent.name}: 测试用例生成失败 ({exc})"
            )
            return []

    def build_test_cases(
        self,
        schema: ServiceSchema,
        dialogue_data_path: Optional[Union[str, Path]] = None,
        max_cases_per_intent: int = 5,
        discovery_data_path: Optional[Union[str, Path]] = None,
        sgd_dialogue_data_path: Optional[Union[str, Path]] = None,
    ) -> Dict[str, List[TestCaseItem]]:
        """Phase 2：为 schema 中的每个意图生成测试用例（LLM 驱动）。

        每个意图独立调用 LLM，生成 ``max_cases_per_intent`` 条包含真实业务值的
        测试用例。可选传入对话数据文件提供业务背景，使生成的槽位值更贴近真实对话。

        内部调用 :meth:`_prepare_dialogue_hint` 和 :meth:`build_test_cases_for_intent`。
        如需逐函数流式处理，请直接使用这两个方法。

        Args:
            schema: 服务 schema，包含意图和槽位定义。
            dialogue_data_path: 可选，chat_test_100/500 格式对话数据文件路径。
            max_cases_per_intent: 每个意图最多生成的测试用例数。
            discovery_data_path: 可选，discovery_raw.json 路径，提供真实槽位示例。
            sgd_dialogue_data_path: 可选，dialogues_001.json（SGD 格式）路径。

        Returns:
            字典，key 为 intent_name，value 为 ``TestCaseItem`` 列表。
        """
        dialogue_hint = self._prepare_dialogue_hint(
            dialogue_data_path=dialogue_data_path,
            sgd_dialogue_data_path=sgd_dialogue_data_path,
            discovery_data_path=discovery_data_path,
        )
        all_slot_descs: Dict[str, str] = {s.name: s.description for s in schema.slots}
        result: Dict[str, List[TestCaseItem]] = {}

        for intent in schema.intents:
            cases = self.build_test_cases_for_intent(
                intent, schema, all_slot_descs, dialogue_hint, max_cases_per_intent
            )
            if cases:
                result[intent.name] = cases

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

        user_msg = REPAIR_USER_TEMPLATE.format(
            service_name=schema.service_name,
            service_description=service_description,
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
    # Dialogue data loading  (delegated to kb_loader module)
    # ------------------------------------------------------------------

    @staticmethod
    def load_kb_context(
        kb_dir: Union[str, Path],
    ) -> Dict[str, Any]:
        """从 KB 输出目录加载 4 个数据文件的上下文信息。

        .. deprecated::
            直接调用 :func:`contextmind.schema_builder.pytod.codegen.shared.kb_loader.load_kb_context`。
            此静态方法保留仅为向后兼容。

        Returns:
            包含以下键的字典：
            ``dialogues_path``、``discovery_path``、
            ``summary_path``、``schema_path``。
        """
        return _load_kb_context(kb_dir)

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

