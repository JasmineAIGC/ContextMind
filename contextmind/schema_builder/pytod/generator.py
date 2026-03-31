"""
基于 LLM 的 PyTOD API 代码生成器。

:class:`PyTODApiCodeGenerator` 驱动 plan.md 5 阶段流水线中需要 LLM 的各阶段：

- **Phase 2** (:meth:`~PyTODApiCodeGenerator.build_test_cases`)：
  使用结构化提示词为每个意图生成测试用例。
- **Phase 3** (:meth:`~PyTODApiCodeGenerator.generate_function_body`)：
  可选带 few-shot 测试用例的单函数体生成。
- **Phase 4** (:meth:`~PyTODApiCodeGenerator.repair_function`)：
  迭代修复：根据失败详情重新生成函数体。

本模块还导出两个 LLM 输出清洗辅助函数：

- :func:`clean_llm_function_body` — 提取并规范化单个函数体。
- :func:`clean_llm_module` — 提取并规范化完整模块的函数定义区。
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

from contextmind.schema_builder.pytod.models import FuncValidation, TestCaseItem
from contextmind.schema_builder.pytod.prompts import (
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
from contextmind.schema_builder.pytod.rule_generator import function_def_header

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
            samples = self._load_dialogue_samples(
                dialogue_data_path, max_samples=max_dialogue_samples
            )
        elif sgd_dialogue_data_path:
            samples = self._load_sgd_dialogue_samples(
                sgd_dialogue_data_path, max_samples=max_dialogue_samples
            )
        if samples:
            formatted = "\n\n".join(
                f"【对话 {i+1}】\n{s}" for i, s in enumerate(samples)
            )
            # 附加 discovery_raw 摘要（若有）
            disc_summary = ""
            if discovery_data_path:
                disc_summary = self._load_discovery_samples(discovery_data_path)
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
            disc_summary = self._load_discovery_samples(discovery_data_path)
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

        # 从测试用例构建 few-shot 示例章节
        few_shot_section = ""
        if test_cases:
            example_lines = ["## 参考测试用例（few-shot 示例，校准函数对不同对话阶段输入的处理）"]
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
            samples = self._load_dialogue_samples(dialogue_data_path, max_samples=3)
            if samples:
                formatted = "\n\n".join(f"【对话 {i+1}】\n{s}" for i, s in enumerate(samples))
                hint_parts.append(f"## 真实对话样本（参考提炼多轮对话场景和槽位值）\n{formatted}")
        elif sgd_dialogue_data_path:
            samples = self._load_sgd_dialogue_samples(sgd_dialogue_data_path, max_samples=3)
            if samples:
                formatted = "\n\n".join(f"【对话 {i+1}】\n{s}" for i, s in enumerate(samples))
                hint_parts.append(f"## 真实对话样本（参考提炼多轮对话场景和槽位值）\n{formatted}")

        # 2. 逐轮槽位提取示例（discovery_raw.json）
        if discovery_data_path:
            disc_summary = self._load_discovery_samples(discovery_data_path)
            if disc_summary:
                hint_parts.append(disc_summary)

        # 3. 知识库构建统计摘要（conversion_summary.json）
        if summary_data_path:
            summary_ctx = self._load_conversion_summary_context(summary_data_path)
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

                # 判断对话数据格式并提取字段
                if "query" in item:
                    # chat_test_500 格式：{label, query:{用户信息, 对话历史}}
                    q = item["query"]
                    user_info = q.get("用户信息", "")
                    history = q.get("对话历史", [])
                else:
                    # chat_test_100 格式：{session_id, 用户信息, 对话历史}
                    user_info = item.get("用户信息", "")
                    history = item.get("对话历史", [])

                if not history:
                    continue

                lines: List[str] = []
                # 截取用户信息前 3 个字段摘要
                if user_info:
                    brief = "、".join(user_info.split("#")[1:4])
                    lines.append(f"[用户信息] {brief}")

                # 格式化对话轮次
                for turn in history[:8]:  # 最多取前 8 轮
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

    @staticmethod
    def _load_sgd_dialogue_samples(
        data_path: Union[str, Path],
        max_samples: int = 5,
    ) -> List[str]:
        """从 SGD 格式的 dialogues_001.json 加载并格式化对话样本。

        SGD 格式：``[{"dialogue_id":..., "services":[...], "turns":[{"speaker":..., "utterance":...,
        "frames":[{"service":..., "slots":[...], "state":{"slot_values":{...}}}]}]}]``

        除对话文本外，还会提取 ``frames.state.slot_values`` 中的实际槽位值，
        帮助 LLM 了解多轮对话中槽位的积累过程。

        Returns:
            格式化后的对话文本列表（每条包含对话内容和槽位状态快照）。
        """
        try:
            path = Path(data_path)
            if not path.exists():
                logger.warning(f"[PyTODApiCodeGenerator] SGD 对话文件不存在: {path}")
                return []
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, list) or not data:
                return []
            samples: List[str] = []
            for item in data:
                if len(samples) >= max_samples:
                    break
                turns = item.get("turns", [])
                if not turns:
                    continue
                lines: List[str] = []
                # 记录最后一次出现的 slot_values 快照（反映多轮积累结果）
                slot_snapshots: List[str] = []
                for turn in turns[:12]:
                    speaker = turn.get("speaker", "")
                    utterance = turn.get("utterance", "")
                    # SGD 中机器人说话者标签为 SYSTEM，用户为 USER
                    label = "机器人" if speaker.upper() in ("SYSTEM", "机器人") else "用户"
                    lines.append(f"{label}：{utterance[:80]}")
                    # 提取该轮的槽位值快照（USER 轮次 frames 中的 state.slot_values）
                    if speaker.upper() in ("USER", "用户"):
                        for frame in turn.get("frames", []):
                            state = frame.get("state", {})
                            sv = state.get("slot_values", {})
                            if sv:
                                sv_str = "、".join(
                                    f"{k}={v[0] if isinstance(v, list) else v}"
                                    for k, v in list(sv.items())[:6]
                                )
                                slot_snapshots.append(f"  [已收集槽位: {sv_str}]")
                # 在对话末尾附加槽位快照（展示多轮积累的槽位状态）
                if slot_snapshots:
                    lines.append(slot_snapshots[-1])  # 只展示最终状态，避免过长
                if lines:
                    samples.append("\n".join(lines))
            return samples
        except Exception as exc:
            logger.warning(f"[PyTODApiCodeGenerator] 加载 SGD 对话数据失败: {exc}")
            return []

    @staticmethod
    def _load_discovery_samples(
        data_path: Union[str, Path],
        max_items: int = 25,
    ) -> str:
        """从 discovery_raw.json 提取真实槽位示例，格式化为 LLM 可读的摘要。

        discovery_raw.json 格式：
        ``[{"dialogue_id":..., "turns":[{"turn_idx":..., "speaker":..., "utterance":...,
            "extractions":[{"extraction_class":..., "label":..., "value":...}]}]}]``

        提取所有 extraction_class 类型（intent、slot、slot_value、fact）中的标签和值，
        为 LLM 提供更丰富的真实业务数据示例。

        Returns:
            格式化后的槽位示例摘要字符串（空时返回空字符串）。
        """
        try:
            path = Path(data_path)
            if not path.exists():
                return ""
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, list):
                return ""
            # 收集所有有 extractions 的轮次中的意图/槽位/事实示例
            examples: Dict[str, List[str]] = {}
            count = 0
            for item in data:
                for turn in item.get("turns", []):
                    for ext in turn.get("extractions", []):
                        label = ext.get("label", "")
                        value = ext.get("value", "")
                        cls = ext.get("extraction_class", "")
                        # 覆盖所有有意义的提取类型
                        if label and value and cls in ("intent", "slot", "slot_value", "fact"):
                            examples.setdefault(label, [])
                            if value not in examples[label]:
                                examples[label].append(value)
                                count += 1
                    if count >= max_items * 3:
                        break
                if count >= max_items * 3:
                    break
            if not examples:
                return ""
            lines = ["## 真实对话中提取到的槽位/意图示例（参考生成真实业务值）"]
            for label, values in list(examples.items())[:max_items]:
                sample_vals = "、".join(str(v)[:60] for v in values[:3])
                lines.append(f"- {label}：{sample_vals}")
            return "\n".join(lines)
        except Exception as exc:
            logger.warning(f"[PyTODApiCodeGenerator] 加载 discovery_raw 失败: {exc}")
            return ""

    @staticmethod
    def _load_conversion_summary_context(
        data_path: Union[str, Path],
    ) -> str:
        """从 conversion_summary.json 提取发现的意图/槽位统计，格式化为 LLM 可读摘要。

        conversion_summary.json 格式（由 KnowledgeBaseBuilder.save_dataset() 生成）：
        ``{"output_dir":..., "dialogues":N, "turns":N, "schema_coverage":
           {"extracted_slots":[...], "extracted_intents":[...]}, ...}``

        Returns:
            格式化后的统计摘要字符串（空时返回空字符串）。
        """
        try:
            path = Path(data_path)
            if not path.exists():
                return ""
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                return ""
            lines: List[str] = ["## 知识库构建统计（来自 conversion_summary）"]
            n_dlg = data.get("dialogues", "?")
            n_turns = data.get("turns", "?")
            lines.append(f"- 对话数: {n_dlg}，总轮次: {n_turns}")
            coverage = data.get("schema_coverage", {})
            extracted_intents: List[str] = coverage.get("extracted_intents", [])
            extracted_slots: List[str] = coverage.get("extracted_slots", [])
            if extracted_intents:
                shown = "、".join(extracted_intents[:20])
                lines.append(
                    f"- 从真实对话中发现的意图（共 {len(extracted_intents)} 个）: {shown}"
                )
            if extracted_slots:
                shown = "、".join(extracted_slots[:20])
                lines.append(
                    f"- 从真实对话中发现的槽位（共 {len(extracted_slots)} 个）: {shown}"
                )
            return "\n".join(lines)
        except Exception as exc:
            logger.warning(f"[PyTODApiCodeGenerator] 加载 conversion_summary 失败: {exc}")
            return ""

    @staticmethod
    def load_kb_context(
        kb_dir: Union[str, Path],
    ) -> Dict[str, Any]:
        """从 KB 输出目录加载 4 个数据文件的上下文信息。

        KB 输出目录（由 :func:`contextmind.knowledge.KnowledgeBaseBuilder.save_dataset` 生成）
        中包含以下文件（全部可选，缺失时跳过）：

        - ``schema.json``         — 服务 schema（意图/槽位定义）
        - ``dialogues_001.json``  — SGD 格式的处理后对话
        - ``discovery_raw.json``  — 逐轮槽位提取原始数据
        - ``conversion_summary.json`` — 转换摘要统计

        Returns:
            包含以下键的字典：
            ``dialogues_path``  (Path|None)、``discovery_path``  (Path|None)、
            ``summary_path``    (Path|None)、``schema_path``     (Path|None)。
        """
        kb_dir = Path(kb_dir)
        def _find(name: str) -> Optional[Path]:
            p = kb_dir / name
            return p if p.exists() else None

        return {
            "dialogues_path": _find("dialogues_001.json"),
            "discovery_path": _find("discovery_raw.json"),
            "summary_path": _find("conversion_summary.json"),
            "schema_path": _find("schema.json"),
        }

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
        # 无 def 行 —— LLM 直接输出函数体。
        # 修复 LLM 常见 quirk：第一个语句行缺少前导缩进，其余行均有 4 空格缩进。
        # 若检测到该模式，将第一行补齐到其余行的最小缩进级别，
        # 使后续 textwrap.dedent 能正确归一化所有行。
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
