"""
langextract 深度集成桥接模块

本模块展示如何充分利用 langextract 库的核心能力（Annotator），而不是仅使用其
WordAligner 工具。

## 当前架构的问题

原有提取流程（``extractor.py``）：

1. 一次 LLM 调用处理完整多轮对话
2. LLM 输出 ``turn_idx`` 和 ``provenance_text``（两者均可能有偏差）
3. 再用 WordAligner / difflib 对 provenance_text 做事后对齐

这种方式的缺陷：
- LLM 容易混淆 turn_idx（说话人混淆、偏移 ±1）
- LLM 容易在 provenance_text 中轻微改写原话（导致对齐失败）
- 仅使用了 langextract 的 ``WordAligner`` 工具，未用其核心 ``Annotator`` 能力

## 更好的 langextract 使用方式

langextract 的 ``Annotator`` 类提供了完整的"提取 + 对齐"一体化管道：

1. 以每轮话语为单独文本输入调用 ``Annotator.annotate_text()``
2. LLM 被明确要求只输出该轮话语中的 **逐字（verbatim）** 片段作为 ``extraction_text``
3. langextract 原生提供 ``char_interval``（字符位置），无需手工对齐

这种"逐轮注解"方式的优势：
- 每次 LLM 调用只看一轮话语，不会混淆 turn_idx（根本不需要 turn_idx）
- LLM 输出的 extraction_text 必须来自同一段文本，misalignment 率接近零
- 充分利用 langextract 的 Annotator + Resolver + WordAligner 完整管道

## 主要组件

- :class:`SimpleLLMClientAdapter` — 将 ``SimpleLLMClient`` 适配为 langextract
  的 ``BaseLanguageModel`` 接口，使现有 LLM 客户端无缝接入 ``Annotator``
- :func:`create_per_turn_annotator` — 构建逐轮注解器（``Annotator``），
  返回可复用的实例
- :func:`extract_with_per_turn_annotator` — 完整提取流程：逐轮调用 Annotator，
  聚合所有轮次的 KnowledgeItem，返回 ExtractionResult
- :func:`build_langextract_schema_prompt` — 根据 ExtractionSchema 生成
  langextract 兼容的 PromptTemplateStructured 描述文本

## 快速使用示例::

    import json
    from pathlib import Path
    from contextmind.scenarios.anyihua.knowledge_extraction import (
        AnyihuaKnowledgeExtractor, DEFAULT_SCHEMA,
    )
    from contextmind.scenarios.anyihua.knowledge_extraction.langextract_bridge import (
        extract_with_per_turn_annotator,
    )
    from contextmind.infra.llm_client import SimpleLLMClient, LLMConfig

    dialogues = json.loads(Path("resources/data/chat_test_100.json").read_text())
    client = SimpleLLMClient(LLMConfig.from_env())

    # 使用逐轮 Annotator 模式（充分利用 langextract 能力）
    result = extract_with_per_turn_annotator(dialogues[0], client, DEFAULT_SCHEMA)
    print(f"溯源率: {result.stats['alignment_rate']:.1%}")
    for item in result.knowledge_items:
        print(f"  [{item.extraction_class}] {item.label}: {item.value}")
        print(f"    {item.provenance}")
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Sequence
from typing import Any, Dict, List, Optional, Tuple

from langextract.annotation import Annotator
from langextract.core.base_model import BaseLanguageModel
from langextract.core.types import FormatType, ScoredOutput
from langextract.data import Document, ExampleData, Extraction
from langextract.prompting import PromptTemplateStructured
from langextract.resolver import Resolver
from langextract.tokenizer import UnicodeTokenizer

from contextmind.infra.llm_client import SimpleLLMClient
from contextmind.infra.logger import get_logger

from .extractor import (
    ExtractionResult,
    ExtractionSchema,
    KnowledgeItem,
    _build_provenance,
    _parse_turns,
)

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# SimpleLLMClient → langextract BaseLanguageModel 适配器
# --------------------------------------------------------------------------- #


class SimpleLLMClientAdapter(BaseLanguageModel):
    """
    将项目自有的 ``SimpleLLMClient`` 适配为 langextract ``BaseLanguageModel`` 接口。

    langextract 的 ``Annotator`` 需要一个实现了 ``infer()`` 方法的
    ``BaseLanguageModel`` 实例。本适配器将 ``SimpleLLMClient.generate()``
    包装为符合接口要求的生成器，使现有 OpenAI 兼容端点无缝接入 langextract 管道。

    参数:
        client: 已初始化的 SimpleLLMClient 实例

    使用示例::

        from contextmind.infra.llm_client import SimpleLLMClient, LLMConfig
        from contextmind.scenarios.anyihua.knowledge_extraction.langextract_bridge import (
            SimpleLLMClientAdapter,
        )

        client = SimpleLLMClient(LLMConfig.from_env())
        adapter = SimpleLLMClientAdapter(client)

        # 现在可以作为 langextract 语言模型使用
        from langextract.annotation import Annotator
        annotator = Annotator(language_model=adapter, prompt_template=...)
    """

    def __init__(self, client: SimpleLLMClient) -> None:
        super().__init__()
        self._client = client

    def infer(
        self,
        batch_prompts: Sequence[str],
        **kwargs: Any,
    ) -> Iterator[Sequence[ScoredOutput]]:
        """
        实现 langextract BaseLanguageModel.infer() 接口。

        逐条处理 batch_prompts 中的每个 prompt，调用 SimpleLLMClient.generate()
        获取响应，并包装为 ``ScoredOutput``（score=1.0 表示唯一候选输出）。

        参数:
            batch_prompts: 待推理的 prompt 列表（langextract 逐条送入）
            **kwargs:      预留参数（temperature、max_tokens 等），当前忽略

        Yields:
            每个 prompt 对应一个 ``[ScoredOutput]`` 列表
        """
        for prompt in batch_prompts:
            try:
                _reasoning, text = self._client.generate(prompt)
                yield [ScoredOutput(score=1.0, output=text)]
            except Exception as exc:
                logger.warning(f"[SimpleLLMClientAdapter] LLM 推理失败: {exc}")
                yield [ScoredOutput(score=0.0, output="")]


# --------------------------------------------------------------------------- #
# 逐轮提取 Prompt 构建
# --------------------------------------------------------------------------- #

# YAML 格式的 few-shot 示例文本（用于构建 PromptTemplateStructured.examples）
_SLOT_EXAMPLE_TEXT = "您在安逸花账户有一笔两万一千九百块钱的额度嘛，对吧？"
_SLOT_EXAMPLE_YAML = """\
- extraction_class: slot_value
  extraction_text: 两万一千九百块钱
  attributes:
    label: available_credit
    value: 两万一千九百块钱
- extraction_class: intent
  extraction_text: 您在安逸花账户有一笔两万一千九百块钱的额度嘛，对吧？
  attributes:
    label: explain_credit_limit
    value: 告知用户当前可用额度"""

_USER_EXAMPLE_TEXT = "不是这个我说七月二十三号七月二十三号的这一笔贷款我没贷怎么怎么会有一笔一万三千多块钱的还有一个八月。"
_USER_EXAMPLE_YAML = """\
- extraction_class: slot_value
  extraction_text: 七月二十三号
  attributes:
    label: dispute_date
    value: 七月二十三号
- extraction_class: slot_value
  extraction_text: 一万三千多块钱
  attributes:
    label: inquiry_amount
    value: 一万三千多块钱
- extraction_class: intent
  extraction_text: 七月二十三号的这一笔贷款我没贷怎么怎么会有一笔一万三千多块钱
  attributes:
    label: handle_loan_dispute
    value: 用户质疑某笔借款记录"""


def build_langextract_schema_prompt(schema: ExtractionSchema) -> str:
    """
    根据 ExtractionSchema 生成适合 langextract ``PromptTemplateStructured`` 的
    提示词描述文本。

    langextract 的 ``PromptTemplateStructured.description`` 字段是提取任务的
    说明文字，告知 LLM：
    1. 提取类别（extraction_class）及其含义
    2. extraction_text 必须是输入话语的逐字子串
    3. attributes 中的 label 和 value 约定

    参数:
        schema: 动态提取 Schema（槽位、意图、事实定义）

    返回:
        格式化好的提示词描述字符串
    """
    lines = [
        f"你是{schema.scene_name}对话的知识提取专家。",
        "",
        "从给定的单轮对话话语中提取结构化知识。",
        "输出为 YAML 列表，每项包含以下字段：",
        "  - extraction_class: 类别，必须是 slot_value / intent / fact 之一",
        "  - extraction_text:  话语中的原始逐字文本片段（verbatim），"
        "必须是输入话语的精确子串，不得改写或省略",
        "  - attributes.label: 槽位名称 / 意图编码 / 事实标签",
        "  - attributes.value: 提取到的值或自然语言描述",
        "",
        "提取规则：",
        "  1. extraction_text 必须是本轮话语的精确子串，不能修改任何字符",
        "  2. 仅提取当前话语中明确出现的信息，不推断、不猜测",
        "  3. 同一信息只提取一次，选取最具代表性的文本片段",
        "  4. 若当前话语无可提取信息，输出空列表 []",
        "",
    ]

    # 槽位说明
    if schema.slots:
        lines.append("【槽位定义（slot_value）—— label 须从以下名称选取】")
        for s in schema.slots:
            lines.append(f"  - {s.name}: {s.description}")
        if schema.slot_open_ended:
            lines.append(
                "  （以上为参考列表；若话语涉及未列出的重要信息，可自行命名 label）"
            )
    else:
        lines.append("【槽位（slot_value）—— 根据话语内容自行命名 label】")

    lines.append("")

    # 意图说明
    if schema.intents:
        lines.append("【意图定义（intent）—— label 须从以下名称选取】")
        for i in schema.intents:
            lines.append(f"  - {i.name}: {i.description}")
        if schema.intent_open_ended:
            lines.append(
                "  （以上为参考列表；若话语体现了未列出的意图，可自行命名 label）"
            )
    else:
        lines.append("【意图（intent）—— 根据话语内容自行命名 label】")

    lines.append("")
    lines.append(f"【事实（fact）—— {schema.fact_description}】")

    return "\n".join(lines)


def create_per_turn_annotator(
    client: SimpleLLMClient,
    schema: ExtractionSchema,
) -> Annotator:
    """
    创建逐轮知识注解器（langextract ``Annotator`` 实例）。

    返回的 Annotator 可对单轮话语文本调用 ``annotate_text()``，
    利用 langextract 原生对齐机制直接获得带 ``char_interval`` 的提取结果，
    无需手工调用 WordAligner。

    参数:
        client: 已初始化的 SimpleLLMClient 实例
        schema: 提取 Schema（槽位、意图、事实定义）

    返回:
        可重复使用的 ``Annotator`` 实例

    示例::

        annotator = create_per_turn_annotator(client, DEFAULT_SCHEMA)
        annotated = annotator.annotate_text("您在安逸花账户有一笔两万一千九百块钱的额度嘛，对吧？",
                                            show_progress=False)
        for ext in annotated.extractions:
            print(ext.extraction_class, ext.extraction_text, ext.char_interval)
    """
    adapter = SimpleLLMClientAdapter(client)

    description = build_langextract_schema_prompt(schema)

    # few-shot 示例：帮助 LLM 理解期望的输出格式
    slot_example = ExampleData(
        text=_SLOT_EXAMPLE_TEXT,
        extractions=[
            Extraction(
                extraction_class="slot_value",
                extraction_text="两万一千九百块钱",
                attributes={"label": "available_credit", "value": "两万一千九百块钱"},
            ),
            Extraction(
                extraction_class="intent",
                extraction_text=_SLOT_EXAMPLE_TEXT,
                attributes={
                    "label": "explain_credit_limit",
                    "value": "告知用户当前可用额度",
                },
            ),
        ],
    )
    user_example = ExampleData(
        text=_USER_EXAMPLE_TEXT,
        extractions=[
            Extraction(
                extraction_class="slot_value",
                extraction_text="七月二十三号",
                attributes={"label": "dispute_date", "value": "七月二十三号"},
            ),
            Extraction(
                extraction_class="slot_value",
                extraction_text="一万三千多块钱",
                attributes={"label": "inquiry_amount", "value": "一万三千多块钱"},
            ),
            Extraction(
                extraction_class="intent",
                extraction_text="七月二十三号的这一笔贷款我没贷怎么怎么会有一笔一万三千多块钱",
                attributes={
                    "label": "handle_loan_dispute",
                    "value": "用户质疑某笔借款记录",
                },
            ),
        ],
    )

    prompt_template = PromptTemplateStructured(
        description=description,
        examples=[slot_example, user_example],
    )

    return Annotator(
        language_model=adapter,
        prompt_template=prompt_template,
        format_type=FormatType.YAML,
        fence_output=False,
    )


# --------------------------------------------------------------------------- #
# 逐轮提取主函数
# --------------------------------------------------------------------------- #


def extract_with_per_turn_annotator(
    dialogue: Dict[str, Any],
    client: SimpleLLMClient,
    schema: ExtractionSchema,
) -> ExtractionResult:
    """
    使用 langextract ``Annotator`` 逐轮提取知识，充分利用 langextract 原生对齐能力。

    与 ``AnyihuaKnowledgeExtractor.extract()`` 的核心区别：

    ====================================  =====================================
    原有方式（extractor.py）              本函数（langextract_bridge.py）
    ====================================  =====================================
    1 次 LLM 调用处理完整对话             N 次 LLM 调用，每轮 1 次
    LLM 自行判断 turn_idx（易错）          无需 turn_idx，LLM 只看当前轮
    provenance_text 可能被改写             extraction_text 被约束为逐字子串
    事后用 WordAligner/difflib 对齐        langextract 原生提供 char_interval
    ====================================  =====================================

    优势：
    - extraction_text 直接是 langextract 对齐产物，字符位置更准确
    - 完全消除 turn_idx 混淆导致的跨轮溯源失败
    - 充分利用 Annotator + Resolver + WordAligner 完整管道

    劣势：
    - 每轮 1 次 LLM 调用，总调用次数等于轮数（成本更高）
    - 单轮处理缺乏跨轮上下文（如某槽位仅在多轮交叉中才能推断）

    参数:
        dialogue: chat_test_100.json 中的单条对话条目
        client:   已初始化的 SimpleLLMClient 实例
        schema:   提取 Schema

    返回:
        ExtractionResult，每条知识的 provenance 来自 langextract 原生 char_interval
    """
    dialogue_id = str(dialogue.get("session_id") or dialogue.get("dialogue_id", ""))
    logger.info(
        f"[PerTurnAnnotator] ── 开始逐轮提取对话 {dialogue_id or '(无ID)'} ──"
    )

    source_text, turns = _parse_turns(dialogue)
    if not turns:
        logger.warning(f"[PerTurnAnnotator] 对话为空，跳过: {dialogue_id}")
        return ExtractionResult(
            dialogue_id=dialogue_id,
            source_text="",
            turns=[],
            knowledge_items=[],
            stats={
                "total": 0,
                "aligned": 0,
                "unaligned": 0,
                "alignment_rate": 0.0,
                "skipped_incomplete": 0,
                "turns": 0,
            },
        )

    annotator = create_per_turn_annotator(client, schema)
    tokenizer = UnicodeTokenizer()

    knowledge_items: List[KnowledgeItem] = []
    aligned_count = 0
    skipped_count = 0

    for turn_idx, speaker, utterance in turns:
        if not utterance.strip():
            continue

        logger.debug(
            f"[PerTurnAnnotator] 处理第{turn_idx + 1}轮({speaker}): "
            f"{utterance[:40]}…"
        )

        try:
            annotated = annotator.annotate_text(
                text=utterance,
                max_char_buffer=500,  # 单轮话语通常 ≤ 200 字
                show_progress=False,
            )
        except Exception as exc:
            logger.warning(
                f"[PerTurnAnnotator] 第{turn_idx + 1}轮注解失败: {exc}"
            )
            continue

        for ext in annotated.extractions:
            cls = str(ext.extraction_class or "").strip()
            extraction_text = str(ext.extraction_text or "").strip()
            attrs = ext.attributes or {}
            label = str(attrs.get("label", cls)).strip()
            value = str(attrs.get("value", extraction_text)).strip()

            if not (cls and label and value and extraction_text):
                logger.debug(
                    f"[PerTurnAnnotator] 跳过不完整提取: cls={cls!r} "
                    f"label={label!r} value={value!r}"
                )
                skipped_count += 1
                continue

            # langextract 原生提供字符位置（无需手工对齐）
            char_start: Optional[int] = None
            char_end: Optional[int] = None
            if ext.char_interval is not None:
                char_start = ext.char_interval.start_pos
                char_end = ext.char_interval.end_pos

            if char_start is not None:
                aligned_count += 1
                logger.debug(
                    f"[PerTurnAnnotator] ✓ [{cls}] {label}: {value[:30]} "
                    f"← 第{turn_idx + 1}轮({speaker}) [{char_start}:{char_end}]"
                )
            else:
                logger.debug(
                    f"[PerTurnAnnotator] △ [{cls}] {label}: {value[:30]} "
                    f"← 第{turn_idx + 1}轮({speaker}) 溯源失败"
                )

            provenance = _build_provenance(
                extraction_text, turn_idx, speaker, char_start, char_end
            )
            knowledge_items.append(
                KnowledgeItem(
                    extraction_class=cls,
                    label=label,
                    value=value,
                    turn_idx=turn_idx,
                    speaker=speaker,
                    provenance=provenance,
                )
            )

    total = len(knowledge_items)
    stats = {
        "total": total,
        "aligned": aligned_count,
        "unaligned": total - aligned_count,
        "alignment_rate": round(aligned_count / total, 3) if total else 0.0,
        "skipped_incomplete": skipped_count,
        "turns": len(turns),
    }

    logger.info(
        f"[PerTurnAnnotator] 提取完成: {dialogue_id} | "
        f"共 {total} 条 | 溯源成功 {aligned_count}/{total}"
        f"（{stats['alignment_rate']:.1%}）"
    )

    return ExtractionResult(
        dialogue_id=dialogue_id,
        source_text=source_text,
        turns=turns,
        knowledge_items=knowledge_items,
        stats=stats,
    )
