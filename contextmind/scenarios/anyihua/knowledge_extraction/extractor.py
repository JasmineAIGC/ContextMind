"""
安逸花外呼 · 知识提取（单轮对话 + langextract 溯源版）

核心设计：逐轮提取 + 轮级溯源
==================================

安逸花外呼数据是多轮对话。langextract 的 WordAligner 设计用于对单段文本做字符
对齐，直接套用在完整多轮对话上会导致对齐精度下降。

本模块的解决方案：

1. **逐轮解析**：将对话拆解为 [(轮次, 说话人, 话语文本), ...] 列表。
2. **全对话 LLM 提取**：将完整对话（含轮次标记）送给 LLM，LLM 在提取每条知识时
   同时标注该知识来自哪一轮（turn_idx）。
3. **轮级 WordAligner 对齐**：每条提取结果仅在其所属轮次的文本上做对齐，
   WordAligner 输入为短单段文本，对齐精度大幅提升。
4. **单一溯源字段**：对齐成功时为 ``「原文片段」[第N轮(说话人) 位置 s:e]``，
   对齐失败时为 ``「原文片段」[第N轮(说话人) 溯源失败]``。

提取 Schema（基于 anyihua_schema_induction_demo.py）:
    槽位（slot_value）:
        customer_name, phone_suffix, available_credit, loan_amount,
        loan_status, repayment_date, interest_rate, bank_name,
        loan_date, overdue_days, credit_limit
    意图（intent）:
        verify_identity, handle_loan_dispute, inquire_credit,
        inquire_interest, request_repayment_plan, say_goodbye,
        confirm_account_usage, reject_promotion
    事实（fact）:
        任意其他对话中提及的业务事实

工作流程::

    原始对话 (chat_test_100.json 条目)
        │
        ▼
    逐轮解析（_parse_turns）
    [(idx, speaker, utterance), ...]
        │
        ▼
    LLM 提取（含轮次感知 prompt）
    ┌──────────────────────────────────────────────┐
    │ extraction_class, label, value               │
    │ turn_idx（来自哪一轮）                        │
    │ provenance_text（该轮的 verbatim 片段）        │
    └──────────────────────────────────────────────┘
        │
        ▼
    轮级 WordAligner 对齐
    ┌──────────────────────────────────────────────┐
    │ 仅对 turns[turn_idx] 的文本做字符对齐         │
    │ 短文本 → 精确字符区间                         │
    └──────────────────────────────────────────────┘
        │
        ▼
    ExtractionResult（可 JSON 序列化，可保存文件）

LLM 客户端通过 ``contextmind/infra/llm_client.py`` + ``.env`` 统一初始化。

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
        print(f"[第{item.turn_idx+1}轮({item.speaker})] [{item.extraction_class}] {item.label}: {item.value}")
        print(f"  溯源: {item.provenance}")

    # 批量提取，结果自动保存为文件
    results = extractor.extract_batch(dialogues[:10], save_path=Path("data/results.json"))
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------- #
# langextract — 数据类型 + 溯源对齐工具
# --------------------------------------------------------------------------- #
from langextract.data import Extraction
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
_SPEAKER_LABEL = {"SYSTEM": "坐席", "USER": "用户"}


# --------------------------------------------------------------------------- #
# 数据模型
# --------------------------------------------------------------------------- #


@dataclass
class KnowledgeItem:
    """
    单条提取知识，含轮次归属与原文溯源信息。

    属性:
        extraction_class:  知识类别，"slot_value" / "intent" / "fact"
        label:             知识标签，槽位名 / 意图编码 / 事实标签
        value:             提取出的知识内容（自然语言文本）
        turn_idx:          来自对话的第几轮（0-based），-1 表示无法定位
        speaker:           说话人，"坐席" 或 "用户"
        provenance:        溯源内容（单一字段），格式：
                           对齐成功：「原文片段」[第N轮(说话人) 位置 start:end]
                           对齐失败：「原文片段」[第N轮(说话人) 溯源失败]
                           无轮次：  「原文片段」[溯源失败]
    """

    extraction_class: str
    label: str
    value: str
    turn_idx: int
    speaker: str
    provenance: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExtractionResult:
    """
    单条对话的完整提取结果，含每条知识的溯源信息。

    属性:
        dialogue_id:    对话唯一标识（来自 session_id 字段）
        source_text:    完整对话文本（含轮次标记）
        turns:          解析后的轮次列表 [(turn_idx, speaker, utterance)]
        knowledge_items:提取出的知识列表，每条的 provenance 标明轮次与位置
        stats:          提取统计：total / aligned / unaligned / alignment_rate / turns
        extracted_at:   提取时间戳
    """

    dialogue_id: str
    source_text: str
    turns: List[Tuple[int, str, str]] = field(default_factory=list)
    knowledge_items: List[KnowledgeItem] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    extracted_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dialogue_id": self.dialogue_id,
            "source_text": self.source_text,
            "turns": [
                {"turn_idx": idx, "speaker": sp, "utterance": utt}
                for idx, sp, utt in self.turns
            ],
            "knowledge_items": [item.to_dict() for item in self.knowledge_items],
            "stats": self.stats,
            "extracted_at": self.extracted_at,
        }


# --------------------------------------------------------------------------- #
# 对话解析：拆轮次
# --------------------------------------------------------------------------- #


def _parse_turns(dialogue: Dict[str, Any]) -> Tuple[str, List[Tuple[int, str, str]]]:
    """
    将对话条目拆解为轮次列表和带轮次标记的完整文本。

    支持格式：
    - chat_test 格式：含 ``对话历史`` 字符串列表（已含"坐席："/"用户："前缀）
    - SGD 格式：含 ``turns`` 列表

    返回:
        (source_text, turns)
        source_text : 每行格式为 "[第N轮 说话人] 话语内容"
        turns       : [(turn_idx, speaker_label, utterance_text), ...]
    """
    turns: List[Tuple[int, str, str]] = []

    if "对话历史" in dialogue:
        raw_lines = dialogue["对话历史"]
        if isinstance(raw_lines, str):
            raw_lines = [raw_lines]
        for idx, line in enumerate(raw_lines):
            line = str(line).strip()
            if line.startswith(_AGENT_PREFIX):
                speaker = "坐席"
                utt = line[len(_AGENT_PREFIX):]
            elif line.startswith(_USER_PREFIX):
                speaker = "用户"
                utt = line[len(_USER_PREFIX):]
            else:
                speaker = "用户"
                utt = line
            turns.append((idx, speaker, utt.strip()))

    elif "turns" in dialogue:
        for idx, turn in enumerate(dialogue["turns"]):
            speaker_code = turn.get("speaker", "USER")
            speaker = _SPEAKER_LABEL.get(speaker_code, speaker_code)
            utt = turn.get("utterance", "")
            turns.append((idx, speaker, utt.strip()))

    # 构建带轮次标记的源文本（便于日志展示）
    lines = [f"[第{idx + 1}轮({sp})] {utt}" for idx, sp, utt in turns]
    source_text = "\n".join(lines)
    return source_text, turns


# --------------------------------------------------------------------------- #
# 轮级 WordAligner 溯源对齐
# --------------------------------------------------------------------------- #


def _align_to_turn(
    provenance_text: str,
    turn_text: str,
) -> Tuple[Optional[int], Optional[int]]:
    """
    将 provenance_text 精确对齐到单轮话语文本的字符区间。

    参数:
        provenance_text: LLM 给出的 verbatim 原文片段
        turn_text:       该轮次的原始话语文本（单段）

    返回:
        (char_start, char_end) 或 (None, None)（对齐失败）
    """
    if not provenance_text or not turn_text:
        return None, None
    try:
        exts = [Extraction(extraction_class="x", extraction_text=provenance_text)]
        groups = _WORD_ALIGNER.align_extractions(
            [exts],
            turn_text,
            token_offset=0,
            char_offset=0,
            tokenizer_impl=_TOKENIZER,
        )
        if not groups or not groups[0]:
            return None, None
        aligned = groups[0][0]
        if aligned.char_interval is not None:
            return aligned.char_interval.start_pos, aligned.char_interval.end_pos
        return None, None
    except Exception as exc:
        logger.debug(f"[WordAligner] 对齐异常（{provenance_text!r}）: {exc}")
        return None, None


# --------------------------------------------------------------------------- #
# 溯源字符串构建
# --------------------------------------------------------------------------- #


def _build_provenance(
    verbatim_text: str,
    turn_idx: int,
    speaker: str,
    char_start: Optional[int],
    char_end: Optional[int],
) -> str:
    """
    将轮次归属和对齐结果整合为单一溯源字符串。

    格式:
        对齐成功：「原文片段」[第N轮(说话人) 位置 start:end]
        对齐失败：「原文片段」[第N轮(说话人) 溯源失败]
        无轮次：  「原文片段」[溯源失败]
    """
    if turn_idx < 0:
        return f"「{verbatim_text}」[溯源失败]"
    turn_label = f"第{turn_idx + 1}轮({speaker})"
    if char_start is not None and char_end is not None:
        return f"「{verbatim_text}」[{turn_label} 位置 {char_start}:{char_end}]"
    return f"「{verbatim_text}」[{turn_label} 溯源失败]"


# --------------------------------------------------------------------------- #
# LLM 提取 Prompt（轮次感知 + Schema 引导）
# --------------------------------------------------------------------------- #

# 安逸花外呼业务 Schema（基于 anyihua_schema_induction_demo.py）
_SCHEMA_CONTEXT = """\
【提取 Schema（安逸花外呼业务）】

槽位值（slot_value）：
  - customer_name       : 客户姓名（如"高先生"）
  - phone_suffix        : 手机尾号（如"六七八"）
  - available_credit    : 可用额度（如"两万一千九百块钱"）
  - loan_amount         : 借款金额（如"六百块钱"）
  - loan_status         : 借款状态（如"已还清"、"未还清"）
  - repayment_date      : 还款日（如"十一月一日"）
  - interest_rate       : 借款利率（如"百分之二十四"）
  - bank_name           : 绑定银行（如"农业银行"）
  - loan_date           : 借款时间（如"二五年五月份"）
  - overdue_days        : 逾期天数（如"几天"）
  - credit_limit        : 授信额度（如"一万八千元"）

用户意图（intent）：
  - verify_identity     : 核实身份
  - handle_loan_dispute : 处理借款纠纷（投诉不明借款记录）
  - inquire_credit      : 询问额度
  - inquire_interest    : 询问利率
  - request_repayment_plan : 请求还款方案
  - say_goodbye         : 结束通话
  - confirm_account_usage  : 确认账户使用情况
  - reject_promotion    : 拒绝促销推荐

关键事实（fact）：
  不属于上述两类的重要业务事实（如逾期记录、临时额度到期等）"""

_EXTRACTION_SYSTEM_PROMPT = f"""\
你是安逸花外呼对话的知识提取专家。

{_SCHEMA_CONTEXT}

你的任务是从多轮对话中提取上述三类结构化知识。
对话中每轮格式为：[第N轮(说话人)] 话语内容

输出格式（严格 JSON）：
{{
  "extractions": [
    {{
      "extraction_class": "slot_value",
      "label": "<槽位名，来自上方列表>",
      "value": "<提取到的值>",
      "turn_idx": <0-based 整数，该信息来自第几轮，从0开始>,
      "provenance_text": "<该轮话语中原始出现的完整文本片段，必须是逐字子串>"
    }},
    {{
      "extraction_class": "intent",
      "label": "<意图编码，来自上方列表>",
      "value": "<自然语言描述>",
      "turn_idx": <0-based 整数>,
      "provenance_text": "<触发此意图的原话，必须是该轮话语的逐字子串>"
    }},
    {{
      "extraction_class": "fact",
      "label": "<事实标签>",
      "value": "<事实内容>",
      "turn_idx": <0-based 整数>,
      "provenance_text": "<支撑此事实的原话，必须是该轮话语的逐字子串>"
    }}
  ]
}}

关键约束：
- turn_idx 必须是整数，从 0 开始；第1轮对应 0，第2轮对应 1，以此类推
- provenance_text 必须是对应轮次话语中完全相同的文本片段（verbatim），不能改写
- 如果一个信息在对话中多次出现，只提取一次（选最早出现的轮次）
- 只提取对话中明确出现的信息，不猜测不推断
- 只输出 JSON，不要任何额外说明"""

_EXTRACTION_USER_TEMPLATE = """\
请从以下安逸花外呼对话中提取结构化知识（每条须标注 turn_idx 和 provenance_text）：

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
        List[dict]，每项含 extraction_class / label / value / turn_idx / provenance_text；
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

    # 2. 去掉 Markdown 代码块
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
# 结果保存
# --------------------------------------------------------------------------- #


def save_results(
    results: List["ExtractionResult"],
    path: Path,
    indent: int = 2,
) -> None:
    """
    将批量提取结果保存为 JSON 文件。

    参数:
        results: ExtractionResult 列表
        path:    保存路径（自动创建父目录）
        indent:  JSON 缩进量
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [r.to_dict() for r in results]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")
    logger.info(f"[AnyihuaExtractor] 结果已保存至 {path}（共 {len(results)} 条对话）")


# --------------------------------------------------------------------------- #
# 主提取器
# --------------------------------------------------------------------------- #


class AnyihuaKnowledgeExtractor:
    """
    安逸花外呼对话知识提取器（单轮对话 + langextract 溯源版）。

    核心流程：
    1. 逐轮解析对话（每轮作为独立文本单元，解决 langextract 处理多轮对话的问题）
    2. 将完整对话（含轮次标记）送给 LLM，LLM 输出每条知识所属的 turn_idx
    3. 对每条知识，仅在其对应轮次的文本上执行 langextract WordAligner 对齐
       （短文本 = 高精度字符级溯源）
    4. 生成单一 provenance 字段，格式含轮次编号与字符位置

    LLM 通过 ``contextmind/infra/llm_client.py`` + ``.env`` 统一初始化。

    参数:
        llm_client: 可选的 SimpleLLMClient 实例；不传则自动从 .env 加载
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
        从单条原始对话中提取带轮次归属与溯源的结构化知识。

        参数:
            dialogue: chat_test_100.json 中的单条对话条目

        返回:
            ExtractionResult，每条知识的 provenance 字段格式为
            「片段」[第N轮(说话人) 位置 s:e] 或 「片段」[第N轮(说话人) 溯源失败]
        """
        dialogue_id = str(dialogue.get("session_id") or dialogue.get("dialogue_id", ""))
        logger.info(
            f"[AnyihuaExtractor] ── 开始处理对话 {dialogue_id or '(无ID)'} ──"
        )

        # Step 1: 逐轮解析
        source_text, turns = _parse_turns(dialogue)
        if not turns:
            logger.warning(f"[AnyihuaExtractor] 对话为空，跳过: {dialogue_id}")
            return ExtractionResult(
                dialogue_id=dialogue_id,
                source_text="",
                turns=[],
                knowledge_items=[],
                stats={"total": 0, "aligned": 0, "unaligned": 0, "alignment_rate": 0.0, "turns": 0},
            )

        logger.info(
            f"[AnyihuaExtractor] 共 {len(turns)} 轮对话，"
            f"坐席 {sum(1 for _, sp, _ in turns if sp == '坐席')} 轮，"
            f"用户 {sum(1 for _, sp, _ in turns if sp == '用户')} 轮"
        )

        # Step 2: LLM 提取（含轮次感知 prompt）
        logger.info("[AnyihuaExtractor] 调用 LLM 进行知识提取（含轮次标记）…")
        raw_items = self._call_llm(source_text)
        if not raw_items:
            logger.warning(f"[AnyihuaExtractor] LLM 未返回任何提取结果: {dialogue_id}")
            return ExtractionResult(
                dialogue_id=dialogue_id,
                source_text=source_text,
                turns=turns,
                knowledge_items=[],
                stats={"total": 0, "aligned": 0, "unaligned": 0, "alignment_rate": 0.0, "turns": len(turns)},
            )

        logger.info(f"[AnyihuaExtractor] LLM 返回 {len(raw_items)} 条候选提取结果")

        # Step 3: 逐条进行轮级 WordAligner 对齐
        turn_map = {idx: (sp, utt) for idx, sp, utt in turns}
        knowledge_items: List[KnowledgeItem] = []
        aligned_count = 0
        skipped_count = 0

        for i, item in enumerate(raw_items):
            cls = str(item.get("extraction_class", "")).strip()
            label = str(item.get("label", "")).strip()
            value = str(item.get("value", "")).strip()
            prov_text = str(item.get("provenance_text", "")).strip()

            # 解析 turn_idx（容忍格式变体：可能是字符串）
            raw_turn_idx = item.get("turn_idx", -1)
            try:
                turn_idx = int(raw_turn_idx)
            except (TypeError, ValueError):
                turn_idx = -1

            if not (cls and label and value and prov_text):
                logger.debug(
                    f"[AnyihuaExtractor] 跳过字段不完整的提取结果 #{i+1}: "
                    f"cls={cls!r} label={label!r} value={value!r}"
                )
                skipped_count += 1
                continue

            # 获取对应轮次的说话人和话语文本
            if turn_idx in turn_map:
                speaker, turn_text = turn_map[turn_idx]
            else:
                logger.debug(
                    f"[AnyihuaExtractor] turn_idx={turn_idx} 超出范围（共 {len(turns)} 轮），"
                    f"无法定位: [{cls}] {label}: {value[:30]}"
                )
                speaker = ""
                turn_text = ""
                turn_idx = -1

            # 轮级 WordAligner 对齐（只对该轮短文本对齐）
            char_start, char_end = _align_to_turn(prov_text, turn_text)

            if char_start is not None:
                aligned_count += 1
                logger.debug(
                    f"[AnyihuaExtractor] ✓ [{cls}] {label}: {value[:30]} "
                    f"← 第{turn_idx+1}轮({speaker}) 位置[{char_start}:{char_end}]"
                )
            else:
                logger.debug(
                    f"[AnyihuaExtractor] △ [{cls}] {label}: {value[:30]} "
                    f"← 第{turn_idx+1}轮({speaker}) 溯源失败（「{prov_text[:20]}」）"
                )

            provenance = _build_provenance(prov_text, turn_idx, speaker, char_start, char_end)
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

        # 日志汇总
        slot_count = sum(1 for it in knowledge_items if it.extraction_class == "slot_value")
        intent_count = sum(1 for it in knowledge_items if it.extraction_class == "intent")
        fact_count = sum(1 for it in knowledge_items if it.extraction_class == "fact")
        logger.info(
            f"[AnyihuaExtractor] 提取完成: {dialogue_id} | "
            f"共 {total} 条（槽位 {slot_count} / 意图 {intent_count} / 事实 {fact_count}）| "
            f"溯源成功 {aligned_count}/{total}（{stats['alignment_rate']:.1%}）| "
            f"跳过 {skipped_count} 条（字段不完整）"
        )

        return ExtractionResult(
            dialogue_id=dialogue_id,
            source_text=source_text,
            turns=turns,
            knowledge_items=knowledge_items,
            stats=stats,
        )

    def extract_batch(
        self,
        dialogues: Sequence[Dict[str, Any]],
        stop_on_error: bool = False,
        save_path: Optional[Path] = None,
    ) -> List[ExtractionResult]:
        """
        批量提取多条对话的知识，并可选择自动保存结果文件。

        参数:
            dialogues:      对话条目列表（chat_test_100.json 内容）
            stop_on_error:  True 则遇到异常立即抛出；False 则跳过并记录日志（默认）
            save_path:      如指定，批量提取完成后自动保存 JSON 结果至此路径

        返回:
            ExtractionResult 列表（与 dialogues 一一对应，失败条目为空结果）
        """
        total = len(dialogues)
        logger.info(
            f"[AnyihuaExtractor] ═══ 开始批量提取，共 {total} 条对话 ═══"
        )
        results: List[ExtractionResult] = []

        for idx, dialogue in enumerate(dialogues):
            dialogue_id = str(
                dialogue.get("session_id") or dialogue.get("dialogue_id", f"#{idx}")
            )
            logger.info(
                f"[AnyihuaExtractor] 处理进度 [{idx + 1}/{total}] → {dialogue_id}"
            )
            try:
                results.append(self.extract(dialogue))
            except Exception as exc:
                if stop_on_error:
                    raise
                logger.error(
                    f"[AnyihuaExtractor] ✗ 提取失败（{dialogue_id}）: {exc}，使用空结果"
                )
                _, turns = _parse_turns(dialogue)
                source_text = "\n".join(
                    f"[第{i+1}轮({sp})] {utt}" for i, sp, utt in turns
                )
                results.append(
                    ExtractionResult(
                        dialogue_id=dialogue_id,
                        source_text=source_text,
                        turns=turns,
                        knowledge_items=[],
                        stats={
                            "total": 0,
                            "aligned": 0,
                            "unaligned": 0,
                            "alignment_rate": 0.0,
                            "turns": len(turns),
                            "error": str(exc),
                        },
                    )
                )

        # 汇总日志
        total_items = sum(len(r.knowledge_items) for r in results)
        total_aligned = sum(r.stats.get("aligned", 0) for r in results)
        overall_rate = total_aligned / total_items if total_items else 0.0
        logger.info(
            f"[AnyihuaExtractor] ═══ 批量提取完成 ═══ "
            f"对话 {len(results)} 条 | 知识条目 {total_items} 条 | "
            f"整体溯源率 {overall_rate:.1%}"
        )

        # 保存结果文件
        if save_path is not None:
            save_results(results, Path(save_path))

        return results

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _call_llm(self, source_text: str) -> List[Dict[str, Any]]:
        """
        调用 LLM 提取结构化知识（含轮次标记的完整对话文本）。

        通过 SimpleLLMClient.generate() 统一调用，与 .env 配置对应。
        LLM 输出中包含 turn_idx 字段，用于后续轮级 WordAligner 对齐。
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
    从单条安逸花外呼对话中提取带轮次归属与溯源的结构化知识（便捷函数）。

    参数:
        dialogue:    原始对话条目（chat_test_100.json 单条）
        llm_client:  可选的 SimpleLLMClient 实例；若不传入则自动从 .env 加载

    返回:
        ExtractionResult，每条知识项的 provenance 字段含轮次归属与字符位置
    """
    extractor = AnyihuaKnowledgeExtractor(llm_client=llm_client)
    return extractor.extract(dialogue)
