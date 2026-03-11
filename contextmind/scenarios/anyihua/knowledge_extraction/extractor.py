"""
安逸花外呼 · 知识提取（langextract 溯源版）

以 langextract 为提取工具，从原始安逸花外呼对话数据中提取结构化知识，
每条知识均携带一个 ``provenance`` 字段表示溯源内容（原文出处及字符位置）。

LLM 客户端通过 ``contextmind/infra/llm_client.py`` + ``.env`` 统一初始化，
无需在调用处手动传入。

工作流程::

    原始对话 (chat_test_100.json 条目)
        │
        ▼
    对话文本化（_dialogue_to_text）
        │
        ▼
    LLM 提取（SimpleLLMClient，从 .env 自动加载）
    ┌──────────────────────────────────┐
    │ 槽位值（slot_value）              │
    │ 用户意图（intent）                │
    │ 关键事实（fact）                  │
    └──────────────────────────────────┘
        │   每条提取结果携带
        │   verbatim 溯源文本片段
        ▼
    langextract WordAligner
    ┌──────────────────────────────────────────┐
    │ 原文片段 → 字符区间（start_pos:end_pos） │
    │ 整合为单一 provenance 字符串             │
    └──────────────────────────────────────────┘
        │
        ▼
    ExtractionResult（可 JSON 序列化）

溯源字段说明::

    KnowledgeItem.provenance : 单一溯源字段，格式为
                               "「原文片段」[位置 start:end]"（对齐成功时）
                               "「原文片段」"（对齐失败时，仍保留 LLM 给出的原文片段）

典型使用::

    import json
    from pathlib import Path
    from contextmind.scenarios.anyihua.knowledge_extraction import AnyihuaKnowledgeExtractor

    dialogues = json.loads(Path("resources/data/chat_test_100.json").read_text())

    # LLM 从 .env 自动加载，无需手动传入
    extractor = AnyihuaKnowledgeExtractor()

    # 单条提取
    result = extractor.extract(dialogues[0])
    for item in result.knowledge_items:
        print(f"[{item.extraction_class}] {item.label}: {item.value}")
        print(f"  溯源: {item.provenance}")

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

from contextmind.infra.llm_client import LLMConfig, SimpleLLMClient
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
    单条提取知识，含原文溯源信息。

    属性:
        extraction_class:  知识类别，"slot_value" / "intent" / "fact"
        label:             知识标签，槽位名 / 意图编码 / 事实标签
        value:             提取出的知识内容（自然语言文本）
        provenance:        溯源内容（单一字段），格式：
                           对齐成功时："「原文片段」[位置 start:end]"
                           对齐失败时："「原文片段」"
                           此字段直接告知该知识条目来自对话的哪段原文。
    """

    extraction_class: str
    label: str
    value: str
    provenance: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExtractionResult:
    """
    单条对话的完整提取结果，含每条知识的溯源信息。

    属性:
        dialogue_id:    对话唯一标识（来自 session_id 字段）
        source_text:    完整对话文本（含"坐席："/"用户："前缀）
        knowledge_items:提取出的知识列表，每条的 provenance 字段标明原文出处
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
# 溯源字符串构建
# --------------------------------------------------------------------------- #


def _build_provenance(
    verbatim_text: str,
    char_start: Optional[int],
    char_end: Optional[int],
) -> str:
    """
    将对齐结果整合为单一溯源字符串。

    对齐成功时格式：「原文片段」[位置 start:end]
    对齐失败时格式：「原文片段」

    该字段直接告知知识条目来自对话中的哪段原文。
    """
    if char_start is not None and char_end is not None:
        return f"「{verbatim_text}」[位置 {char_start}:{char_end}]"
    return f"「{verbatim_text}」"


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

    LLM 通过 ``contextmind/infra/llm_client.py`` 统一初始化，从 ``.env`` 文件读取
    API Key / Base URL / Model 等配置，与项目其他模块保持一致。

    每条提取结果包含：
    - 知识类别（extraction_class）：slot_value / intent / fact
    - 知识标签（label）：槽位名 / 意图编码 / 事实标签
    - 知识内容（value）：提取出的自然语言文本
    - 溯源内容（provenance）：单一字段，格式 "「原文片段」[位置 start:end]"

    参数:
        llm_client:  可选的 SimpleLLMClient 实例。若不传入，则自动通过
                     LLMConfig.from_env() 从 .env 文件加载配置后初始化。
    """

    def __init__(
        self,
        llm_client: Optional[SimpleLLMClient] = None,
    ) -> None:
        if llm_client is None:
            try:
                llm_client = SimpleLLMClient(LLMConfig.from_env())
            except Exception as exc:
                raise RuntimeError(
                    "LLM 客户端初始化失败，请确认 .env 文件中已正确配置 API Key、"
                    "Base URL 和 Model（如 LLM_API_KEY、LLM_BASE_URL、LLM_MODEL）。"
                    f"原始错误: {exc}"
                ) from exc
        self._llm: SimpleLLMClient = llm_client

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def extract(self, dialogue: Dict[str, Any]) -> ExtractionResult:
        """
        从单条原始对话中提取带溯源的结构化知识。

        参数:
            dialogue: chat_test_100.json 中的单条对话条目（含 session_id 和 对话历史）

        返回:
            ExtractionResult，每条知识的 provenance 字段标明原文出处及字符位置
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

        # 5. 将对齐结果转换为 KnowledgeItem（provenance 为单一溯源字段）
        knowledge_items: List[KnowledgeItem] = []
        aligned_count = 0

        for ext, meta in zip(aligned_extractions, item_meta):
            char_start: Optional[int] = None
            char_end: Optional[int] = None

            if ext.char_interval is not None:
                char_start = ext.char_interval.start_pos
                char_end = ext.char_interval.end_pos
                aligned_count += 1

            knowledge_items.append(
                KnowledgeItem(
                    extraction_class=meta["extraction_class"],
                    label=meta["label"],
                    value=meta["value"],
                    provenance=_build_provenance(meta["provenance_text"], char_start, char_end),
                )
            )

        total = len(aligned_extractions)
        stats = {
            "total": total,
            "aligned": aligned_count,
            "unaligned": total - aligned_count,
            "alignment_rate": round(aligned_count / total, 3) if total else 0.0,
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

        通过 SimpleLLMClient.generate() 统一调用（与 .env 配置对应），
        LLM 负责识别知识并为每条知识提供 verbatim 溯源原文（provenance_text），
        WordAligner 随后将其精确对齐到 source_text 的字符区间。
        """
        prompt = _build_extraction_prompt(source_text)
        try:
            _reasoning, response = self._llm.generate(prompt)  # _reasoning = chain-of-thought (DeepSeek-R1 etc.)
            return _parse_llm_extraction(response)
        except Exception as exc:
            logger.error(f"[AnyihuaExtractor] LLM 调用失败: {exc}")
            raise


# --------------------------------------------------------------------------- #
# 便捷函数（无需实例化 Extractor）
# --------------------------------------------------------------------------- #


def extract_knowledge_with_provenance(
    dialogue: Dict[str, Any],
    llm_client: Optional[SimpleLLMClient] = None,
) -> ExtractionResult:
    """
    从单条安逸花外呼对话中提取带溯源的结构化知识（便捷函数）。

    参数:
        dialogue:    原始对话条目（chat_test_100.json 单条）
        llm_client:  可选的 SimpleLLMClient 实例；若不传入则自动从 .env 加载

    返回:
        ExtractionResult，每条知识项的 provenance 字段标明原文出处
    """
    extractor = AnyihuaKnowledgeExtractor(llm_client=llm_client)
    return extractor.extract(dialogue)
