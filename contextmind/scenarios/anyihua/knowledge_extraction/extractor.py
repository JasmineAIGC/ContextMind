"""
安逸花外呼 · 知识提取（单轮对话 + langextract 溯源版）

核心设计：逐轮提取 + 轮级溯源 + 动态 Schema
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
5. **动态 Schema**：槽位、意图、事实定义均可通过 ``ExtractionSchema`` 灵活配置，
   支持开放式提取（LLM 自由命名 label）或预定义受限提取。

工作流程::

    原始对话 (chat_test_100.json 条目)
        │
        ▼
    逐轮解析（_parse_turns）
    [(idx, speaker, utterance), ...]
        │
        ▼
    LLM 提取（含轮次感知 prompt + ExtractionSchema 生成的 schema 段落）
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
    ExtractionResult（可 JSON 序列化，可保存文件，可转为 SGD 格式）

LLM 客户端通过 ``contextmind/infra/llm_client.py`` + ``.env`` 统一初始化。

典型使用::

    import json
    from pathlib import Path
    from contextmind.scenarios.anyihua.knowledge_extraction import (
        AnyihuaKnowledgeExtractor,
        ExtractionSchema, SlotDefinition, IntentDefinition,
        DEFAULT_SCHEMA, STATS_FIELD_DESCRIPTIONS,
    )

    dialogues = json.loads(Path("resources/data/chat_test_100.json").read_text())

    # 使用默认 Schema（安逸花外呼预定义槽位 + 意图）
    extractor = AnyihuaKnowledgeExtractor()

    # 或使用自定义 Schema（如换一个业务场景，或增加/修改槽位名称）
    custom_schema = ExtractionSchema(
        scene_name="银行信用卡外呼",
        slots=[
            SlotDefinition("customer_name", "客户姓名"),
            SlotDefinition("card_limit", "信用卡额度"),
        ],
        intents=[
            IntentDefinition("verify_identity", "身份核实"),
            IntentDefinition("explain_bill", "账单说明"),
        ],
        fact_description="其他重要信用卡业务事实",
        slot_open_ended=True,  # 允许 LLM 在上述列表之外自由提取新槽位
    )
    extractor = AnyihuaKnowledgeExtractor(schema=custom_schema)

    # 单条提取
    result = extractor.extract(dialogues[0])
    for item in result.knowledge_items:
        print(f"[第{item.turn_idx+1}轮({item.speaker})] [{item.extraction_class}] {item.label}: {item.value}")
        print(f"  溯源: {item.provenance}")

    # 查看统计字段说明
    for key, info in result.stats_explained.items():
        print(f"{key}={info['value']}  —— {info['description']}")

    # 批量提取，结果自动保存为文件
    results = extractor.extract_batch(dialogues[:10], save_path=Path("data/results.json"))
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

# --------------------------------------------------------------------------- #
# langextract — 数据类型 + 溯源对齐工具
# --------------------------------------------------------------------------- #
from langextract.data import AlignmentStatus, Extraction
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

# 溯源对齐的临近轮次搜索窗口（±N 轮）。
# 设为 3 可覆盖 LLM 最常见的 ±1 偏差（含跨说话人的转换），保留余量到 ±3。
_NEARBY_SEARCH_WINDOW = 3

# 全量搜索时要求 provenance_text 最少字符数，避免超短文本在无关轮次中误匹配。
_MIN_PROVENANCE_LEN_FOR_GLOBAL_SEARCH = 4


# --------------------------------------------------------------------------- #
# 提取统计字段说明
# --------------------------------------------------------------------------- #

#: 每个统计字段的中文说明，可用于展示给用户。
STATS_FIELD_DESCRIPTIONS: Dict[str, str] = {
    "total": (
        "本次提取出的知识条目总数（槽位值 + 意图 + 事实之和，不含被跳过的不完整条目）"
    ),
    "aligned": (
        "成功完成字符区间溯源的条目数，即 provenance_text 能在对应轮次话语中精确定位"
        "（含精确匹配、WordAligner 模糊匹配、difflib 滑窗模糊匹配三种方式）"
    ),
    "unaligned": (
        "溯源失败的条目数：provenance_text 无法在任何轮次话语中定位，"
        "通常因 LLM 大幅改写了原话（相似度低于 80%），或 provenance_text 本身不是对话原文"
    ),
    "alignment_rate": (
        "溯源成功率 = aligned / total，介于 0.0（完全失败）和 1.0（全部成功）之间，"
        "越高说明 LLM 返回的 provenance_text 质量越好"
    ),
    "turn_corrected": (
        "溯源时发现 LLM 给出的 turn_idx 有偏差，系统通过临近轮次搜索自动修正的条目数。"
        "常见原因：LLM 将 turn_idx 偏移了 ±1（典型的说话人混淆）"
    ),
    "global_search_found": (
        "turn_idx 无效或临近搜索失败后，通过全量扫描所有轮次成功定位 provenance_text 的条目数"
    ),
    "skipped_incomplete": (
        "因字段缺失（extraction_class / label / value / provenance_text 任一为空）"
        "而被丢弃的 LLM 返回条目数，不计入 total"
    ),
    "dedup_removed": (
        "跨轮去重时移除的重复条目数（槽位、事实、意图均参与去重）。"
        "包含两个阶段：① 同一 label 在多轮重复出现时保留最新值，移除早期重复；"
        "② 不同 label 但值高度相似（≥ 85%）时移除早期重复。移除数即为此值"
    ),
    "updated_count": (
        "跨轮去重中检测到的值变更次数（旧值 → 新值的 UPDATE 数）。"
        "涵盖槽位（slot_value）、事实（fact）、意图（intent）三类知识的更新，"
        "变更记录在 ExtractionResult.updates 列表中，可用于追踪用户对信息的纠正或意图变化"
    ),
    "turns": (
        "本条对话拆解后的总轮次数（每句坐席话语或用户话语为一轮）"
    ),
    "error": (
        "批量处理时捕获的异常信息（仅在该条对话提取出错时出现）"
    ),
}


# --------------------------------------------------------------------------- #
# 动态提取 Schema
# --------------------------------------------------------------------------- #


@dataclass
class SlotDefinition:
    """
    单个槽位定义。

    属性:
        name:        槽位名称（英文，作为 JSON key 和 label 使用）
        description: 槽位含义说明（中文，用于生成提示词）
    """

    name: str
    description: str


@dataclass
class IntentDefinition:
    """
    单个意图定义。

    属性:
        name:        意图名称（英文）
        description: 意图含义说明（中文）
    """

    name: str
    description: str


@dataclass
class ExtractionSchema:
    """
    动态提取 Schema：定义本次提取所用的槽位、意图和事实描述。

    不同业务场景可定义不同的 Schema，传入 ``AnyihuaKnowledgeExtractor``
    以替换默认的安逸花外呼 Schema。

    属性:
        scene_name:      业务场景名称（中文，用于提示词标题，如"安逸花外呼"）
        slots:           槽位定义列表；为空时允许 LLM 自由命名槽位（开放槽位模式）
        intents:         意图定义列表；为空时允许 LLM 自由命名意图（开放意图模式）
        fact_description:对话中"事实（fact）"类知识的补充说明，用于 prompt
        slot_open_ended: True = 允许 LLM 提取不在 slots 列表中的槽位（仅当 slots 非空）
        intent_open_ended:True = 允许 LLM 提取不在 intents 列表中的意图（仅当 intents 非空）

    示例::

        from contextmind.scenarios.anyihua.knowledge_extraction import ExtractionSchema, SlotDefinition, IntentDefinition

        schema = ExtractionSchema(
            scene_name="银行贷款外呼",
            slots=[
                SlotDefinition("customer_name", "客户姓名"),
                SlotDefinition("loan_amount", "贷款金额（元）"),
                SlotDefinition("repayment_date", "还款日期"),
            ],
            intents=[
                IntentDefinition("verify_identity", "核实身份"),
                IntentDefinition("explain_terms", "解释贷款条款"),
            ],
            fact_description="其他重要的贷款业务事实",
            slot_open_ended=True,   # 允许 LLM 提取 schema 之外的槽位
            intent_open_ended=False,
        )
        extractor = AnyihuaKnowledgeExtractor(schema=schema)
    """

    scene_name: str = "安逸花外呼"
    slots: List[SlotDefinition] = field(default_factory=list)
    intents: List[IntentDefinition] = field(default_factory=list)
    fact_description: str = (
        "不属于上述两类的重要业务事实（如逾期记录、临时额度到期、已授信天数等）"
    )
    slot_open_ended: bool = False
    intent_open_ended: bool = False


#: 默认安逸花外呼业务 Schema（与 resources/anyihua_sgd/schema.json 对齐）。
#: 可作为模板 clone 后修改，传给 AnyihuaKnowledgeExtractor(schema=...)。
#:
#: 意图分类说明：
#:   【坐席意图】前缀为 "agent_" 或无前缀（verify_identity / explain_* / calculate_* 等）
#:   【用户意图】前缀为 "user_" 或明确说明"用户..."（complain_* / express_* 等）
#:   · 坐席意图从坐席轮次提取，用户意图从用户轮次提取
#:   · general_inquiry 是最后兜底意图，仅当用户回复完全无法匹配其他任何意图时才使用
DEFAULT_SCHEMA = ExtractionSchema(
    scene_name="安逸花外呼",
    slots=[
        # ── 身份核实相关 ──
        SlotDefinition("customer_name", '客户姓名（如"高先生"、"杨女士"）'),
        SlotDefinition("phone_suffix", "手机尾号（3–4 位数字，用于身份核实）"),
        SlotDefinition("identity_confirmed", "身份是否已核实（true / false）"),
        # ── 额度相关 ──
        SlotDefinition("available_credit", "当前可提现额度（元）"),
        SlotDefinition("credit_limit", "账户授信总额度（元）"),
        SlotDefinition("temp_credit", "临时额度上限（元）"),
        SlotDefinition("temp_credit_status", "临时额度是否有效（有效 / 已过期 / 无临时额度）"),
        SlotDefinition("temp_expiry_days", "临时额度剩余有效天数"),
        SlotDefinition("temp_credit_expiry_date", '临时额度到期日期（如"十月二十六号"）'),
        # ── 利率与还款相关 ──
        SlotDefinition("annual_rate_pct", "年化利率（%，如 24 表示 24%）"),
        SlotDefinition("daily_rate_pct", "日利率（%，如 0.065 表示 0.065%）"),
        SlotDefinition("monthly_payment", "用户询问或坐席告知的月还款额（元）"),
        SlotDefinition("total_interest", "用户询问或坐席告知的总利息（元）"),
        SlotDefinition("term_months", "用户询问的分期期数（如 12）"),
        SlotDefinition("billing_day", "账单日（每月几号）"),
        SlotDefinition("repayment_date", '还款日（如"十一月一号"）'),
        # ── 借款记录相关 ──
        SlotDefinition("loan_count", "当前未还清借款笔数"),
        SlotDefinition("last_loan_date", "最近一次借款日期（中文格式）"),
        SlotDefinition("outstanding_amount", "当前未还款金额（元）"),
        SlotDefinition("dispute_date", '用户质疑的借款日期（如"七月二十三号"）'),
        SlotDefinition("inquiry_amount", "用户询问或质疑的金额（元）"),
        SlotDefinition("overdue_days", "逾期天数"),
        # ── 用户态度与期望相关 ──
        SlotDefinition("user_expected_interest", '用户对合理利息的期望金额（元），如"一万块一年应该八九百"'),
        SlotDefinition("user_complaint_reason", "用户抱怨或拒绝的具体原因（如还款太麻烦、利率太高等）"),
    ],
    intents=[
        # ── 坐席主导意图（从坐席轮次提取）──
        IntentDefinition("verify_identity", "【坐席】开场身份核实，确认来电者是账户本人"),
        IntentDefinition("explain_credit_limit", "【坐席】告知用户当前可提现额度及授信额度情况"),
        IntentDefinition("explain_interest_rate", "【坐席】解释贷款利率（年化/日利率）和还款方式"),
        IntentDefinition("calculate_repayment", "【坐席】根据用户需求计算指定金额和期数的月还款额及总利息"),
        IntentDefinition("explain_displayed_amount", "【坐席】解释 APP 页面显示金额的构成或计算逻辑"),
        IntentDefinition("handle_loan_dispute", "【坐席】核实并回应用户对某笔借款记录（日期/金额）的争议"),
        IntentDefinition("guide_loan_operation", "【坐席】引导用户在 APP 完成借款操作步骤"),
        IntentDefinition("promote_loan_offer", "【坐席】主动推介借款优惠、介绍产品亮点或邀请用户使用额度"),
        IntentDefinition("explain_temp_credit", "【坐席】解释临时额度的有效期、金额及使用规则"),
        IntentDefinition("escalate_to_human", "【坐席/用户】请求或承诺转接人工客服"),
        IntentDefinition("say_goodbye", "【坐席/用户】礼貌结束对话、道别"),
        # ── 用户主导意图（从用户轮次提取）──
        IntentDefinition("complain_repayment", "【用户】抱怨月还款额太高、还款方式太麻烦或还款压力大；关键词：还款太麻烦、要还多少、还起太恼火、月供太高"),
        IntentDefinition("complain_interest_rate", "【用户】质疑或抱怨利率偏高、利息太贵；关键词：利息有点高、太高了、利率高"),
        IntentDefinition("express_interest_expectation", "【用户】表达对合理利率/利息的期望或认知，或将当前利息与期望金额比较；关键词：一万块一年应该八九百、一千多太高了、应该只有八百多"),
        IntentDefinition("confirm_information", "【用户】确认或认可坐席提供的信息；关键词：对、好的、明白、是的、嗯"),
        IntentDefinition("reject_offer", "【用户】明确拒绝当前借款方案或产品；关键词：不用了、不需要、不借了"),
        IntentDefinition("ask_for_clarification", "【用户】要求坐席进一步解释某项内容；关键词：为什么、怎么算的、能说清楚吗"),
        IntentDefinition("dispute_loan_record", "【用户】对某笔借款记录提出质疑或否认；关键词：我没有借这笔、这不是我的借款"),
        IntentDefinition("inquire_repayment_method", "【用户】询问还款方式、还款渠道或操作步骤"),
        IntentDefinition("express_hesitation", "【用户】表示犹豫、考虑中或需要时间决定；关键词：我想想、再看看、暂时不用"),
        IntentDefinition("general_inquiry", "【用户·兜底】用户回复完全无法匹配以上任何具体意图时的最后兜底；仅在穷尽所有其他意图后仍无法归类时使用"),
    ],
    fact_description="对话中出现的重要业务事实，不属于槽位值也不属于意图（如：逾期记录说明、临时额度已到期的告知、账户异常状态、坐席的关键承诺等）",
    slot_open_ended=False,
    intent_open_ended=False,
)


def _build_schema_context(schema: ExtractionSchema) -> str:
    """
    将 ExtractionSchema 转换为 prompt 中的 Schema 说明段落。

    参数:
        schema: 动态提取 Schema 对象

    返回:
        格式化好的中文 Schema 说明字符串（直接嵌入 system prompt）
    """
    lines: List[str] = [f"【提取 Schema（{schema.scene_name}业务）】"]

    # 槽位部分
    if schema.slots:
        lines.append("")
        lines.append("槽位值（slot_value）——提取时 label 必须从以下名称中选取：")
        max_name_len = max((len(s.name) for s in schema.slots), default=0)
        for s in schema.slots:
            padding = " " * (max_name_len - len(s.name))
            lines.append(f"  - {s.name}{padding} : {s.description}")
        if schema.slot_open_ended:
            lines.append(
                "  （以上为参考列表，如对话中出现以上未涵盖的重要槽位，"
                "可自行命名并提取）"
            )
    else:
        lines.append("")
        lines.append(
            "槽位值（slot_value）——对话中涉及的所有业务槽位，"
            "请根据对话内容自行命名 label（无预定义列表）。"
        )

    # 意图部分
    if schema.intents:
        lines.append("")
        lines.append("用户意图（intent）——提取时 label 必须从以下名称中选取：")
        max_name_len = max((len(i.name) for i in schema.intents), default=0)
        for i in schema.intents:
            padding = " " * (max_name_len - len(i.name))
            lines.append(f"  - {i.name}{padding} : {i.description}")
        if schema.intent_open_ended:
            lines.append(
                "  （以上为参考列表，如对话中出现以上未涵盖的意图，"
                "可自行命名并提取）"
            )
    else:
        lines.append("")
        lines.append(
            "用户意图（intent）——对话中体现的所有意图，"
            "请根据对话内容自行命名 label（无预定义列表）。"
        )

    # 事实部分
    lines.append("")
    lines.append(f"关键事实（fact）：\n  {schema.fact_description}")

    return "\n".join(lines)





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
class ValueUpdate:
    """
    记录跨轮知识值更新（动态处理：UPDATE 操作）。

    当同一 ``label`` 的 ``slot_value``、``fact`` 或 ``intent`` 在多轮中
    出现不同的值时，表明用户或坐席对该信息进行了纠正或更新。

    属性:
        extraction_class: 知识类别，"slot_value" / "fact" / "intent"
        label:            槽位名、事实标签或意图编码
        old_value:        首次出现的旧值（已被覆盖）
        new_value:        最终确定的新值（最后一次出现）
        old_turn_idx:     旧值出现的轮次（0-based）
        new_turn_idx:     新值出现的轮次（0-based）
    """

    extraction_class: str
    label: str
    old_value: str
    new_value: str
    old_turn_idx: int
    new_turn_idx: int

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
        updates:        跨轮值变更记录，仅当 slot_value/fact 的 value 发生变化时有条目
        stats:          提取统计字典，各字段含义见 STATS_FIELD_DESCRIPTIONS
        extracted_at:   提取时间戳
    """

    dialogue_id: str
    source_text: str
    turns: List[Tuple[int, str, str]] = field(default_factory=list)
    knowledge_items: List[KnowledgeItem] = field(default_factory=list)
    updates: List[ValueUpdate] = field(default_factory=list)
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
            "updates": [u.to_dict() for u in self.updates],
            "stats": self.stats,
            "extracted_at": self.extracted_at,
        }

    @property
    def stats_explained(self) -> Dict[str, Dict[str, Any]]:
        """
        返回带字段说明的统计信息，格式为 ``{字段名: {"value": ..., "description": ...}}``。

        示例::

            for key, info in result.stats_explained.items():
                print(f"{key}: {info['value']}  —— {info['description']}")
        """
        return {
            key: {
                "value": val,
                "description": STATS_FIELD_DESCRIPTIONS.get(key, ""),
            }
            for key, val in self.stats.items()
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


# --------------------------------------------------------------------------- #
# difflib 滑窗模糊匹配（辅助函数）
# --------------------------------------------------------------------------- #

# 滑窗模糊匹配使用的最小相似度阈值（0.0-1.0）。
# 0.80 表示至少 80% 字符相匹配，可处理 LLM 小幅改写（删减/替换 1-2 个字）。
_FUZZY_MIN_RATIO: float = 0.80

# 启用滑窗模糊匹配的最短查询长度（字符数）。
# 短于此长度的 provenance_text 在滑窗中极易误匹配，不做模糊处理。
_FUZZY_MIN_QUERY_LEN: int = 6

# 滑窗长度相对于查询长度的浮动范围（±N 字符）。
# ±2 允许 LLM 轻微缩减或扩展文本（如省略标点、添加"啊/嘛"语气词等）。
_FUZZY_WINDOW_DELTA: int = 2


def _fuzzy_align_provenance(
    query: str,
    text: str,
    min_ratio: float = _FUZZY_MIN_RATIO,
    min_length: int = _FUZZY_MIN_QUERY_LEN,
) -> Tuple[Optional[int], Optional[int]]:
    """
    使用 SequenceMatcher 滑窗算法在 text 中查找与 query 最相似的子串。

    此函数作为 _align_to_turn() 的最终兜底：当精确匹配（str.find）和
    WordAligner 均失败后调用，处理 LLM 在 provenance_text 中做出轻微改写的情况
    （例如：省略虚词、插入语气词"嘛/吧"、替换同义字符等）。

    算法：
    1. 对长度在 [max(min_length, qlen-DELTA), min(text_len, qlen+DELTA)] 范围内
       的所有子串滑窗，计算与 query 的 SequenceMatcher 相似度。
    2. 返回相似度 ≥ min_ratio 的最佳匹配区间；否则返回 (None, None)。

    注意：
    - 若 query 长于 text，退化为整段文本比较。
    - 滑窗计算复杂度为 O(text_len × query_len)，对话轮次文本通常 ≤ 200 字，
      延迟可忽略。

    参数:
        query:      经过 _clean_provenance_text 清理后的 provenance_text
        text:       该轮次的原始话语文本
        min_ratio:  最低相似度阈值（默认 0.80）
        min_length: 启用模糊匹配的最短查询长度（默认 6 字符）

    返回:
        (char_start, char_end) 或 (None, None)（无满足阈值的匹配）
    """
    if not query or not text or len(query) < min_length:
        return None, None

    qlen = len(query)
    text_len = len(text)

    if qlen > text_len:
        # 查询比文本更长：退化为整段比较
        ratio = SequenceMatcher(None, query, text).ratio()
        return (0, text_len) if ratio >= min_ratio else (None, None)

    best_ratio = 0.0
    best_start: Optional[int] = None
    best_end: Optional[int] = None

    # 滑窗长度范围：[max(min_length, qlen-δ), min(text_len, qlen+δ)]
    # 由于 qlen <= text_len（上方已处理 qlen > text_len 的情况），
    # window_len 始终 <= text_len，故 range(text_len - window_len + 1) 不会为负。
    window_min = max(min_length, qlen - _FUZZY_WINDOW_DELTA)
    window_max = min(text_len, qlen + _FUZZY_WINDOW_DELTA) + 1  # +1 使区间右开

    for window_len in range(window_min, window_max):
        for start in range(text_len - window_len + 1):
            window = text[start : start + window_len]
            ratio = SequenceMatcher(None, query, window).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_start = start
                best_end = start + window_len

    if best_ratio >= min_ratio and best_start is not None:
        return best_start, best_end
    return None, None


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
    4. difflib 滑窗模糊匹配：最终兜底，处理 WordAligner 仍无法对齐的轻微改写

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
    # 仅接受 MATCH_EXACT 或 MATCH_FUZZY 状态；MATCH_LESSER / MATCH_GREATER
    # 表示部分匹配（词元数量不足），这类结果交由 Step 4 的 difflib 重新处理。
    try:
        exts = [Extraction(extraction_class="x", extraction_text=cleaned)]
        groups = _WORD_ALIGNER.align_extractions(
            [exts],
            turn_text,
            token_offset=0,
            char_offset=0,
            tokenizer_impl=_TOKENIZER,
        )
        if groups and groups[0]:
            aligned = groups[0][0]
            is_full_match = aligned.alignment_status in (
                AlignmentStatus.MATCH_EXACT,
                AlignmentStatus.MATCH_FUZZY,
            )
            if is_full_match and aligned.char_interval is not None:
                return aligned.char_interval.start_pos, aligned.char_interval.end_pos
    except Exception as exc:
        logger.debug(f"[WordAligner] 对齐异常（{cleaned!r}）: {exc}")

    # Step 4: difflib 滑窗模糊匹配（最终兜底）
    # 处理 WordAligner 仍无法覆盖的 LLM 轻微改写（如语气词插删、同义字替换）
    s, e = _fuzzy_align_provenance(cleaned, turn_text)
    if s is not None:
        logger.debug(
            f"[FuzzyAlign] 滑窗模糊匹配成功 [{s}:{e}]（{cleaned[:20]!r}）"
        )
        return s, e

    return None, None


def _find_turn_by_search(
    provenance_text: str,
    turn_idx: int,
    turn_map: Dict[int, Tuple[str, str]],
) -> Tuple[int, str, Optional[int], Optional[int], bool, bool]:
    """
    当主对齐失败后，在临近轮次及全量轮次中搜索 provenance_text。

    对齐策略（调用方已对 turn_idx 尝试过 _align_to_turn 且失败）：

    1. **临近窗口搜索**（仅当 turn_idx ≥ 0，即 extract() 已验证为合法索引）
       在 ±_NEARBY_SEARCH_WINDOW 范围内，按距离由近到远逐轮尝试。
       这修正了 LLM 最常见的偏差：把相邻轮（尤其是说话人不同的那一轮）
       的文本标注到了错误的 turn_idx 上。

    2. **全量搜索**（兜底）
       若窗口内找不到，扫描所有其余轮次（turn_idx ≥ 0 时扫描窗口外的轮次）。
       当 turn_idx < 0（调用方已将无效或超出范围的索引归一化为 -1）时，
       跳过阶段 1，直接全量扫描所有轮次。
       为避免超短文本误匹配，要求 cleaned provenance_text 长度 ≥
       _MIN_PROVENANCE_LEN_FOR_GLOBAL_SEARCH 个字符。

    注意：extract() 会在调用本函数前将所有超出范围或非整数的 turn_idx 归一化为 -1，
    因此本函数收到的 turn_idx 只有两类：合法索引（≥ 0）或 -1。

    返回:
        (corrected_turn_idx, corrected_speaker, char_start, char_end,
         turn_was_corrected, found_by_global_search)

        · turn_was_corrected = True  表示找到的轮次与原 turn_idx 不同，
          或原 turn_idx 无效（< 0），任何找到的轮次都算修正
        · found_by_global_search = True  表示是通过全量扫描找到的（距离 > 窗口，或 turn_idx < 0）
        · 所有尝试均失败时返回 (turn_idx, orig_speaker, None, None, False, False)
    """
    orig_speaker = turn_map.get(turn_idx, ("", ""))[0]
    cleaned = _clean_provenance_text(provenance_text)
    is_invalid_idx = turn_idx < 0

    if not is_invalid_idx:
        # ── 阶段 1：临近窗口搜索 ──
        others_sorted = sorted(
            [t for t in turn_map if t != turn_idx],
            key=lambda t: abs(t - turn_idx),
        )
        for t in others_sorted:
            if abs(t - turn_idx) > _NEARBY_SEARCH_WINDOW:
                break  # 已按距离升序排列，超出窗口后无需继续
            sp, utt = turn_map[t]
            s, e = _align_to_turn(provenance_text, utt)
            if s is not None:
                logger.debug(
                    f"[AnyihuaExtractor] 临近修正 turn_idx: {turn_idx}→{t}"
                    f" (Δ={t - turn_idx:+d})"
                )
                return t, sp, s, e, True, False

        # ── 阶段 2：全量扫描（窗口外的轮次） ──
        outer_cands = [t for t in others_sorted if abs(t - turn_idx) > _NEARBY_SEARCH_WINDOW]
    else:
        # turn_idx 无效（-1），直接全量扫描所有轮次
        outer_cands = sorted(turn_map.keys())

    if len(cleaned) >= _MIN_PROVENANCE_LEN_FOR_GLOBAL_SEARCH:
        for t in outer_cands:
            sp, utt = turn_map[t]
            s, e = _align_to_turn(provenance_text, utt)
            if s is not None:
                logger.debug(
                    f"[AnyihuaExtractor] 全量搜索找到 turn_idx: {turn_idx}→{t}"
                    + (f" (Δ={t - turn_idx:+d})" if not is_invalid_idx else "")
                )
                # 任何 turn_idx 变化都算修正（is_invalid_idx 时 t ≥ 0 ≠ -1，必然修正）
                return t, sp, s, e, True, True

    return turn_idx, orig_speaker, None, None, False, False


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
# 跨轮去重
# --------------------------------------------------------------------------- #


def _normalize_text(text: str) -> str:
    """规范化文本，用于值相似度比较（折叠空白、去标点、转小写）。

    此处保留单词间的单个空格（仅折叠多余空白），而非完全去除空格，
    以保持词边界的语义意义（例如"用户 拒绝"与"用户拒绝"视为等效）。
    """
    text = text.strip().lower()
    # 将全角空格 \u3000 及多个连续空白折叠为单个半角空格
    text = re.sub(r'[\u3000\s]+', ' ', text).strip()
    # 去除常见中英文标点
    text = re.sub(r'[，。！？,.!?；：""''【】()（）—、/／-]', '', text)
    return text


def _deduplicate_knowledge_items(
    items: List[KnowledgeItem],
) -> Tuple[List[KnowledgeItem], List[ValueUpdate]]:
    """
    对提取结果进行全类别去重，同时记录值变更（动态处理：ADD / DELETE / UPDATE）。

    **去重规则（所有三类知识均参与去重）：**

    第一阶段 — 标签去重（label-based dedup）
        ``slot_value``、``fact``、``intent``：
        相同 ``label`` 的条目只保留最后一次（最新值）。
        - 重复提及（值不变）：早期条目视为 DELETE，仅保留最新 ADD
        - 值发生变更：记录 ``ValueUpdate``（旧值→新值，即 UPDATE 操作）
        这样，三类知识均完整支持动态处理语义：ADD / DELETE / UPDATE。

    第二阶段 — 值相似度去重（value-based cross-label dedup）
        在标签去重之后，进一步检测同类知识中值高度相似（≥ 0.85）但标签不同的条目。
        此类情况通常由 LLM 对同一信息用不同标签重复提取导致（如"客户态度"
        与"用户态度"、"refuse_loan" 与 "拒绝借款"）。
        保留轮次最靠后的条目（最终状态），删除早期重复条目。

    参数:
        items: 所有轮次的知识条目列表（按轮次顺序）

    返回:
        (deduplicated_items, value_updates)
        deduplicated_items: 去重后的知识条目列表，严格按时序排列
        value_updates:      值变更记录列表（旧值 → 新值，含标签去重与值相似度去重产生的更新）
    """
    # ------------------------------------------------------------------ #
    # 第一阶段：标签去重（三类知识均参与）
    # ------------------------------------------------------------------ #
    _DEDUP_CLASSES = {"slot_value", "fact", "intent"}

    # 第一遍：找每个 dedup key 的最后出现位置（按时序保留最新值）
    last_occurrence_index: Dict[Tuple[str, str], int] = {}
    for i, item in enumerate(items):
        if item.extraction_class in _DEDUP_CLASSES:
            last_occurrence_index[(item.extraction_class, item.label)] = i

    # 第二遍：按时序输出，去重类只在最后出现位置输出；值变更 → ValueUpdate
    result: List[KnowledgeItem] = []
    first_occurrence: Dict[Tuple[str, str], KnowledgeItem] = {}
    value_updates: List[ValueUpdate] = []

    for i, item in enumerate(items):
        if item.extraction_class in _DEDUP_CLASSES:
            key = (item.extraction_class, item.label)
            if key not in first_occurrence:
                first_occurrence[key] = item
            if i == last_occurrence_index[key]:
                result.append(item)
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
        else:
            result.append(item)

    # ------------------------------------------------------------------ #
    # 第二阶段：值相似度去重（cross-label dedup）
    # 检测同类知识中值高度相似但标签不同的条目，删除早期重复条目。
    # ------------------------------------------------------------------ #
    _VALUE_DEDUP_CLASSES = {"fact", "intent"}
    # 0.85 的阈值在实践中可有效捕获 LLM 对同一信息使用不同标签的情况
    # （如"客户态度"与"用户态度"，相似度约 0.89），同时避免将语义不同的
    # 短句误判为重复（如"拒绝借款"与"接受借款"，相似度约 0.67）。
    _SIMILARITY_THRESHOLD = 0.85

    # 按类别分组处理，保持时序
    final_result: List[KnowledgeItem] = []
    # 记录每个类别中已保留条目的归一化值（(norm_value, item) 列表）
    retained_by_class: Dict[str, List[Tuple[str, KnowledgeItem]]] = {}

    for item in result:
        cls = item.extraction_class
        if cls not in _VALUE_DEDUP_CLASSES:
            final_result.append(item)
            continue

        norm_val = _normalize_text(item.value)
        if not norm_val:
            # 空值直接保留，不参与相似度比较
            final_result.append(item)
            retained_by_class.setdefault(cls, []).append((norm_val, item))
            continue

        retained = retained_by_class.get(cls, [])
        is_duplicate = False
        matcher = SequenceMatcher(None, norm_val, norm_val)  # 复用实例以提升性能
        for existing_norm, existing_item in retained:
            if not existing_norm:
                continue
            # 用 quick_ratio() 做廉价预筛，避免对明显不相似的文本计算完整相似度
            matcher.set_seq2(existing_norm)
            if matcher.quick_ratio() < _SIMILARITY_THRESHOLD:
                continue
            ratio = matcher.ratio()
            if ratio >= _SIMILARITY_THRESHOLD:
                # 高度相似：当前条目（时序更靠后）替换已有条目
                # 从 final_result 中移除已有条目，用当前条目替换。
                # 注：若 existing_item 在第一阶段已被移出（极罕见），remove 会抛
                # ValueError，此处安全忽略——final_result 中必然已无该条目。
                try:
                    final_result.remove(existing_item)
                except ValueError:
                    logger.debug(
                        "[AnyihuaExtractor] cross-label dedup: existing_item 已不在 "
                        "final_result 中（可能已被前一轮去重移除），安全跳过"
                    )
                # 如果值实际发生变化，记录 UPDATE
                if existing_item.value != item.value:
                    value_updates.append(
                        ValueUpdate(
                            extraction_class=item.extraction_class,
                            label=existing_item.label,  # 用已有条目的 label 作为主 key
                            old_value=existing_item.value,
                            new_value=item.value,
                            old_turn_idx=existing_item.turn_idx,
                            new_turn_idx=item.turn_idx,
                        )
                    )
                # 从 retained 中移除旧条目，加入新条目
                retained_by_class[cls] = [
                    (n, it) for n, it in retained if it is not existing_item
                ]
                retained_by_class[cls].append((norm_val, item))
                final_result.append(item)
                is_duplicate = True
                break

        if not is_duplicate:
            final_result.append(item)
            retained_by_class.setdefault(cls, []).append((norm_val, item))

    return final_result, value_updates


# --------------------------------------------------------------------------- #
# LLM 提取 Prompt（轮次感知 + Schema 引导）
# --------------------------------------------------------------------------- #


def _build_system_prompt(schema: ExtractionSchema) -> str:
    """根据 schema 动态生成 system prompt。"""
    schema_ctx = _build_schema_context(schema)
    return f"""\
你是{schema.scene_name}对话的知识提取专家。

{schema_ctx}

你的任务是从多轮对话中提取上述三类结构化知识。
对话中每轮格式为：[第N轮(说话人)] 话语内容

## 意图提取规则（重要）

意图提取必须遵循以下原则：

1. **按说话人选择意图**：
   - 标注【坐席】的意图（verify_identity / explain_* / calculate_* / handle_* / guide_* / promote_* / explain_temp_credit）必须从**坐席轮次**提取
   - 标注【用户】的意图（complain_* / express_* / confirm_* / reject_* / ask_* / dispute_* / inquire_* / express_*）必须从**用户轮次**提取
   - 不要将用户意图标注在坐席轮次，也不要将坐席意图标注在用户轮次

2. **general_inquiry 是最后兜底**：
   - general_inquiry 仅当用户轮次的内容**完全无法**归入其他任何用户意图时才使用
   - 以下情况必须使用对应的具体意图，**不得**使用 general_inquiry：
     * 用户说还款麻烦/月供高/压力大 → complain_repayment
     * 用户说利息高/利率贵 → complain_interest_rate
     * 用户说一万块应该多少利息/和某个金额比较 → express_interest_expectation
     * 用户说好/对/嗯/明白/是的 → confirm_information
     * 用户说不用/不借/不需要 → reject_offer
     * 用户质疑某笔借款记录 → dispute_loan_record
   - 如果一条用户话语表达了以上任一含义，就使用对应的具体意图

3. **意图去重**：同一意图若在对话中多次出现，只提取最有代表性的一条；不同意图均需提取

## 输出格式（严格 JSON）

{{
  "extractions": [
    {{
      "extraction_class": "slot_value",
      "label": "<槽位名>",
      "value": "<提取到的值>",
      "turn_idx": <0-based 整数，该信息来自第几轮，从0开始>,
      "provenance_text": "<该轮话语中原始出现的完整文本片段，必须是逐字子串>"
    }},
    {{
      "extraction_class": "intent",
      "label": "<意图编码>",
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

## 关键约束

- turn_idx 必须是整数，从 0 开始；第1轮对应 0，第2轮对应 1，以此类推
- provenance_text 必须是对应轮次 **话语内容** 部分的逐字子串，不包含 "[第N轮(说话人)]" 前缀，不能改写
- provenance_text 只写话语内容本身，不要加引号「」，不要加"坐席："/"用户："前缀
- 如果同一槽位/事实在对话中多次出现（如用户纠正了之前的信息），每次出现均提取，以便系统追踪值的变化
- 只提取对话中明确出现的信息，不猜测不推断
- 只输出 JSON，不要任何额外说明"""

_EXTRACTION_USER_TEMPLATE = """\
请从以下{scene_name}对话中提取结构化知识（每条须标注 turn_idx 和 provenance_text）：

{dialogue_text}

请输出 JSON："""


def _build_extraction_prompt(source_text: str, schema: Optional[ExtractionSchema] = None) -> str:
    """
    构建发送给 LLM 的完整提取 prompt。

    参数:
        source_text: 带轮次标记的对话文本
        schema:      提取 Schema；为 None 时使用 DEFAULT_SCHEMA

    返回:
        完整 prompt 字符串（system + user 拼接）
    """
    if schema is None:
        schema = DEFAULT_SCHEMA
    system = _build_system_prompt(schema)
    user = _EXTRACTION_USER_TEMPLATE.format(
        scene_name=schema.scene_name,
        dialogue_text=source_text,
    )
    return f"{system}\n\n{user}"


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
        llm_client:  可选的 SimpleLLMClient 实例；不传则自动从 .env 加载
        schema:      提取 Schema（槽位、意图、事实定义）；不传则使用内置的
                     ``DEFAULT_SCHEMA``（安逸花外呼 Schema）。
                     传入自定义 ``ExtractionSchema`` 可适配任意业务场景。

    示例（自定义 Schema）::

        from contextmind.scenarios.anyihua.knowledge_extraction import (
            AnyihuaKnowledgeExtractor, ExtractionSchema, SlotDefinition, IntentDefinition,
        )

        schema = ExtractionSchema(
            scene_name="银行贷款外呼",
            slots=[
                SlotDefinition("customer_name", "客户姓名"),
                SlotDefinition("loan_amount", "贷款金额（元）"),
            ],
            intents=[
                IntentDefinition("verify_identity", "核实身份"),
                IntentDefinition("explain_terms", "解释贷款条款"),
            ],
            fact_description="其他重要贷款业务事实",
            slot_open_ended=True,   # 允许 LLM 自由扩展槽位
        )
        extractor = AnyihuaKnowledgeExtractor(schema=schema)
    """

    def __init__(
        self,
        llm_client: Optional[SimpleLLMClient] = None,
        schema: Optional[ExtractionSchema] = None,
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
        self._schema: ExtractionSchema = schema if schema is not None else DEFAULT_SCHEMA


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
                stats={
                    "total": 0, "aligned": 0, "unaligned": 0, "alignment_rate": 0.0,
                    "turn_corrected": 0, "global_search_found": 0, "skipped_incomplete": 0,
                    "dedup_removed": 0, "updated_count": 0, "turns": 0,
                },
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
                stats={
                    "total": 0, "aligned": 0, "unaligned": 0, "alignment_rate": 0.0,
                    "turn_corrected": 0, "global_search_found": 0, "skipped_incomplete": 0,
                    "dedup_removed": 0, "updated_count": 0, "turns": len(turns),
                },
            )

        logger.info(f"[AnyihuaExtractor] LLM 返回 {len(raw_items)} 条候选提取结果")

        # Step 3: 逐条进行轮级 WordAligner 对齐
        turn_map = {idx: (sp, utt) for idx, sp, utt in turns}
        knowledge_items: List[KnowledgeItem] = []
        aligned_count = 0
        skipped_count = 0
        turn_corrected_count = 0   # LLM turn_idx 偏差被自动修正的条目数
        global_search_count = 0    # 通过全量扫描找到溯源的条目数

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

            # 主路径：轮级 WordAligner 对齐（只对该轮短文本对齐）
            char_start, char_end = _align_to_turn(prov_text, turn_text)
            turn_corrected = False
            by_global = False

            # 主路径失败时，通过临近搜索 / 全量搜索自动修正 turn_idx 偏差
            if char_start is None:
                (
                    turn_idx,
                    speaker,
                    char_start,
                    char_end,
                    turn_corrected,
                    by_global,
                ) = _find_turn_by_search(prov_text, turn_idx, turn_map)
                if char_start is not None and turn_corrected:
                    logger.info(
                        f"[AnyihuaExtractor] 修正 turn_idx → 第{turn_idx + 1}轮({speaker})"
                        f"（{'全量' if by_global else '临近'}搜索）"
                        f" [{cls}] {label}: {value[:20]}"
                    )

            if char_start is not None:
                aligned_count += 1
                if turn_corrected:
                    turn_corrected_count += 1
                if by_global:
                    global_search_count += 1
                logger.debug(
                    f"[AnyihuaExtractor] ✓ [{cls}] {label}: {value[:30]} "
                    f"← 第{turn_idx+1}轮({speaker}) 位置[{char_start}:{char_end}]"
                    + (" (修正)" if turn_corrected else "")
                )
            else:
                turn_display = f"{turn_idx + 1}" if turn_idx >= 0 else "?"
                logger.debug(
                    f"[AnyihuaExtractor] △ [{cls}] {label}: {value[:30]} "
                    f"← 第{turn_display}轮({speaker}) 溯源失败（「{prov_text[:20]}」）"
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

        # 跨轮槽位/事实去重（保留最新值，记录值变更）
        updates: List[ValueUpdate] = []
        dedup_removed = 0
        if knowledge_items:
            before_dedup = total
            knowledge_items, updates = _deduplicate_knowledge_items(knowledge_items)
            dedup_removed = before_dedup - len(knowledge_items)
            if dedup_removed:
                logger.info(
                    f"[AnyihuaExtractor] 跨轮去重: 删除 {dedup_removed} 条重复槽位/事实"
                    f"，其中值发生变更 {len(updates)} 条"
                )
            total = len(knowledge_items)

        stats = {
            "total": total,
            "aligned": aligned_count,
            "unaligned": total - aligned_count,
            "alignment_rate": round(aligned_count / total, 3) if total else 0.0,
            "turn_corrected": turn_corrected_count,
            "global_search_found": global_search_count,
            "skipped_incomplete": skipped_count,
            "dedup_removed": dedup_removed,
            "updated_count": len(updates),
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
            updates=updates,
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
                            "turn_corrected": 0,
                            "global_search_found": 0,
                            "skipped_incomplete": 0,
                            "dedup_removed": 0,
                            "updated_count": 0,
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
        prompt = _build_extraction_prompt(source_text, self._schema)
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
    schema: Optional[ExtractionSchema] = None,
) -> ExtractionResult:
    """
    从单条安逸花外呼对话中提取带轮次归属与溯源的结构化知识（便捷函数）。

    参数:
        dialogue:    原始对话条目（chat_test_100.json 单条）
        llm_client:  可选的 SimpleLLMClient 实例；若不传入则自动从 .env 加载
        schema:      提取 Schema（槽位、意图定义）；不传则使用 DEFAULT_SCHEMA

    返回:
        ExtractionResult，每条知识项的 provenance 字段含轮次归属与字符位置
    """
    extractor = AnyihuaKnowledgeExtractor(llm_client=llm_client, schema=schema)
    return extractor.extract(dialogue)
