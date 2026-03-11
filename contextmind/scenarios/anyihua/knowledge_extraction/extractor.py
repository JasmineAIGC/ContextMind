"""
安逸花外呼 · 知识提取（langextract 溯源版）

以 langextract 为提取工具，从原始安逸花外呼对话数据中提取结构化知识，
每条知识均携带完整的原文溯源信息（char_interval + alignment_status）。

工作流程::

    原始对话 (chat_test_100.json 条目)
        │
        ▼
    对话文本化（_dialogue_to_text）
        │
        ▼
    LLM 提取（SimpleLLMClient）
    ┌──────────────────────────────────┐
    │ 槽位值（slot_value）              │
    │ 用户意图（intent）                │
    │ 关键事实（fact）                  │
    └──────────────────────────────────┘
        │   每条提取结果携带
        │   verbatim 溯源文本片段
        ▼
    langextract WordAligner
    ┌──────────────────────────────────┐
    │ extraction_text → char_interval  │
    │ alignment_status 对齐质量标记    │
    └──────────────────────────────────┘
        │
        ▼
    ExtractionResult（可 JSON 序列化）

溯源字段说明::

    KnowledgeItem.provenance_text   : 原文中用于定位的原始文本片段（verbatim）
    KnowledgeItem.char_start        : 在对话文本中的字符起始位置（含）
    KnowledgeItem.char_end          : 在对话文本中的字符结束位置（不含）
    KnowledgeItem.alignment_status  : 对齐质量
                                      "match_exact"  — 精确匹配
                                      "match_lesser" — 部分精确匹配
                                      "match_fuzzy"  — 模糊匹配
                                      None           — 对齐失败

典型使用::

    import json
    from pathlib import Path
    from contextmind.infra.llm_client import SimpleLLMClient
    from contextmind.scenarios.anyihua.knowledge_extraction import AnyihuaKnowledgeExtractor

    dialogues = json.loads(Path("resources/data/chat_test_100.json").read_text())
    llm = SimpleLLMClient()
    extractor = AnyihuaKnowledgeExtractor(llm_client=llm)

    # 单条提取
    result = extractor.extract(dialogues[0])
    for item in result.knowledge_items:
        print(f"[{item.extraction_class}] {item.label}: {item.value}")
        print(f"  溯源: {item.provenance_text!r}  @{item.char_start}:{item.char_end}")
        print(f"  对齐质量: {item.alignment_status}")

    # 批量提取
    results = extractor.extract_batch(dialogues[:10])
    for r in results:
        print(r.to_dict())
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------- #
# langextract — 数据类型 + 溯源对齐工具
# --------------------------------------------------------------------------- #
from langextract.data import AlignmentStatus, CharInterval, ExampleData, Extraction
from langextract.resolver import WordAligner
from langextract.tokenizer import UnicodeTokenizer

from contextmind.infra.logger import get_logger

logger = get_logger(__name__)

# --------------------------------------------------------------------------- #
# langextract 工具单例（模块级，线程安全）
# --------------------------------------------------------------------------- #
_TOKENIZER = UnicodeTokenizer()
_WORD_ALIGNER = WordAligner()

# --------------------------------------------------------------------------- #
# 对话解析常量
# --------------------------------------------------------------------------- #
_AGENT_PREFIX = "坐席："
_USER_PREFIX = "用户："


# --------------------------------------------------------------------------- #
# 数据模型
# --------------------------------------------------------------------------- #


@dataclass
class KnowledgeItem:
    """
    单条提取知识，含完整原文溯源信息。

    属性:
        extraction_class:  知识类别，"slot_value" / "intent" / "fact"
        label:             知识标签，槽位名 / 意图编码 / 事实标签
        value:             提取出的知识内容（自然语言文本）
        provenance_text:   在对话原文中用于回溯定位的原始文本片段（verbatim）
                           此字段直接传入 langextract WordAligner 做对齐
        char_start:        在对话文本中的字符起始位置（含）；对齐失败时为 None
        char_end:          在对话文本中的字符结束位置（不含）；对齐失败时为 None
        alignment_status:  对齐质量（"match_exact" / "match_lesser" /
                           "match_fuzzy" / None）
        confidence:        置信度（由 alignment_status 自动推导）
    """

    extraction_class: str
    label: str
    value: str
    provenance_text: str
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    alignment_status: Optional[str] = None
    confidence: float = 0.5

    def is_aligned(self) -> bool:
        """是否成功回溯定位到原文。"""
        return self.char_start is not None and self.char_end is not None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExtractionResult:
    """
    单条对话的完整提取结果，含每条知识的原文溯源信息。

    属性:
        dialogue_id:    对话唯一标识（来自 session_id 字段）
        source_text:    完整对话文本（含"坐席："/"用户："前缀）
        knowledge_items:提取出的知识列表，每条附带 char_start/char_end 溯源
        stats:          对齐统计：total / aligned / unaligned / alignment_rate
        extracted_at:   提取时间戳
    """

    dialogue_id: str
    source_text: str
    knowledge_items: List[KnowledgeItem] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    extracted_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dialogue_id": self.dialogue_id,
            "source_text": self.source_text,
            "knowledge_items": [item.to_dict() for item in self.knowledge_items],
            "stats": self.stats,
            "extracted_at": self.extracted_at,
        }


# --------------------------------------------------------------------------- #
# 对齐质量 → 置信度映射
# --------------------------------------------------------------------------- #

_ALIGNMENT_CONFIDENCE: Dict[Optional[str], float] = {
    "match_exact": 1.0,
    "match_lesser": 0.85,
    "match_fuzzy": 0.70,
    None: 0.50,
}


def _confidence_from_status(status: Optional[str]) -> float:
    return _ALIGNMENT_CONFIDENCE.get(status, 0.50)


# --------------------------------------------------------------------------- #
# 对话文本化
# --------------------------------------------------------------------------- #


def _dialogue_to_text(dialogue: Dict[str, Any]) -> Tuple[str, List[Tuple[str, str]]]:
    """
    将 chat_test 格式的原始对话条目转换为纯文本和 (speaker, utterance) 列表。

    支持格式：
    - chat_test 格式：含 ``对话历史`` 字符串列表（已含"坐席："/"用户："前缀）
    - SGD 格式：含 ``turns`` 列表

    返回:
        (source_text, lines)
        source_text: 以换行拼接的完整对话文本
        lines: List of (speaker_code, utterance) 其中 speaker_code 为 "SYSTEM" 或 "USER"
    """
    lines: List[Tuple[str, str]] = []

    if "对话历史" in dialogue:
        raw_lines = dialogue["对话历史"]
        if isinstance(raw_lines, str):
            raw_lines = [raw_lines]
        for line in raw_lines:
            line = str(line).strip()
            if line.startswith(_AGENT_PREFIX):
                lines.append(("SYSTEM", line[len(_AGENT_PREFIX):].strip()))
            elif line.startswith(_USER_PREFIX):
                lines.append(("USER", line[len(_USER_PREFIX):].strip()))
            else:
                # 无前缀，按交替顺序猜测角色
                lines.append(("USER", line))
    elif "turns" in dialogue:
        for turn in dialogue["turns"]:
            speaker = turn.get("speaker", "USER")
            utterance = turn.get("utterance", "")
            lines.append((speaker, utterance))

    # 重建含角色前缀的完整文本（与 WordAligner 对齐时使用相同文本格式）
    prefix_map = {"SYSTEM": _AGENT_PREFIX, "USER": _USER_PREFIX}
    source_lines = [f"{prefix_map.get(sp, _USER_PREFIX)}{utt}" for sp, utt in lines]
    source_text = "\n".join(source_lines)
    return source_text, lines


# --------------------------------------------------------------------------- #
# langextract WordAligner 溯源对齐
# --------------------------------------------------------------------------- #


def _align_and_annotate(
    extractions: List[Extraction],
    source_text: str,
) -> List[Extraction]:
    """
    使用 langextract WordAligner 将一批 Extraction 回溯对齐到对话原文。

    每个 Extraction.extraction_text 必须是对话原文中出现过的 verbatim 文本片段，
    WordAligner 会将其定位到精确的字符区间（char_interval）并标注对齐质量
    （alignment_status），从而实现完整的溯源可追踪性。

    参数:
        extractions:  待对齐的 Extraction 列表（extraction_text 为原文片段）
        source_text:  完整对话文本（含"坐席："/"用户："前缀）

    返回:
        char_interval 和 alignment_status 已填充的 Extraction 列表
    """
    if not extractions or not source_text:
        return extractions

    try:
        aligned_groups = _WORD_ALIGNER.align_extractions(
            [extractions],
            source_text,
            token_offset=0,
            char_offset=0,
            tokenizer_impl=_TOKENIZER,
        )
        if not aligned_groups:
            logger.warning("[AnyihuaExtractor] WordAligner 返回空结果，跳过溯源对齐")
            return extractions
        return list(aligned_groups[0])
    except Exception as exc:
        logger.warning(f"[AnyihuaExtractor] WordAligner 对齐失败，跳过溯源: {exc}")
        return extractions


# --------------------------------------------------------------------------- #
# LLM 提取 Prompt
# --------------------------------------------------------------------------- #

_EXTRACTION_SYSTEM_PROMPT = """\
你是安逸花外呼对话的知识提取专家。

你的任务是从安逸花外呼对话中提取三类结构化知识：

1. **槽位值（slot_value）**：客户的具体信息字段
   常见槽位：customer_name（姓名）、phone_suffix（手机尾号）、
   available_credit（可用额度）、loan_amount（借款金额）、
   loan_status（借款状态）、repayment_date（还款日）、
   interest_rate（利率）、bank_name（绑定银行）

2. **用户意图（intent）**：用户在对话中表达的目的
   常见意图：verify_identity（核实身份）、handle_loan_dispute（处理借款纠纷）、
   inquire_credit（询问额度）、inquire_interest（询问利率）、
   request_repayment_plan（请求还款方案）、say_goodbye（结束通话）

3. **关键事实（fact）**：对话中提及的重要业务事实（不属于上述两类的）

输出格式（严格 JSON）：
{
  "extractions": [
    {
      "extraction_class": "slot_value",
      "label": "<槽位名>",
      "value": "<提取到的值>",
      "provenance_text": "<对话中原始出现的完整文本片段，必须是对话的逐字子串>"
    },
    {
      "extraction_class": "intent",
      "label": "<意图编码>",
      "value": "<自然语言描述>",
      "provenance_text": "<触发此意图的用户原话，必须是对话的逐字子串>"
    },
    {
      "extraction_class": "fact",
      "label": "<事实标签>",
      "value": "<事实内容>",
      "provenance_text": "<对话中支撑此事实的原始文本片段，必须是对话的逐字子串>"
    }
  ]
}

关键约束：
- provenance_text 必须是对话原文中**完全相同**的文本片段（verbatim），不能改写或总结
- 如果一个信息在对话中多次出现，只提取一次
- 不要提取对话中未明确出现的信息（不猜测、不推断）
- 值（value）为空或无法确定时，跳过该条
- 只输出 JSON，不要任何额外说明"""

_EXTRACTION_USER_TEMPLATE = """\
请从以下安逸花外呼对话中提取结构化知识（每条提取结果均须附带 provenance_text）：

{dialogue_text}

请输出 JSON："""


def _build_extraction_prompt(source_text: str) -> str:
    return (
        f"{_EXTRACTION_SYSTEM_PROMPT}\n\n"
        + _EXTRACTION_USER_TEMPLATE.format(dialogue_text=source_text)
    )


def _parse_llm_extraction(llm_response: str) -> List[Dict[str, Any]]:
    """
    从 LLM 响应中解析提取结果列表。

    支持：
    - 纯 JSON 响应
    - Markdown 代码块包裹的 JSON（```json ... ``` 或 ``` ... ```）
    - 嵌套在其他文本中的 JSON 对象（正则兜底）

    返回:
        List[dict]，每项含 extraction_class / label / value / provenance_text；
        解析失败时返回 []
    """

    def _try_parse(text: str) -> Optional[List[Dict[str, Any]]]:
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and "extractions" in obj:
                return obj["extractions"]
            if isinstance(obj, list):
                return obj
            return None
        except (json.JSONDecodeError, ValueError):
            return None

    # 1. 直接解析
    result = _try_parse(llm_response.strip())
    if result is not None:
        return result

    # 2. 去掉 Markdown 代码块（一次性匹配完整的 ``` ... ``` 块）
    stripped = re.sub(r"```(?:json)?\s*([\s\S]*?)```", r"\1", llm_response).strip()
    result = _try_parse(stripped)
    if result is not None:
        return result

    # 3. 正则兜底：提取第一个 {...} JSON 块
    match = re.search(r"\{[\s\S]+\}", llm_response)
    if match:
        result = _try_parse(match.group(0))
        if result is not None:
            return result

    logger.warning("[AnyihuaExtractor] LLM 响应解析失败，返回空列表")
    return []


# --------------------------------------------------------------------------- #
# 主提取器
# --------------------------------------------------------------------------- #


class AnyihuaKnowledgeExtractor:
    """
    安逸花外呼对话知识提取器（langextract 溯源版）。

    结合 SimpleLLMClient（知识识别）和 langextract WordAligner（原文定位），
    从原始外呼对话数据中提取带溯源的结构化知识。

    每条提取结果包含：
    - 知识类别（extraction_class）：slot_value / intent / fact
    - 知识标签（label）：槽位名 / 意图编码 / 事实标签
    - 知识内容（value）：提取出的自然语言文本
    - 溯源原文（provenance_text）：在对话中定位用的 verbatim 片段
    - 字符位置（char_start / char_end）：对话文本中的精确位置
    - 对齐质量（alignment_status）：match_exact / match_lesser / match_fuzzy / None
    - 置信度（confidence）：由对齐质量自动推导

    参数:
        llm_client:              SimpleLLMClient 实例（OpenAI-compatible 接口）
        min_alignment_confidence:过滤阈值，低于此置信度的结果将从 knowledge_items
                                 中移除（但仍会在日志中记录）；默认 0.5（不过滤 None）
    """

    def __init__(
        self,
        llm_client: Any,
        min_alignment_confidence: float = 0.5,
    ) -> None:
        if llm_client is None:
            raise ValueError("llm_client 不能为 None，请传入 SimpleLLMClient 实例")
        self._llm = llm_client
        self._min_confidence = min_alignment_confidence

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def extract(self, dialogue: Dict[str, Any]) -> ExtractionResult:
        """
        从单条原始对话中提取带溯源的结构化知识。

        参数:
            dialogue: chat_test_100.json 中的单条对话条目（含 session_id 和 对话历史）

        返回:
            ExtractionResult，含每条知识的 char_start/char_end 溯源位置
        """
        dialogue_id = dialogue.get("session_id") or dialogue.get("dialogue_id", "")
        logger.info(f"[AnyihuaExtractor] 开始提取: {dialogue_id}")

        # 1. 对话文本化
        source_text, _ = _dialogue_to_text(dialogue)
        if not source_text.strip():
            logger.warning(f"[AnyihuaExtractor] 空对话，跳过: {dialogue_id}")
            return ExtractionResult(
                dialogue_id=dialogue_id,
                source_text="",
                knowledge_items=[],
                stats={"total": 0, "aligned": 0, "unaligned": 0, "alignment_rate": 0.0},
            )

        # 2. LLM 提取：识别知识 + 定位 provenance_text
        raw_items = self._call_llm(source_text)
        if not raw_items:
            logger.warning(f"[AnyihuaExtractor] LLM 未返回任何提取结果: {dialogue_id}")
            return ExtractionResult(
                dialogue_id=dialogue_id,
                source_text=source_text,
                knowledge_items=[],
                stats={"total": 0, "aligned": 0, "unaligned": 0, "alignment_rate": 0.0},
            )

        # 3. 构建 langextract Extraction 对象（尚未对齐）
        #    extraction_text = provenance_text（对话中的 verbatim 原文片段）
        raw_extractions: List[Extraction] = []
        item_meta: List[Dict[str, str]] = []  # 与 raw_extractions 一一对应

        for item in raw_items:
            cls = str(item.get("extraction_class", "")).strip()
            label = str(item.get("label", "")).strip()
            value = str(item.get("value", "")).strip()
            prov = str(item.get("provenance_text", "")).strip()

            if not (cls and label and value and prov):
                continue

            raw_extractions.append(
                Extraction(
                    extraction_class=cls,
                    extraction_text=prov,         # verbatim 原文片段，用于 WordAligner 对齐
                    attributes={"label": label, "value": value},
                    # char_interval / alignment_status 由下方 WordAligner 批量填充
                )
            )
            item_meta.append({"extraction_class": cls, "label": label, "value": value, "provenance_text": prov})

        # 4. langextract WordAligner：批量回溯对齐 → 填充 char_interval + alignment_status
        aligned_extractions = _align_and_annotate(raw_extractions, source_text)

        # 5. 将对齐结果转换为 KnowledgeItem
        knowledge_items: List[KnowledgeItem] = []
        aligned_count = 0

        for ext, meta in zip(aligned_extractions, item_meta):
            char_start: Optional[int] = None
            char_end: Optional[int] = None
            alignment_status_str: Optional[str] = None

            if ext.char_interval is not None:
                char_start = ext.char_interval.start_pos
                char_end = ext.char_interval.end_pos
                aligned_count += 1

            if ext.alignment_status is not None:
                alignment_status_str = (
                    ext.alignment_status.value
                    if hasattr(ext.alignment_status, "value")
                    else str(ext.alignment_status)
                )

            confidence = _confidence_from_status(alignment_status_str)

            # 置信度过滤（None 对应 0.5，通常保留）
            if confidence < self._min_confidence:
                logger.debug(
                    f"[AnyihuaExtractor] 过滤低置信度提取 "
                    f"({confidence:.2f} < {self._min_confidence}): {meta['label']}: {meta['value'][:40]}"
                )
                continue

            knowledge_items.append(
                KnowledgeItem(
                    extraction_class=meta["extraction_class"],
                    label=meta["label"],
                    value=meta["value"],
                    provenance_text=meta["provenance_text"],
                    char_start=char_start,
                    char_end=char_end,
                    alignment_status=alignment_status_str,
                    confidence=confidence,
                )
            )

        total = len(aligned_extractions)
        stats = {
            "total": total,
            "aligned": aligned_count,
            "unaligned": total - aligned_count,
            "alignment_rate": round(aligned_count / total, 3) if total else 0.0,
            "after_filter": len(knowledge_items),
        }

        logger.info(
            f"[AnyihuaExtractor] 完成: {dialogue_id} — "
            f"总计 {total} 条，对齐 {aligned_count} 条 "
            f"（对齐率 {stats['alignment_rate']:.1%}）"
        )

        return ExtractionResult(
            dialogue_id=dialogue_id,
            source_text=source_text,
            knowledge_items=knowledge_items,
            stats=stats,
        )

    def extract_batch(
        self,
        dialogues: Sequence[Dict[str, Any]],
        stop_on_error: bool = False,
    ) -> List[ExtractionResult]:
        """
        批量提取多条对话的知识。

        参数:
            dialogues:      对话条目列表（chat_test_100.json 内容）
            stop_on_error:  True 则遇到异常立即抛出；False 则跳过并记录日志（默认）

        返回:
            ExtractionResult 列表（与 dialogues 一一对应，失败条目为空结果）
        """
        results: List[ExtractionResult] = []
        total = len(dialogues)
        for idx, dialogue in enumerate(dialogues):
            dialogue_id = dialogue.get("session_id") or dialogue.get("dialogue_id", f"#{idx}")
            logger.info(f"[AnyihuaExtractor] 批量处理 [{idx + 1}/{total}]: {dialogue_id}")
            try:
                results.append(self.extract(dialogue))
            except Exception as exc:
                if stop_on_error:
                    raise
                logger.error(f"[AnyihuaExtractor] 提取失败（{dialogue_id}）: {exc}，使用空结果")
                source_text, _ = _dialogue_to_text(dialogue)
                results.append(
                    ExtractionResult(
                        dialogue_id=dialogue_id,
                        source_text=source_text,
                        knowledge_items=[],
                        stats={"total": 0, "aligned": 0, "unaligned": 0, "alignment_rate": 0.0, "error": str(exc)},
                    )
                )
        return results

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _call_llm(self, source_text: str) -> List[Dict[str, Any]]:
        """
        调用 LLM 提取结构化知识。

        LLM 负责：
        1. 识别对话中的知识（槽位值、意图、事实）
        2. 为每条知识提供 verbatim 溯源原文（provenance_text）

        WordAligner 随后将 provenance_text 精确对齐到 source_text 的字符区间。
        """
        prompt = _build_extraction_prompt(source_text)
        try:
            if hasattr(self._llm, "generate"):
                _, response = self._llm.generate(prompt)
            elif hasattr(self._llm, "generate_async"):
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    # Already inside an event loop; cannot call run_until_complete.
                    # Caller should use an async wrapper instead.
                    raise RuntimeError(
                        "llm_client 仅实现了 generate_async()，但当前在同步上下文中调用。"
                        "请使用 asyncio.run(extractor.extract_async(dialogue)) 或改用实现了 "
                        "generate() 的 LLM 客户端。"
                    )
                except RuntimeError as inner:
                    if "no running event loop" in str(inner).lower() or "no current event loop" in str(inner).lower():
                        _, response = asyncio.run(self._llm.generate_async(prompt))
                    else:
                        raise
            else:
                raise ValueError("llm_client 须实现 generate() 或 generate_async() 方法")

            return _parse_llm_extraction(response)

        except Exception as exc:
            logger.error(f"[AnyihuaExtractor] LLM 调用失败: {exc}")
            raise


# --------------------------------------------------------------------------- #
# 便捷函数（无需实例化 Extractor）
# --------------------------------------------------------------------------- #


def extract_knowledge_with_provenance(
    dialogue: Dict[str, Any],
    llm_client: Any,
    min_alignment_confidence: float = 0.5,
) -> ExtractionResult:
    """
    从单条安逸花外呼对话中提取带溯源的结构化知识（便捷函数）。

    参数:
        dialogue:                原始对话条目（chat_test_100.json 单条）
        llm_client:              SimpleLLMClient 实例
        min_alignment_confidence:置信度过滤阈值（默认 0.5）

    返回:
        ExtractionResult，每条知识项均附带 char_start/char_end 和 alignment_status
    """
    extractor = AnyihuaKnowledgeExtractor(
        llm_client=llm_client,
        min_alignment_confidence=min_alignment_confidence,
    )
    return extractor.extract(dialogue)
