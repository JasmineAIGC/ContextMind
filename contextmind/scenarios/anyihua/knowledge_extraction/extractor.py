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

# 匹配 LLM 可能在 provenance_text 中附加的轮次前缀，如 [第1轮(坐席)] 或 [第12轮(用户)]
_TURN_LABEL_RE = re.compile(r"^\[第\d+轮\([^)]*\)\]\s*")
# 匹配说话人前缀（LLM 偶尔把原始文件里的 "坐席：" 或 "用户：" 带入 provenance_text）
_SPEAKER_PREFIX_RE = re.compile(r"^(坐席|用户)[：:]\s*")
# 匹配被「」包裹的文本（LLM 有时会给 provenance_text 加引号）
_CHINESE_QUOTE_RE = re.compile(r"^「(.+)」$")

# 最多清除轮次：3 种前缀/包裹可能相互嵌套（如 [第N轮(坐席)] 「坐席：xxx」），
# 最多嵌套 3 层，加 1 次收敛确认，共 4 次迭代足够覆盖所有实际情况
_MAX_CLEANING_ITERATIONS = 4



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


def _clean_provenance_text(raw: str) -> str:
    """
    清除 LLM 在 provenance_text 中附加的冗余前缀或包裹符号。

    处理以下三类 LLM 常见错误（反复应用直到稳定，支持多层嵌套）：
    1. 轮次前缀：`[第N轮(说话人)] ` — LLM 从 source_text 直接复制了整行（含标记）
    2. 说话人前缀：`坐席：` / `用户：` — LLM 带入了原始文件的话者标签
    3. 中文引号包裹：`「…」` — LLM 使用引号包裹 verbatim 文本

    每种清除仅去除前缀或外层包裹，不会改写话语内容本身，因此不存在"过度清除"。
    例如：`[第3轮(坐席)] 「您好，我是坐席：小李」` → `您好，我是坐席：小李`
    （内部的"坐席："不会被误删，因为 _SPEAKER_PREFIX_RE 只匹配行首）

    参数:
        raw: LLM 原始返回的 provenance_text 字段

    返回:
        去除上述噪声后的干净文本，若结果为空则返回原始值（避免全部丢失）
    """
    text = raw.strip()
    # 反复清除，直到稳定（处理多层嵌套，如 [第3轮(坐席)] 「您好」 → 「您好」 → 您好）
    # _MAX_CLEANING_ITERATIONS 次足以覆盖最多 3 层嵌套 + 1 次收敛确认
    for _ in range(_MAX_CLEANING_ITERATIONS):
        prev = text
        # 1. 去除「」包裹
        m = _CHINESE_QUOTE_RE.match(text)
        if m:
            text = m.group(1).strip()
        # 2. 去除轮次标签前缀 [第N轮(xxx)]
        text = _TURN_LABEL_RE.sub("", text).strip()
        # 3. 去除说话人前缀 坐席：/ 用户：
        text = _SPEAKER_PREFIX_RE.sub("", text).strip()
        if text == prev:
            break  # 已稳定，不再循环
    return text if text else raw


def _align_to_turn(
    provenance_text: str,
    turn_text: str,
) -> Tuple[Optional[int], Optional[int]]:
    """
    将 provenance_text 精确对齐到单轮话语文本的字符区间。

    对齐策略（依优先级）：
    1. 预处理：清除 LLM 在 provenance_text 中附加的轮次前缀/引号/说话人前缀
    2. 快速路径：直接 str.find()，处理精确子串（最常见、最可靠）
    3. WordAligner 回退：处理近似匹配（LLM 轻微改写等边缘情况）

    注意：_clean_provenance_text 只去除行首前缀/外层包裹，不会过度清除话语内容。
    因此清除前后的两种 provenance_text 都尝试 str.find()，仅当两者不同时才
    额外尝试 raw（防御性措施，应对极端边缘情况）。

    参数:
        provenance_text: LLM 给出的 verbatim 原文片段（可能含噪声前缀）
        turn_text:       该轮次的原始话语文本（单段，已去掉说话人前缀）

    返回:
        (char_start, char_end) 或 (None, None)（对齐失败）
    """
    if not provenance_text or not turn_text:
        return None, None

    # Step 1: 预处理——清除 LLM 附加的冗余前缀 / 引号
    cleaned = _clean_provenance_text(provenance_text)

    # Step 2: 快速路径——精确子串查找（O(n)，最可靠）
    pos = turn_text.find(cleaned)
    if pos >= 0:
        return pos, pos + len(cleaned)

    # 若 cleaned 与 raw 不同（清除了某些前缀），也尝试原始文本——
    # 防御极端边缘情况（如 provenance_text 本身就是话语全文，含本应属于内容的「」）
    if cleaned != provenance_text:
        pos_raw = turn_text.find(provenance_text)
        if pos_raw >= 0:
            return pos_raw, pos_raw + len(provenance_text)

    # Step 3: WordAligner 回退（处理 LLM 轻微改写 / 近似匹配）
    try:
        exts = [Extraction(extraction_class="x", extraction_text=cleaned)]
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
        logger.debug(f"[WordAligner] 对齐异常（{cleaned!r}）: {exc}")
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

# 安逸花外呼业务 Schema（与 resources/anyihua_sgd/schema.json 对齐）
_SCHEMA_CONTEXT = """\
【提取 Schema（安逸花外呼业务）】

槽位值（slot_value）——与 resources/anyihua_sgd/schema.json 一致：
  - customer_name       : 客户姓名（如"高先生"、"杨女士"）
  - phone_suffix        : 手机尾号（3–4 位数字，用于身份核实）
  - dispute_date        : 用户质疑的借款日期（如"七月二十三号"）
  - inquiry_amount      : 用户询问或质疑的金额（元）
  - term_months         : 用户询问的分期期数（如 12）
  - identity_confirmed  : 身份是否已核实（true / false）
  - available_credit    : 当前可提现额度（元）
  - temp_credit         : 临时额度上限（元）
  - temp_credit_status  : 临时额度是否有效（有效 / 已过期 / 无临时额度）
  - temp_expiry_days    : 临时额度剩余有效天数
  - annual_rate_pct     : 年化利率（%）
  - loan_count          : 当前未还清借款笔数
  - last_loan_date      : 最近一次借款日期（中文格式）
  - outstanding_amount  : 当前未还款金额（元）
  - billing_day         : 账单日（每月几号）

用户意图（intent）——与 resources/anyihua_sgd/schema.json 一致：
  - verify_identity       : 开场身份核实，确认来电者是账户本人
  - explain_credit_limit  : 告知额度情况
  - explain_interest_rate : 解释利率和还款方式
  - calculate_repayment   : 计算指定金额和期数的月还款额
  - explain_displayed_amount : 解释 APP 显示金额的构成
  - handle_loan_dispute   : 核实用户争议的借款记录
  - guide_loan_operation  : 引导用户在 APP 完成借款操作
  - escalate_to_human     : 转接人工客服
  - say_goodbye           : 礼貌告别
  - general_inquiry       : 通用询问（无法匹配其他意图时的默认意图）

关键事实（fact）：
  不属于上述两类的重要业务事实（如逾期记录、临时额度到期、已授信天数等）"""

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
- provenance_text 必须是对应轮次 **话语内容** 部分的逐字子串，不包含 "[第N轮(说话人)]" 前缀，不能改写
- provenance_text 只写话语内容本身，不要加引号「」，不要加"坐席："/"用户："前缀
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

    def convert_to_sgd(
        self,
        result: ExtractionResult,
        raw_dialogue: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        将单条提取结果与原始对话合并，转换为 SGD 格式对话字典。

        参数:
            result:       extract() 返回的 ExtractionResult
            raw_dialogue: 对应的原始对话条目

        返回:
            SGD 格式对话字典（可直接序列化为 JSON）
        """
        from .sgd_converter import to_sgd_dialogue
        return to_sgd_dialogue(result, raw_dialogue)

    def convert_to_sgd_batch(
        self,
        results: List[ExtractionResult],
        raw_dialogues: Sequence[Dict[str, Any]],
        output_dir: Optional[Path] = None,
        schema_source: Optional[Path] = None,
    ) -> List[Dict[str, Any]]:
        """
        批量将提取结果与原始对话合并，转换为 SGD 格式对话列表。

        参数:
            results:       extract_batch() 返回的 ExtractionResult 列表
            raw_dialogues: 原始对话条目列表（与 results 一一对应）
            output_dir:    若指定，自动调用 save_as_sgd() 保存文件
            schema_source: schema.json 来源路径（传给 save_as_sgd）

        返回:
            SGD 格式对话字典列表
        """
        from .sgd_converter import save_as_sgd, to_sgd_dialogue
        n = min(len(results), len(raw_dialogues))
        logger.info(f"[AnyihuaExtractor] ═══ 开始 SGD 格式转换，共 {n} 条对话 ═══")

        sgd_dialogues: List[Dict[str, Any]] = []
        for i in range(n):
            try:
                sgd_dialogues.append(to_sgd_dialogue(results[i], raw_dialogues[i]))
            except Exception as exc:
                logger.error(
                    f"[AnyihuaExtractor] ✗ SGD 转换失败 [{i}] "
                    f"({results[i].dialogue_id}): {exc}"
                )

        logger.info(
            f"[AnyihuaExtractor] SGD 转换完成: {len(sgd_dialogues)} 条对话，"
            f"共 {sum(len(d['turns']) for d in sgd_dialogues)} 轮"
        )

        if output_dir is not None:
            save_as_sgd(
                results=results,
                raw_dialogues=list(raw_dialogues),
                output_dir=Path(output_dir),
                schema_source=schema_source,
            )

        return sgd_dialogues

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
