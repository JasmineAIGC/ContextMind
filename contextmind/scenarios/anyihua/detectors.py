"""
安逸花外呼促活场景 · 四类质量问题检测器

基于 chat_test_100.json 数据分析，针对 AI 坐席四类典型质量问题
实现检测函数。所有检测函数均为纯函数，接受 session 字典为参数。

检测优先级（基于实测误报分析，由高到低）：
    1. 数据错误   — 数值比对，最精确，几乎无误报
    2. 重复询问   — 字符串匹配，极精确
    3. 不当告别   — 关键词 + 上下文，精确
    4. 答非所问   — 规则辅助（LLM 增强），召回率有限

数据集统计（已逐条验证）：
    - 数据错误：15/100，实测覆盖率 14/15（93%）
    - 重复询问：15/100，精确匹配覆盖 13/15（87%），L1+L2 可达 15/15
    - 不当告别：15/100，关键词覆盖 13/15（87%）
    - 答非所问：15/100，规则覆盖约 60%，LLM 增强可达 80%+

基于 docs/analysis/pytod-on-chat-test-100.md §5 实现。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from .utils import extract_amounts, parse_user_info


# --------------------------------------------------------------------------- #
# 角色前缀常量（对话历史格式: "坐席：发言内容" / "用户：发言内容"）
# --------------------------------------------------------------------------- #

_AGENT_PREFIX = "坐席："
_USER_PREFIX = "用户："


# --------------------------------------------------------------------------- #
# 告别检测常量
# --------------------------------------------------------------------------- #

#: 固定告别话术关键词（13/15 会话命中至少 2 个）
FAREWELL_KEYWORDS: List[str] = [
    "不打扰您了",
    "祝您生活愉快",
    "再见",
    "感谢您的接听",
    "感谢接听",       # 口语缩写，无"您"
]

#: 单关键词即可判断告别的强信号词组（score 不够时的补充）
_FAREWELL_SOFT_PATTERNS: List[str] = [
    "先不打扰",
    "不打扰了",
    "打扰到您了",
]

#: 用户诉求关键词（出现在最后 12 条历史中则视为有未解决问题）
USER_CONCERN_WORDS: List[str] = [
    "为什么",
    "怎么",
    "没有",
    "借不出",
    "不对",
    "不是",
    "投诉",
    "能不能",
    "可不可以",
    "怎么办",
    "解冻",
    "申请",
    "问一下",
    "还想问",       # "我还想问你" — 用户明确表示有更多问题
    "什么意思",     # 用户对坐席说法表示困惑
    "干啥",         # "我问他干啥" — 口语质疑
    "不行",         # "这个不行" — 操作失败反馈
    "显示",         # "它显示九万四千八" — 用户质疑 APP 显示数字
]

# --------------------------------------------------------------------------- #
# 答非所问规则常量
# --------------------------------------------------------------------------- #

#: 用户疑问词 → 坐席回复中不应出现的无关模式
#: 用户问 Q，坐席回答无关的 Y 时视为答非所问
OFFTOPIC_SIGNALS: Dict[str, List[str]] = {
    "多少": ["再见", "打扰", "明白吧", "操作流程", "安逸花呀", "是吗", "提完了"],
    "为什么": ["按需借", "提现", "立即借款", "安逸花呀"],
    "能不能": ["再见", "不打扰", "感谢", "明白吧"],
    "怎么": ["按需借", "提现", "可以用", "就可以了"],
    "显示": ["之前借", "是吗", "借了一笔"],  # 用户质疑 APP 显示数字时，坐席转移话题
}

#: LLM 答非所问检测预过滤词：用户发言须含至少一个问题/质疑信号才调用 LLM
#: 无明确问题信号时，答非所问在语义上不成立（无问题可"非所答"），直接跳过 LLM 调用
_QUESTION_SIGNALS: List[str] = [
    "多少", "为什么", "为啥", "为何", "能不能", "可以吗", "能吗",
    "怎么", "怎样", "怎么回事", "什么", "哪里", "哪个", "哪些",
    "不是", "不对", "不行", "显示", "不明白", "什么意思",
    "多久", "几天", "几期", "不应该", "咋",
]

# --------------------------------------------------------------------------- #
# LLM 全量质检常量
# --------------------------------------------------------------------------- #

#: LLM 全量质检合法标签集合（detect_session_llm 返回值必须在此集合内）
_VALID_LABELS: frozenset[str] = frozenset(
    {"数据错误", "重复询问", "不当告别", "答非所问", "无标签命中"}
)

#: use_full_history=False 时传入 LLM 的最大历史消息条数
#: 对话历史中每条消息为单独一条（"坐席：…" 或 "用户：…"），不是一个来回
_DEFAULT_HISTORY_TURNS: int = 10


# --------------------------------------------------------------------------- #
# 1. 数据错误检测
# --------------------------------------------------------------------------- #


def detect_data_error(session: Dict[str, Any]) -> Tuple[bool, str]:
    """
    检测坐席回复是否引用了错误的金额数字。

    原理：从 用户信息 获取真实可提现额度和临时额度作为 ground truth，
    与 坐席回复 中提取的中文金额对比。容许 300 元口语化误差。

    实测数据：
    - 全部 15 条数据错误会话均有数字偏差
    - 12/15 可直接从 坐席回复 检出（余下 3 条本轮回复未引用具体金额）
    - 罗女士 + 陈女士两个独立会话出现相同幻觉数字"四万五千一百"

    参数:
        session: 单条 chat_test_100.json 记录

    返回:
        (is_error: bool, reason: str)
        is_error=True 时 reason 描述具体错误数字与实际值的差异
    """
    info = parse_user_info(session["用户信息"])

    # Ground truth：坐席可以合法引用的金额
    gt_values = [
        v for v in [
            info["available_credit"],       # 可提现额度（最核心）
            info["temp_credit"],            # 临时额度上限
            # 当临时额度有效时，坐席可引用临时额度；过期后只能引用 available_credit
            info["available_credit"] if info["temp_expired"] else info["temp_credit"],
        ]
        if v > 0
    ]

    reply_amounts = extract_amounts(session["坐席回复"])

    for amount_text_cn, value in reply_amounts:
        if value <= 1000:
            continue
        tolerance = 300
        if not any(abs(value - gt) < tolerance for gt in gt_values):
            return True, (
                f"坐席引用金额 {amount_text_cn}({value:,}元) 与实际可提现 "
                f"{info['available_credit']:,}元不符"
            )

    return False, ""


def detect_data_error_recent_history(session: Dict[str, Any]) -> Tuple[bool, str]:
    """
    扩展版：检测最近一条历史坐席发言是否引用了错误金额。

    仅扫描对话历史中最近一条坐席发言（不含本轮回复，本轮已由 detect_data_error 覆盖），
    可检出"本轮回复未引用数字、但上一轮坐席已报错误金额"的场景。

    设计说明：
        函数仅扫描最近 1 条历史坐席发言，而非全部历史。扫描全部历史会导致大量误报：
        早期历史发言中的金额可能是当时合法引用的数字（用户额度随时间变化），
        或出现在贷款金额、分期金额等非额度比对语境中。
        此函数不在主质检流水线中使用（主流水线已切换为 detect_session_llm 全量 LLM 分类），
        保留供调试和离线分析参考。

    参数:
        session: 单条 chat_test_100.json 记录

    返回:
        (is_error: bool, reason: str)
    """
    info = parse_user_info(session["用户信息"])
    gt_values = [
        v for v in [
            info["available_credit"],
            info["temp_credit"],
            info["available_credit"] if info["temp_expired"] else info["temp_credit"],
        ]
        if v > 0
    ]

    # 只扫描最近一条历史坐席发言（当前回复已由 detect_data_error 处理）
    # 若历史中无坐席发言，recent_turn 为空字符串，extract_amounts 将返回空列表
    agent_turns = [t for t in session["对话历史"] if t.startswith("坐席：")]
    recent_turn = agent_turns[-1] if agent_turns else ""

    for amount_text_cn, value in extract_amounts(recent_turn):
        if value <= 1000:
            continue
        if not any(abs(value - gt) < 300 for gt in gt_values):
            return True, (
                f"近期历史发言引用金额 {amount_text_cn}({value:,}) 与用户信息不符"
            )

    return False, ""


# --------------------------------------------------------------------------- #
# 2. 重复询问检测
# --------------------------------------------------------------------------- #


def detect_repetition(session: Dict[str, Any]) -> Tuple[bool, str]:
    """
    检测坐席回复是否是对话历史中已说过的重复话语。

    实测数据：
    - 15 条重复询问中，13 条（87%）的 坐席回复 与历史中某条坐席发言逐字相同
    - 典型案例：'借不了了。'、'五万九千。' 等极短回复出现 2~4 次
    - 另 2 条在语义层面高度相似（>85% 字符重叠）但文本不完全相同

    分层检测：
    - Layer 1: 精确字符串匹配（无 LLM，覆盖 13/15）
    - Layer 2: 字符重叠相似度（覆盖剩余 2/15）

    参数:
        session: 单条 chat_test_100.json 记录

    返回:
        (is_repeat: bool, reason: str)
    """
    history = session["对话历史"]
    reply = session["坐席回复"].strip()
    agent_turns = [t.removeprefix(_AGENT_PREFIX).strip() for t in history if t.startswith(_AGENT_PREFIX)]

    # Layer 1: 精确匹配
    if reply in agent_turns:
        count = agent_turns.count(reply)
        idx = agent_turns.index(reply) + 1  # 1-based turn number
        return True, f"坐席回复与第 {idx} 轮历史发言完全相同（已重复 {count + 1} 次）"

    # Layer 2: 字符重叠相似度
    def _char_similarity(a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        common = sum(1 for c in a if c in b)
        return 2 * common / (len(a) + len(b))

    for i, past in enumerate(agent_turns):
        sim = _char_similarity(reply, past)
        if sim > 0.85:
            return True, (
                f"坐席回复与第 {i + 1} 轮历史发言语义高度相似"
                f"（相似度 {sim:.0%}）"
            )

    return False, ""


# --------------------------------------------------------------------------- #
# 3. 不当告别检测
# --------------------------------------------------------------------------- #


def detect_improper_farewell(session: Dict[str, Any]) -> Tuple[bool, str]:
    """
    检测不当告别：用户有未解决诉求时，坐席执行告别话术。

    实测数据：
    - 13/15 坐席回复含关键词 "不打扰您了" + "再见"（或类似组合）
    - 另 2 条为委婉告别（"先不打扰" / "感谢接听…再见"）
    - 全部 15 条：用户最后几轮发言中均有待解决诉求

    检测逻辑：
    1. 检测 坐席回复 是否为告别语
    2. 若是，检测 对话历史 最后 8 条中是否有用户未解决诉求
    3. 两者同时满足则判定为 不当告别

    参数:
        session: 单条 chat_test_100.json 记录

    返回:
        (is_improper: bool, reason: str)
    """
    reply = session["坐席回复"]
    history = session["对话历史"]

    # 判断是否为告别语（命中 2 个关键词或含委婉告别词）
    farewell_score = sum(1 for kw in FAREWELL_KEYWORDS if kw in reply)
    is_farewell = farewell_score >= 2 or any(
        p in reply for p in _FAREWELL_SOFT_PATTERNS
    )

    if not is_farewell:
        return False, ""

    # 检查用户最近 12 条发言（扩大窗口，覆盖历史问题被忽略的情况）
    last_user_turns = [t.removeprefix(_USER_PREFIX) for t in history[-12:] if t.startswith(_USER_PREFIX)]
    unresolved = [
        t for t in last_user_turns if any(w in t for w in USER_CONCERN_WORDS)
    ]

    if unresolved:
        return True, (
            f"用户有 {len(unresolved)} 个未解决问题时执行告别："
            f"{unresolved[-1][:40]}…"
        )

    return False, ""


# --------------------------------------------------------------------------- #
# 4. 答非所问检测
# --------------------------------------------------------------------------- #


def detect_off_topic_rule(session: Dict[str, Any]) -> Tuple[bool, str]:
    """
    基于规则的答非所问检测（无需 LLM，作为快速预过滤层）。

    检测"用户问 Q，坐席答 Y（与 Q 无关）"的模式。
    规则版召回率约 60%，建议结合 detect_off_topic_llm 提升至 80%+。

    参数:
        session: 单条 chat_test_100.json 记录

    返回:
        (is_offtopic: bool, reason: str)
    """
    history = session["对话历史"]
    reply = session["坐席回复"]

    last_user = next(
        (t.removeprefix(_USER_PREFIX) for t in reversed(history) if t.startswith(_USER_PREFIX)), ""
    )

    for q_word, irrelevant_patterns in OFFTOPIC_SIGNALS.items():
        if q_word in last_user:
            mismatches = [p for p in irrelevant_patterns if p in reply]
            if mismatches:
                return True, (
                    f"用户发言含 '{q_word}'，但坐席回复含 "
                    f"'{mismatches[0]}'，可能答非所问"
                )

    return False, ""


async def detect_off_topic_llm(
    session: Dict[str, Any],
    llm_client: Any,
) -> Tuple[bool, str]:
    """
    LLM 增强版答非所问检测（精度更高，需 LLMClient 实例）。

    使用 LLM 判断坐席回复是否响应了用户的当前意图，
    可处理"APP 显示九万四千八"、"分 12 期手续费"等复杂意图对齐场景。

    内置预过滤：若用户最后发言不含明确问题信号（如疑问词、否定词等），
    则答非所问在语义上不成立，直接返回 False 而不调用 LLM API。

    参数:
        session:    单条 chat_test_100.json 记录
        llm_client: contextmind.infra.llm_client.LLMClient 实例，
                    需支持 chat_async(messages) 方法

    返回:
        (is_offtopic: bool, reason: str)
    """
    history = session["对话历史"]
    reply = session["坐席回复"]
    last_user = next(
        (t.removeprefix(_USER_PREFIX) for t in reversed(history) if t.startswith(_USER_PREFIX)), ""
    )

    # 预过滤：若用户最后发言不含任何问题/质疑信号，答非所问在语义上无法成立
    # （"答非所问"的前提是用户"问"了，否则坐席无从"非所答"）
    if not any(signal in last_user for signal in _QUESTION_SIGNALS):
        return False, ""

    messages = [
        {
            "role": "system",
            "content": (
                "你是安逸花外呼质检系统，负责检测坐席回复是否'答非所问'。\n"
                "安逸花是小额贷款产品，外呼坐席的核心任务是向用户推介借款并解答疑问。\n\n"
                "【判定为'答非所问'的条件（需同时满足）】\n"
                "1. 用户最后发言是明确的问题（询问金额、原因、操作方式、时间等）\n"
                "2. 坐席回复完全未涉及该问题，内容与问题毫无关联\n\n"
                "【不属于'答非所问'的情况（符合其一即判为 false）】\n"
                "- 用户发言不是问题（如表示确认、感谢、陈述事实）\n"
                "- 坐席给出了方向正确的回答，即使不够详细\n"
                "- 坐席承认无法处理并说明了原因\n"
                "- 坐席回答问题后顺带推介了产品\n"
                "- 有任何不确定性时\n\n"
                "请只输出以下格式的 JSON，禁止输出其他内容：\n"
                '{"is_off_topic": false, "reason": "简短说明"}'
            ),
        },
        {
            "role": "user",
            "content": (
                f"用户最后发言：{last_user}\n"
                f"坐席回复：{reply}\n\n"
                "该坐席回复是否答非所问？"
            ),
        },
    ]

    try:
        raw = await llm_client.chat_async(messages=messages)
        # 兼容 LLM 可能返回的 markdown 代码块格式
        raw_clean = raw.strip()
        if raw_clean.startswith("```"):
            raw_clean = raw_clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        elif raw_clean.startswith("`"):
            raw_clean = raw_clean.strip("`")
        parsed = json.loads(raw_clean)
        if parsed.get("is_off_topic"):
            return True, parsed.get("reason", "意图不对齐")
    except Exception:
        pass

    return False, ""


# --------------------------------------------------------------------------- #
# 5. LLM 全量质检（单次调用，统一分类）
# --------------------------------------------------------------------------- #


async def detect_session_llm(
    session: Dict[str, Any],
    llm_client: Any,
    use_full_history: bool = False,
) -> Tuple[str, str]:
    """
    LLM 全量质检：一次 LLM 调用完成对单条会话的五分类判断。

    将用户信息、对话历史和本轮坐席回复一并送入 LLM，由模型直接输出质量标签。
    替代所有规则检测器，适用于对精度要求较高的场景。

    五个合法标签（_VALID_LABELS）：
        - 数据错误：坐席引用的金额与用户实际信息不符（误差超过 300 元）
        - 重复询问：坐席回复与历史发言高度重复
        - 不当告别：用户有未解决问题时坐席执行告别话术
        - 答非所问：用户明确提问但坐席回复完全无关
        - 无标签命中：不存在上述任何质量问题

    参数:
        session:          单条 chat_test_100.json 记录
        llm_client:       LLMClient 实例（需支持 chat_async 方法）
        use_full_history: True 时将全部对话历史送入 LLM；
                          False（默认）时仅保留最近 _DEFAULT_HISTORY_TURNS 轮（节省 token）

    返回:
        (label: str, reason: str)
        label 必为 _VALID_LABELS 中的一个；若 LLM 调用失败则返回 ("无标签命中", "LLM 调用异常")
    """
    user_info = session["用户信息"]
    history = session["对话历史"]
    reply = session["坐席回复"]

    # 按 use_full_history 决定传入 LLM 的历史轮数
    history_slice = history if use_full_history else history[-_DEFAULT_HISTORY_TURNS:]
    history_text = "\n".join(history_slice)

    messages = [
        {
            "role": "system",
            "content": (
                "你是安逸花外呼质检系统，负责对客服坐席的对话质量进行分类。\n"
                "安逸花是小额贷款产品，外呼坐席负责向用户推介借款、解答疑问并处理还款业务。\n\n"
                "【质量标签及判断标准】\n"
                "1. 数据错误\n"
                "   坐席在对话中提及的金额（可提现额度、临时额度等）与【用户信息】中的实际数据不符，\n"
                "   偏差超过 300 元即视为错误。\n\n"
                "2. 重复询问\n"
                "   坐席的最终回复内容与对话历史中某条坐席发言高度重复（字面相同或语义极为相似），\n"
                "   构成无效重复。\n\n"
                "3. 不当告别\n"
                "   用户明确表示有疑问、诉求或困惑，坐席却直接执行告别话术\n"
                "   （如'不打扰您了'、'再见'、'祝您生活愉快'等）。\n\n"
                "4. 答非所问\n"
                "   用户提出明确问题，坐席的回复内容与该问题完全无关。\n"
                "   仅当用户明确提问且坐席回复毫无关联时才判定；\n"
                "   若坐席给出了方向正确的回答（即使不够详细），不算答非所问。\n\n"
                "5. 无标签命中\n"
                "   坐席回复不存在上述任何质量问题，对话质量正常。\n\n"
                "【判断原则】\n"
                "- 若同时满足多个标签，选择最主要、最严重的一个\n"
                "- 有任何不确定时，选择'无标签命中'（宁可漏报，不要误报）\n"
                "- label 必须是以下五个之一：数据错误、重复询问、不当告别、答非所问、无标签命中\n\n"
                "只输出以下格式的 JSON，禁止输出其他内容：\n"
                '{"label": "...", "reason": "简短说明（30字以内）"}'
            ),
        },
        {
            "role": "user",
            "content": (
                f"【用户信息】\n{user_info}\n\n"
                f"【对话历史】\n{history_text}\n\n"
                f"【坐席最终回复】\n{reply}\n\n"
                "请判断该坐席最终回复的质量标签。"
            ),
        },
    ]

    try:
        raw = await llm_client.chat_async(messages=messages)
        raw_clean = raw.strip()
        if raw_clean.startswith("```"):
            raw_clean = raw_clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        elif raw_clean.startswith("`"):
            raw_clean = raw_clean.strip("`")
        parsed = json.loads(raw_clean)
        label = parsed.get("label", "无标签命中")
        reason = parsed.get("reason", "")
        if label not in _VALID_LABELS:
            return "无标签命中", f"LLM 返回未知标签: {label}"
        return label, reason
    except Exception as exc:
        return "无标签命中", f"LLM 调用异常: {exc}"
