"""
通用知识库构建器

将任意对话数据集经过两步处理，输出标准 SGD 格式 ``schema.json``：

1. **发现阶段**（Discovery）：
   使用 LLM 以"开放式提取"模式扫描样本对话，自动发现所有出现过的
   槽位（slots）和意图（intents）。利用已有的
   :class:`~contextmind.scenarios.anyihua.knowledge_extraction.AnyihuaKnowledgeExtractor`
   实现（传入空 schema + open_ended=True）。

2. **合成阶段**（Synthesis）：
   将发现阶段收集到的槽位/意图计数及样本，调用 LLM 第二次，
   输出规范化的 SGD ServiceSchema JSON。

输出的 ``schema.json`` 格式与 ``data/anyihua_sgd/schema.json`` 完全兼容，
可直接传入 :class:`~contextmind.modes.pytod.AdkPyTODTracker` 使用。

典型用法::

    import json
    from pathlib import Path
    from contextmind.kb import KnowledgeBaseBuilder

    dialogues = json.loads(Path("my_dialogues.json").read_text())

    builder = KnowledgeBaseBuilder(
        scene_name="银行贷款外呼",
        scene_description="银行客服主动致电老客户推介个人贷款产品",
    )
    schema_dict = builder.build(dialogues[:20])   # 用前 20 条做发现
    builder.save(schema_dict, Path("output/schema.json"))

    # 也可以只传文本列表
    text_dialogues = [
        ["agent: 你好，请问是张先生吗？", "user: 是的"],
        "坐席：您好\\n用户：你好",
    ]
    schema_dict = builder.build(text_dialogues)
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from contextmind.infra.llm_client import AdkLLMClient, LLMConfig
from contextmind.infra.logger import get_logger
from contextmind.scenarios.anyihua.knowledge_extraction.extractor import (
    AnyihuaKnowledgeExtractor,
    ExtractionSchema,
)
from .normalizer import normalize_dialogues
from .synthesizer import SchemaSynthesizer

logger = get_logger(__name__)


class KnowledgeBaseBuilder:
    """
    通用知识库构建器：任意对话数据 → SGD ``schema.json``。

    参数
    ----
    scene_name:
        业务场景的中文名称（如 ``"银行贷款外呼"``），用于 LLM 提示词。
    scene_description:
        场景简短描述（一句话），可为空；留空则使用 ``scene_name``。
    llm_client:
        :class:`~contextmind.infra.llm_client.AdkLLMClient` 实例；
        若为 ``None``，从 ``.env`` 自动加载。
    discovery_sample:
        发现阶段最多使用的对话条数（默认 20）。
        数量越多、发现越全面，但 LLM 调用次数也越多。

    属性
    ----
    last_slot_counter:
        最近一次 :meth:`build` 发现阶段产生的槽位计数器（供调试）。
    last_intent_counter:
        最近一次 :meth:`build` 发现阶段产生的意图计数器（供调试）。
    """

    def __init__(
        self,
        scene_name: str,
        scene_description: str = "",
        llm_client: Optional[AdkLLMClient] = None,
        discovery_sample: int = 20,
    ) -> None:
        self.scene_name = scene_name
        self.scene_description = scene_description or scene_name
        self.discovery_sample = discovery_sample

        # 延迟初始化：避免在无 LLM 环境下导入时崩溃
        self._llm_client: Optional[AdkLLMClient] = llm_client

        self.last_slot_counter: Counter = Counter()
        self.last_intent_counter: Counter = Counter()

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def build(
        self,
        dialogues: List[Any],
    ) -> Dict[str, Any]:
        """
        对输入对话执行完整的两阶段知识库构建流程。

        参数
        ----
        dialogues:
            对话列表，每项可为以下任一格式：

            - ``str``：平铺文本（换行分隔，每行含说话人前缀）
            - ``List[str]``：每项为一轮话语
            - ``dict``（chat_test 格式，含 ``对话历史``）
            - ``dict``（SGD 格式，含 ``turns``）

        返回
        ----
        SGD 格式的 **单服务** schema dict（不带顶层列表包裹）::

            {
              "service_name": "...",
              "description": "...",
              "slots": [...],
              "intents": [...]
            }

        将其包入列表 ``[schema_dict]`` 即可写入标准 ``schema.json``。
        """
        # -- Step 0: 归一化 --
        logger.info(
            f"[KnowledgeBaseBuilder] 场景: {self.scene_name!r}，"
            f"输入对话: {len(dialogues)} 条"
        )
        normalized = normalize_dialogues(dialogues)
        sample = normalized[: self.discovery_sample]
        logger.info(
            f"[KnowledgeBaseBuilder] 发现阶段使用前 {len(sample)} 条对话"
        )

        # -- Step 1: 发现阶段 --
        slot_counter, intent_counter, slot_samples, intent_samples = (
            self._run_discovery(sample)
        )
        self.last_slot_counter = slot_counter
        self.last_intent_counter = intent_counter

        logger.info(
            f"[KnowledgeBaseBuilder] 发现阶段完成 — "
            f"槽位类型 {len(slot_counter)} 个，意图类型 {len(intent_counter)} 个"
        )

        # -- Step 2: 合成阶段 --
        synthesizer = SchemaSynthesizer(llm_client=self._get_llm())
        schema_dict = synthesizer.synthesize(
            scene_name=self.scene_name,
            scene_description=self.scene_description,
            slot_counter=slot_counter,
            intent_counter=intent_counter,
            slot_sample_values=slot_samples,
            intent_sample_descs=intent_samples,
            n_dialogues=len(sample),
        )
        return schema_dict

    def save(
        self,
        schema_dict: Dict[str, Any],
        path: Union[str, Path],
    ) -> None:
        """
        将 schema dict 包入列表并写入标准 SGD ``schema.json`` 文件。

        参数
        ----
        schema_dict:
            :meth:`build` 返回的单服务 schema dict。
        path:
            输出文件路径（如 ``"output/schema.json"``）。
            父目录不存在时自动创建。
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([schema_dict], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"[KnowledgeBaseBuilder] schema.json 已写入: {path}")

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _get_llm(self) -> AdkLLMClient:
        """延迟初始化 LLM 客户端。"""
        if self._llm_client is None:
            try:
                self._llm_client = AdkLLMClient(config=LLMConfig.from_env())
            except Exception as exc:
                raise RuntimeError(
                    "LLM 客户端初始化失败，请在 .env 中配置 LLM_API_KEY / "
                    f"LLM_BASE_URL / LLM_MODEL。原始错误: {exc}"
                ) from exc
        return self._llm_client

    def _run_discovery(
        self,
        normalized_dialogues: List[Dict[str, Any]],
    ) -> tuple[Counter, Counter, Dict[str, List[str]], Dict[str, List[str]]]:
        """
        发现阶段：对每条对话运行开放式 LLM 提取，汇总槽位和意图。

        返回
        ----
        (slot_counter, intent_counter, slot_sample_values, intent_sample_descs)

        - slot_counter: ``Counter({slot_name: 出现次数})``
        - intent_counter: ``Counter({intent_name: 出现次数})``
        - slot_sample_values: ``{slot_name: [value, ...]}``（最多 5 个）
        - intent_sample_descs: ``{intent_name: [description, ...]}``（最多 3 个）
        """
        # 使用完全开放式 Schema（空槽位/意图列表 + open_ended=True）
        open_schema = ExtractionSchema(
            scene_name=self.scene_name,
            slots=[],
            intents=[],
            fact_description=f"{self.scene_name} 对话中出现的重要业务事实",
            slot_open_ended=True,
            intent_open_ended=True,
        )
        extractor = AnyihuaKnowledgeExtractor(
            llm_client=self._get_llm(),
            schema=open_schema,
        )

        slot_counter: Counter = Counter()
        intent_counter: Counter = Counter()
        slot_sample_values: Dict[str, List[str]] = {}
        intent_sample_descs: Dict[str, List[str]] = {}

        for i, dlg in enumerate(normalized_dialogues):
            dialogue_id = dlg.get("session_id", f"dlg_{i}")
            logger.info(
                f"[KnowledgeBaseBuilder] 发现对话 {i+1}/{len(normalized_dialogues)} "
                f"({dialogue_id})"
            )
            try:
                result = extractor.extract(dlg)
            except Exception as exc:
                logger.warning(
                    f"[KnowledgeBaseBuilder] 对话 {dialogue_id} 提取失败，跳过: {exc}"
                )
                continue

            for item in result.knowledge_items:
                if item.extraction_class == "slot_value" and item.label:
                    slot_counter[item.label] += 1
                    samples = slot_sample_values.setdefault(item.label, [])
                    if item.value and len(samples) < 5:
                        if item.value not in samples:
                            samples.append(item.value)

                elif item.extraction_class == "intent" and item.label:
                    intent_counter[item.label] += 1
                    descs = intent_sample_descs.setdefault(item.label, [])
                    if item.value and len(descs) < 3:
                        if item.value not in descs:
                            descs.append(item.value)

        return slot_counter, intent_counter, slot_sample_values, intent_sample_descs
