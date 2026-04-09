"""
测试用例生成器（LLM 驱动）。

:class:`TestCaseGenerator` 负责功能一「预生成测试数据」的 LLM 调用层：
为 schema 中的每个意图生成覆盖多种场景的测试用例，保存到 ``*_test_cases.json``，
供功能二中 4 种代码生成算法共享使用。

调用顺序::

    gen = TestCaseGenerator(llm_client=llm_client)
    kb_ctx = TestCaseGenerator.load_kb_context(kb_dir)
    dialogue_hint = gen._prepare_dialogue_hint(
        sgd_dialogue_data_path=kb_ctx["dialogues_path"],
        discovery_data_path=kb_ctx["discovery_path"],
        summary_data_path=kb_ctx["summary_path"],
    )
    for intent in schema.intents:
        cases = gen.build_test_cases_for_intent(
            intent, schema, all_slot_descs, dialogue_hint, max_cases=10
        )
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from contextmind.infra.logger import get_logger
from contextmind.modes.pytod.schemas import IntentDefinition, ServiceSchema

from contextmind.schema_builder.pytod.testcase.kb_loader import (
    load_conversion_summary_context,
    load_dialogue_samples,
    load_discovery_samples,
    load_kb_context as _load_kb_context,
    load_sgd_dialogue_samples,
)
from contextmind.schema_builder.pytod.testcase.models import TestCaseItem
from contextmind.schema_builder.pytod.testcase.prompts import (
    TEST_CASE_GEN_SYSTEM,
    TEST_CASE_GEN_USER_TEMPLATE,
)

logger = get_logger(__name__)


class TestCaseGenerator:
    """使用 LLM 为 PyTOD 意图生成测试用例（功能一：预生成测试数据）。

    本类只做一件事：给定 schema 中的意图定义，调用 LLM 生成覆盖多种场景的
    测试用例（``TestCaseItem`` 列表）。生成的测试用例由功能二（codegen）中的
    4 种算法在运行时加载，用于验证生成的函数代码正确性。

    Args:
        llm_client: AdkLLMClient 实例。若为 None 则从环境变量自动加载。
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
    # KB 上下文加载（静态）
    # ------------------------------------------------------------------

    @staticmethod
    def load_kb_context(
        kb_dir: Union[str, Path],
    ) -> Dict[str, Any]:
        """从 KB 输出目录扫描数据文件路径。

        封装 :func:`~contextmind.schema_builder.pytod.testcase.kb_loader.load_kb_context`，
        返回包含各文件路径的字典，供 :meth:`_prepare_dialogue_hint` 使用。

        Args:
            kb_dir: KB 输出目录（由 KnowledgeBaseBuilder.save_dataset() 生成）。

        Returns:
            包含以下键的字典（文件不存在时对应值为 None）：
            ``dialogues_path``、``discovery_path``、``summary_path``、``schema_path``。
        """
        return _load_kb_context(kb_dir)

    # ------------------------------------------------------------------
    # 对话提示构建
    # ------------------------------------------------------------------

    def _prepare_dialogue_hint(
        self,
        dialogue_data_path: Optional[Union[str, Path]] = None,
        sgd_dialogue_data_path: Optional[Union[str, Path]] = None,
        discovery_data_path: Optional[Union[str, Path]] = None,
        summary_data_path: Optional[Union[str, Path]] = None,
    ) -> str:
        """构建对话业务背景提示字符串（仅需计算一次，供各意图共用）。

        综合利用 KB 输出的 4 个 JSON 文件：

        - ``dialogues_001.json``      — 真实对话样本（含槽位注解）
        - ``discovery_raw.json``      — 逐轮槽位提取示例
        - ``conversion_summary.json`` — 发现的意图/槽位统计摘要
        - chat_test_100/500 格式对话（若提供 dialogue_data_path）

        Args:
            dialogue_data_path:     可选，chat_test_100/500 格式对话数据文件路径。
            sgd_dialogue_data_path: 可选，dialogues_001.json（SGD 格式）路径。
            discovery_data_path:    可选，discovery_raw.json 路径，提供真实槽位示例。
            summary_data_path:      可选，conversion_summary.json 路径，提供发现统计摘要。

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
                    f"[TestCaseGenerator] 对话数据: 从 {Path(dialogue_data_path).name} 加载 {len(samples)} 条样本"
                )
            else:
                logger.warning(
                    f"[TestCaseGenerator] 对话数据文件无可用样本，已忽略: {dialogue_data_path}"
                )
        elif sgd_dialogue_data_path:
            samples = load_sgd_dialogue_samples(sgd_dialogue_data_path, max_samples=3)
            if samples:
                formatted = "\n\n".join(f"【对话 {i+1}】\n{s}" for i, s in enumerate(samples))
                hint_parts.append(f"## 真实对话样本（参考提炼多轮对话场景和槽位值）\n{formatted}")
                logger.info(
                    f"[TestCaseGenerator] 对话数据(SGD): 从 {Path(sgd_dialogue_data_path).name} 加载 {len(samples)} 条样本"
                )
            else:
                logger.warning(
                    f"[TestCaseGenerator] SGD 对话数据文件无可用样本，已忽略: {sgd_dialogue_data_path}"
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

    # ------------------------------------------------------------------
    # Phase 2: 测试用例生成
    # ------------------------------------------------------------------

    def build_test_cases_for_intent(
        self,
        intent: IntentDefinition,
        schema: ServiceSchema,
        all_slot_descs: Dict[str, str],
        dialogue_hint: str = "",
        max_cases: int = 5,
    ) -> List[TestCaseItem]:
        """为单个意图生成测试用例（LLM 驱动）。

        调用方（builder 逐函数循环）先通过 :meth:`_prepare_dialogue_hint` 准备好对话提示，
        再对每个意图单独调用本方法，从而实现「一个函数完整处理完再进入下一个」的流式处理。

        Args:
            intent:         当前处理的意图定义。
            schema:         完整服务 schema（用于 service_name、description 等字段）。
            all_slot_descs: 槽位名到描述的映射字典。
            dialogue_hint:  已准备好的对话提示字符串（由 :meth:`_prepare_dialogue_hint` 生成）。
            max_cases:      最多生成的测试用例数。

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
                    f"[TestCaseGenerator] {intent.name}: 生成 {len(cases)} 条测试用例"
                )
                return cases
            else:
                logger.warning(
                    f"[TestCaseGenerator] {intent.name}: 测试用例解析失败，跳过"
                )
                return []
        except Exception as exc:
            logger.warning(
                f"[TestCaseGenerator] {intent.name}: 测试用例生成失败 ({exc})"
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
        """为 schema 中的每个意图生成测试用例（LLM 驱动，批量版本）。

        每个意图独立调用 LLM，生成 ``max_cases_per_intent`` 条包含真实业务值的
        测试用例。可选传入对话数据文件提供业务背景，使生成的槽位值更贴近真实对话。

        内部调用 :meth:`_prepare_dialogue_hint` 和 :meth:`build_test_cases_for_intent`。
        如需逐函数流式处理，请直接使用这两个方法。

        Args:
            schema:                  服务 schema，包含意图和槽位定义。
            dialogue_data_path:      可选，chat_test_100/500 格式对话数据文件路径。
            max_cases_per_intent:    每个意图最多生成的测试用例数。
            discovery_data_path:     可选，discovery_raw.json 路径，提供真实槽位示例。
            sgd_dialogue_data_path:  可选，dialogues_001.json（SGD 格式）路径。

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
            f"[TestCaseGenerator] 测试用例构建完成: "
            f"{len(result)}/{len(schema.intents)} 个意图有测试用例"
        )
        return result

    # ------------------------------------------------------------------
    # LLM 调用与结果解析（私有）
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
