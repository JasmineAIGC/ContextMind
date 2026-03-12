"""
langextract 深度集成桥接模块

本模块演示如何按照 langextract 官方推荐方式（https://github.com/google/langextract）
进行知识提取，核心是使用 ``lx.extract(model=...)`` 顶层 API，
而不是绕过它只使用底层的 ``WordAligner``。

## 原有架构的问题

原有提取流程（``extractor.py``）：

1. 一次 LLM 调用处理完整多轮对话
2. LLM 输出 ``turn_idx`` 和 ``provenance_text``（两者均可能有偏差）
3. 再用 WordAligner / difflib 对 provenance_text 做事后对齐

这种方式的缺陷：
- LLM 容易混淆 turn_idx（说话人混淆、偏移 ±1）
- LLM 容易在 provenance_text 中轻微改写原话（导致对齐失败）
- 仅使用了 langextract 的 ``WordAligner`` 工具，完全未用其核心提取管道

## 正确使用 langextract 的方式

langextract 官方示例（README.md）的标准用法::

    import langextract as lx

    result = lx.extract(
        text_or_documents=input_text,
        prompt_description=prompt,
        examples=examples,
        model_id="gemini-2.5-flash",     # 使用内置模型
    )

对于**自定义模型**（如本项目的 ``SimpleLLMClient``），官方同样支持::

    result = lx.extract(
        text_or_documents=input_text,
        prompt_description=prompt,
        examples=examples,
        model=my_custom_model,            # 传入自定义 BaseLanguageModel 实例
    )

``lx.extract()`` 内部会自动：
1. 按 ``max_char_buffer`` 分块（对单轮短话语直接单块处理）
2. 调用 LLM 获取 YAML 格式的提取结果
3. 通过 ``Annotator + Resolver + WordAligner`` 对齐到字符区间（char_interval）
4. 返回带 ``char_interval`` 的 ``AnnotatedDocument``

## 逐轮提取 + 历史上下文 + 去重

本模块的核心函数 ``extract_with_per_turn_annotator()`` 在每轮提取时：

1. **以当前轮话语为 ``text_or_documents``** — LLM 只看一段话，无需输出 turn_idx
2. **通过 ``additional_context`` 传入历史轮次** — 帮助 LLM 理解跨轮引用
   （如"这笔贷款"的指代需要联系前几轮上下文）
3. **跨轮槽位去重** — 同一 label 的 slot_value/fact 仅保留最新值
   （用户纠正时取最后一次），意图（intent）则每轮独立保留

## 主要组件

- :class:`SimpleLLMClientAdapter` — 将 ``SimpleLLMClient`` 适配为 langextract
  ``BaseLanguageModel`` 接口，使现有 OpenAI 兼容端点无缝接入 ``lx.extract()``
- :func:`build_langextract_schema_prompt` — 从 ``ExtractionSchema`` 生成
  langextract 兼容的提示词描述字符串
- :func:`build_langextract_examples` — 从内置 few-shot 示例生成 ``ExampleData`` 列表
- :func:`extract_with_per_turn_annotator` — 完整逐轮提取流程（推荐入口）：
  对每轮话语调用 ``lx.extract()``，传入历史上下文，最后跨轮去重

## 快速使用示例::

    import json
    from pathlib import Path
    from contextmind.scenarios.anyihua.knowledge_extraction.langextract_bridge import (
        extract_with_per_turn_annotator,
        SimpleLLMClientAdapter,
        DEFAULT_SCHEMA,
    )
    from contextmind.infra.llm_client import SimpleLLMClient, LLMConfig

    dialogues = json.loads(Path("resources/data/chat_test_100.json").read_text())
    client = SimpleLLMClient(LLMConfig.from_env())

    # 逐轮提取，携带最近 3 轮历史上下文，并对槽位去重
    result = extract_with_per_turn_annotator(
        dialogues[0], client, DEFAULT_SCHEMA,
        context_window=3, deduplicate_slots=True,
    )
    print(f"溯源率: {result.stats['alignment_rate']:.1%}")
    for item in result.knowledge_items:
        print(f"  [{item.extraction_class}] {item.label}: {item.value}")
        print(f"    {item.provenance}")
"""

from __future__ import annotations

import langextract as lx  # `lx` is the official alias from langextract's own README examples
from collections.abc import Iterator, Sequence
from typing import Any, Dict, List, Optional, Tuple

from langextract.core.base_model import BaseLanguageModel
from langextract.core.types import ScoredOutput
from langextract.data import ExampleData, Extraction

from contextmind.infra.llm_client import SimpleLLMClient
from contextmind.infra.logger import get_logger

from .extractor import (
    DEFAULT_SCHEMA,
    ExtractionResult,
    ExtractionSchema,
    KnowledgeItem,
    ValueUpdate,
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

    官方 langextract 通过 ``model_id="gemini-2.5-flash"`` 使用内置 Gemini 模型；
    对于自定义 LLM，官方同样支持直接传入 ``BaseLanguageModel`` 子类实例::

        result = lx.extract(
            text_or_documents=text,
            prompt_description=prompt,
            examples=examples,
            model=SimpleLLMClientAdapter(client),   # 自定义模型
        )

    本适配器将 ``SimpleLLMClient.generate()`` 包装为符合接口要求的生成器，
    使现有 OpenAI 兼容端点无缝接入 langextract 的完整提取管道
    （Annotator → Resolver → WordAligner → char_interval）。

    参数:
        client: 已初始化的 SimpleLLMClient 实例
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
# 逐轮提取 Prompt 与 Few-shot 示例构建
# --------------------------------------------------------------------------- #

# Few-shot 示例 1：坐席话语 → slot_value + intent
_SLOT_EXAMPLE_TEXT = "您在安逸花账户有一笔两万一千九百块钱的额度嘛，对吧？"

# Few-shot 示例 2：用户话语 → slot_value × 2 + intent
_USER_EXAMPLE_TEXT = "不是这个我说七月二十三号七月二十三号的这一笔贷款我没贷怎么怎么会有一笔一万三千多块钱的还有一个八月。"


def build_langextract_examples() -> List[ExampleData]:
    """
    构建 langextract few-shot 示例列表（``ExampleData``）。

    遵循官方规范（README.md）：
    - ``extraction_text`` 必须是 ``text`` 的逐字子串（verbatim），不得改写
    - 按在文本中出现的顺序排列

    返回:
        两条 ``ExampleData``（坐席话语示例、用户话语示例），
        可直接传给 ``lx.extract(examples=...)``
    """
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
                # 意图的 extraction_text 取最能代表意图的原文片段
                extraction_text="您在安逸花账户有一笔两万一千九百块钱的额度嘛，对吧？",
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
    return [slot_example, user_example]


def build_langextract_schema_prompt(schema: ExtractionSchema) -> str:
    """
    根据 ExtractionSchema 生成适合 langextract 的提示词描述字符串。

    此字符串对应官方示例中的 ``prompt_description`` 参数::

        result = lx.extract(
            text_or_documents=utterance,
            prompt_description=build_langextract_schema_prompt(schema),
            examples=build_langextract_examples(),
            model=adapter,
        )

    langextract 的核心约束（在提示词中明确声明）：
    - ``extraction_text`` 必须是输入话语的逐字子串（verbatim）
    - 这一约束使 langextract 内置的 WordAligner 能精确对齐到字符区间

    参数:
        schema: 动态提取 Schema（槽位、意图、事实定义）

    返回:
        格式化好的提示词描述字符串（传给 ``lx.extract(prompt_description=...)``）
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
        "  3. 若提供了对话历史（additional_context），历史仅供理解上下文用，",
        "     extraction_text 必须来自当前话语，不得截取自历史内容",
        "  4. 同一信息只提取一次，选取最具代表性的文本片段",
        "  5. 若当前话语无可提取信息，输出空列表 []",
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




# --------------------------------------------------------------------------- #
# 辅助函数：历史上下文构建 & 跨轮去重
# --------------------------------------------------------------------------- #


def _build_history_context(
    turns: List[Tuple[int, str, str]],
    current_idx: int,
    context_window: int,
) -> Optional[str]:
    """
    构建当前轮提取时要传入的历史上下文字符串。

    多轮对话中，用户常通过代词或省略指代前几轮提到的实体（如"那笔贷款"、
    "刚才说的日期"）。将最近 ``context_window`` 轮作为 ``additional_context``
    传给 ``lx.extract()``，使 LLM 能正确理解跨轮引用，减少提取错误。

    参数:
        turns:          全部轮次列表，格式为 [(turn_idx, speaker, utterance), ...]
        current_idx:    当前正在提取的轮次在列表中的位置（0-based）
        context_window: 历史窗口大小，即取当前轮之前最多多少轮作为上下文

    返回:
        格式化的历史上下文字符串；若无历史（首轮或 context_window=0）则返回 None
    """
    if context_window <= 0 or current_idx == 0:
        return None

    start = max(0, current_idx - context_window)
    history_turns = turns[start:current_idx]
    if not history_turns:
        return None

    lines = ["[对话历史（供参考，勿从中提取）]"]
    for turn_idx, speaker, utterance in history_turns:
        lines.append(f"第{turn_idx + 1}轮 ({speaker}): {utterance}")
    return "\n".join(lines)


def _deduplicate_knowledge_items(
    items: List[KnowledgeItem],
) -> Tuple[List[KnowledgeItem], List[ValueUpdate]]:
    """
    对跨轮提取结果进行槽位去重，同时记录值变更。

    在多轮对话中，同一槽位可能多次被提取：
    - 用户重复提及同一信息（如反复强调日期）→ 保留最后一次（通常最准确）
    - 用户纠正之前的信息（如"不是一万三，是一万五"）→ 同样保留最后一次，
      并将旧值 → 新值的变更记录到 ``ValueUpdate`` 列表中

    **去重规则：**
    - ``slot_value`` 和 ``fact``：相同 ``label`` 的条目只保留最后一次（最新值），
      保留位置为最后出现的时序位置（不破坏对话时间顺序）
    - ``intent``：每轮意图独立保留，不去重（不同轮次意图均有业务价值）

    **两阶段算法：**
    1. 第一遍扫描：找到每个需去重 key 的最后出现位置索引
    2. 第二遍扫描：按时序逐一输出，去重 key 仅在其最后出现位置输出，
       同时比较首次出现值与最终值，差异则记录为 ``ValueUpdate``

    参数:
        items: 所有轮次合并后的知识条目列表（按轮次顺序）

    返回:
        (deduplicated_items, value_updates)
        deduplicated_items: 去重后的知识条目列表，严格按时序排列
        value_updates:      值变更记录列表（旧值 → 新值）
    """
    _DEDUP_CLASSES = {"slot_value", "fact"}

    # 第一遍：找每个 dedup key 的最后出现位置
    last_occurrence_index: Dict[Tuple[str, str], int] = {}
    for i, item in enumerate(items):
        if item.extraction_class in _DEDUP_CLASSES:
            last_occurrence_index[(item.extraction_class, item.label)] = i

    # 第二遍：按时序输出，去重类只在最后出现位置输出，记录值变更
    result: List[KnowledgeItem] = []
    first_occurrence: Dict[Tuple[str, str], KnowledgeItem] = {}  # 记录首次出现的条目（用于比较）
    value_updates: List[ValueUpdate] = []

    for i, item in enumerate(items):
        if item.extraction_class in _DEDUP_CLASSES:
            key = (item.extraction_class, item.label)
            if key not in first_occurrence:
                first_occurrence[key] = item
            if i == last_occurrence_index[key]:
                # 该 key 的最后一次出现：加入结果
                result.append(item)
                # 若与首次出现的值不同，记录更新
                orig = first_occurrence[key]
                if orig.value != item.value:
                    value_updates.append(
                        ValueUpdate(
                            extraction_class=item.extraction_class,
                            label=item.label,
                            old_value=orig.value,
                            new_value=item.value,
                            old_turn_idx=orig.turn_idx,
                            new_turn_idx=item.turn_idx,
                        )
                    )
            # 非最后出现位置：跳过（不加入结果）
        else:
            # intent 及其他类别：不去重，直接保留
            result.append(item)

    return result, value_updates


# --------------------------------------------------------------------------- #
# 逐轮提取主函数（官方 lx.extract() 调用模式）
# --------------------------------------------------------------------------- #


def extract_with_per_turn_annotator(
    dialogue: Dict[str, Any],
    client: SimpleLLMClient,
    schema: ExtractionSchema,
    *,
    context_window: int = 3,
    deduplicate_slots: bool = True,
) -> ExtractionResult:
    """
    使用 ``lx.extract(model=...)`` 逐轮提取知识，完整利用 langextract 官方管道。

    **与原有 extractor.py 的对比**

    ====================================  =====================================
    原有方式（extractor.py）              本函数（langextract_bridge.py）
    ====================================  =====================================
    1 次 LLM 调用处理完整对话             N 次 ``lx.extract()`` 调用，每轮 1 次
    LLM 自行判断 turn_idx（易错）          无需 turn_idx，LLM 只看当前轮话语
    provenance_text 可能被 LLM 改写        extraction_text 被约束为逐字子串
    事后用 WordAligner/difflib 对齐        langextract 原生提供 char_interval
    无历史上下文                           通过 additional_context 传入历史轮次
    无跨轮去重                             slot_value/fact 按 label 去重
    ====================================  =====================================

    **多轮上下文的必要性**

    在客服对话中，用户常用代词指代前文实体（如"那笔贷款"、"你们刚才说的那个
    额度"）。若不传历史，LLM 无法正确理解这些引用；
    通过 ``additional_context`` 注入最近 ``context_window`` 轮，
    LLM 可在提取时正确消歧，同时 extraction_text 仍来自当前轮话语，
    溯源位置不受影响。

    **跨轮去重的必要性**

    多轮提取时，同一槽位可能在多轮反复出现（用户重复强调或纠正）。
    ``deduplicate_slots=True`` 时，对 ``slot_value``/``fact`` 按 label 去重，
    保留最新值（用户最后表达的意图/数值最可靠）；``intent`` 不去重（逐轮保留）。

    参数:
        dialogue:          chat_test_100.json 中的单条对话条目
        client:            已初始化的 SimpleLLMClient 实例
        schema:            提取 Schema（槽位、意图、事实定义）
        context_window:    传入 additional_context 的历史轮次数（0 表示不传历史）
        deduplicate_slots: 是否对 slot_value/fact 按 label 跨轮去重

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

    # 为当前对话创建一个 SimpleLLMClientAdapter（可在所有轮次复用）
    adapter = SimpleLLMClientAdapter(client)
    prompt_description = build_langextract_schema_prompt(schema)
    examples = build_langextract_examples()

    knowledge_items: List[KnowledgeItem] = []
    aligned_count = 0
    skipped_count = 0

    for list_idx, (turn_idx, speaker, utterance) in enumerate(turns):
        if not utterance.strip():
            continue

        # 构建历史上下文（传给 additional_context）
        history_ctx = _build_history_context(turns, list_idx, context_window)

        logger.debug(
            f"[PerTurnAnnotator] 处理第{turn_idx + 1}轮({speaker})"
            f"{' +历史' if history_ctx else ''}: {utterance[:40]}…"
        )

        try:
            # ---------------------------------------------------------------- #
            # 官方 lx.extract(model=...) 调用模式
            # ---------------------------------------------------------------- #
            annotated_doc = lx.extract(
                text_or_documents=utterance,
                prompt_description=prompt_description,
                examples=examples,
                model=adapter,                  # 使用自定义 LLM 适配器
                additional_context=history_ctx,  # 传入历史轮次供 LLM 参考
                max_char_buffer=500,             # 单轮话语 ≤ 200 字，单块处理
                show_progress=False,
                use_schema_constraints=False,   # 自定义 model 已含格式控制逻辑，
                                                # langextract 的 schema 约束（Gemini
                                                # 专用 JSON schema）不适用于通用 LLM
            )
        except Exception as exc:
            logger.warning(
                f"[PerTurnAnnotator] 第{turn_idx + 1}轮提取失败: {exc}"
            )
            continue

        for ext in annotated_doc.extractions:
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

    # 跨轮槽位去重
    value_updates: List[ValueUpdate] = []
    if deduplicate_slots and knowledge_items:
        before_dedup = len(knowledge_items)
        knowledge_items, value_updates = _deduplicate_knowledge_items(knowledge_items)
        dedup_removed = before_dedup - len(knowledge_items)
        if dedup_removed:
            logger.info(
                f"[PerTurnAnnotator] 跨轮去重: 删除 {dedup_removed} 条重复槽位/事实"
                f"，其中值发生变更 {len(value_updates)} 条"
            )
    else:
        dedup_removed = 0

    total = len(knowledge_items)
    updated_count = len(value_updates)
    stats = {
        "total": total,
        "aligned": aligned_count,
        "unaligned": total - aligned_count,
        "alignment_rate": round(aligned_count / total, 3) if total else 0.0,
        "skipped_incomplete": skipped_count,
        "dedup_removed": dedup_removed,
        "updated_count": updated_count,
        "turns": len(turns),
    }

    logger.info(
        f"[PerTurnAnnotator] 提取完成: {dialogue_id} | "
        f"共 {total} 条（去重删除 {dedup_removed}，值更新 {updated_count}） | "
        f"溯源成功 {aligned_count}/{total}（{stats['alignment_rate']:.1%}）"
    )

    return ExtractionResult(
        dialogue_id=dialogue_id,
        source_text=source_text,
        turns=turns,
        knowledge_items=knowledge_items,
        updates=value_updates,
        stats=stats,
    )
