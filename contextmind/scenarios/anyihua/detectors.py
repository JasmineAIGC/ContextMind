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
import re
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

#: 标签优先顺序（与系统 prompt 中"检查顺序"一致）
#: 当 JSON 解析失败时按此顺序从 LLM 原始输出中提取标签
_LABEL_PRIORITY: List[str] = ["数据错误", "重复询问", "不当告别", "答非所问", "无标签命中"]

#: use_full_history=False 时传入 LLM 的最大历史消息条数
#: 对话历史中每条消息为单独一条（"坐席：…" 或 "用户：…"），不是一个来回
#: 设为 20 以覆盖更多重复询问场景（部分会话首次重复出现在第 20+ 条之前）
_DEFAULT_HISTORY_TURNS: int = 20

#: 在规则预分析摘要中显示的历史发言最大字符数
_DISPLAY_TURN_MAX_LEN: int = 30


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
    LLM 全量质检：单次调用，按优先级顺序依次检查五个质量标签。

    设计原则：
    - 【用户系统额度】从 user_info 预解析，作为"数据错误"判断的唯一客观参考
    - 【对话历史】提供对话背景，坐席发言可用于重复询问/不当告别/答非所问比对
    - 【坐席最终回复】是被评估对象
    - 规则预分析结果作为提示注入 prompt，提升 LLM 对数值偏差和重复模式的感知
    - 使用思维链提示词（CoT）提升推理质量，从回复中提取最后出现的 JSON

    五个合法标签（_VALID_LABELS）：
        - 数据错误：坐席最终回复的明确金额与系统记录额度偏差 > 300 元
        - 重复询问：坐席最终回复与历史某条坐席发言几乎逐字相同
        - 不当告别：坐席执行告别话术时用户最后消息中有明确未回应的问题/投诉
        - 答非所问：用户最后消息有明确具体问题，坐席回复与该问题完全无关
        - 无标签命中：不存在上述任何质量问题

    参数:
        session:          单条 chat_test_100.json 记录
        llm_client:       LLMClient 实例（需支持 chat_async(messages, temperature) 方法）
        use_full_history: True 时将全部对话历史送入 LLM；
                          False（默认）时仅保留最近 _DEFAULT_HISTORY_TURNS 条（节省 token）

    返回:
        (label: str, reason: str)
        label 必为 _VALID_LABELS 中的一个；若 LLM 调用失败则返回 ("无标签命中", "LLM 调用异常")
    """
    user_info_str = session["用户信息"]
    history = session["对话历史"]
    reply = session["坐席回复"]

    # 预解析用户系统额度作为"数据错误"判断的客观参考
    # 用户在对话中自述的金额不能作为参考（用户可能误记/质疑正确数字）
    info = parse_user_info(user_info_str)
    credit_yuan = info["available_credit"]
    credit_display = f"{credit_yuan:,}元" if credit_yuan > 0 else "未提供"

    # --------------------------------------------------------------------------- #
    # 规则预分析：为 LLM 提供具体数值证据，提升数据错误和重复询问的召回率
    # --------------------------------------------------------------------------- #

    # 1. 数据错误预分析：提取坐席回复及历史发言中的金额，与系统额度比对
    # 合法参考值：available_credit 和 temp_credit（未过期时）
    _gt_values = [
        v for v in [credit_yuan, info["temp_credit"]]
        if v > 0
    ]
    data_error_hints: List[str] = []
    if _gt_values:
        def _is_amount_valid(value: int) -> bool:
            """检查 value 是否与任意合法额度相差 ≤ 300 元"""
            return any(abs(value - gt) <= 300 for gt in _gt_values)

        # 检查坐席最终回复中的金额
        for amount_text, value in extract_amounts(reply):
            if value > 1000 and not _is_amount_valid(value):
                diff = abs(value - credit_yuan)
                data_error_hints.append(
                    f"坐席最终回复提到「{amount_text}」({value:,}元)，"
                    f"系统额度{credit_yuan:,}元，偏差{diff:,}元 ⚠️"
                )
        # 检查对话历史中坐席发言的金额（覆盖"回复本轮未提数字但历史已报错"的场景）
        seen_history_errors: set = set()
        for turn in history:
            if turn.startswith(_AGENT_PREFIX):
                turn_text = turn.removeprefix(_AGENT_PREFIX)
                for amount_text, value in extract_amounts(turn_text):
                    if (
                        value > 1000
                        and not _is_amount_valid(value)
                        and amount_text not in seen_history_errors
                    ):
                        seen_history_errors.add(amount_text)
                        diff = abs(value - credit_yuan)
                        data_error_hints.append(
                            f"历史坐席发言提到「{amount_text}」({value:,}元)，"
                            f"系统额度{credit_yuan:,}元，偏差{diff:,}元 ⚠️"
                        )

    # 2. 重复询问预分析：计算坐席最终回复与历史坐席发言的文本相似度
    agent_turns_history = [
        t.removeprefix(_AGENT_PREFIX).strip()
        for t in history
        if t.startswith(_AGENT_PREFIX)
    ]
    reply_stripped = reply.strip()
    is_exact_repeat = reply_stripped in agent_turns_history
    max_sim = 0.0
    max_sim_turn = ""
    for past in agent_turns_history:
        if not past:
            continue
        past_chars = set(past)  # O(1) lookup vs O(n) for string membership
        common = sum(1 for c in reply_stripped if c in past_chars)
        denom = len(reply_stripped) + len(past)
        sim = 2 * common / denom if denom > 0 else 0.0
        if sim > max_sim:
            max_sim = sim
            max_sim_turn = past

    repetition_hint = ""
    if is_exact_repeat:
        repetition_hint = f"⚠️ 坐席最终回复与历史某条坐席发言完全一致（精确匹配）"
    elif max_sim >= 0.80:
        repetition_hint = (
            f"⚠️ 坐席最终回复与历史发言「{max_sim_turn[:_DISPLAY_TURN_MAX_LEN]}」"
            f"相似度 {max_sim:.0%}（≥80%）"
        )

    # --------------------------------------------------------------------------- #
    # 构建 prompt
    # --------------------------------------------------------------------------- #

    # 按 use_full_history 决定传入 LLM 的历史条数
    history_slice = history if use_full_history else history[-_DEFAULT_HISTORY_TURNS:]
    history_text = "\n".join(history_slice)

    system_prompt = (
        "你是安逸花外呼对话质检专家。安逸花是小额贷款产品，坐席职责是推介借款并解答问题。\n\n"
        "请对【坐席最终回复】从以下五个标签中选择唯一最匹配的一个。\n\n"
        "【重要】用户消息中提到的金额（用户自述的额度、用户质疑的数字）不可作为系统真实额度，"
        "只有【用户系统额度】是判断数据错误的唯一客观标准。\n\n"
        "【判断标准（按①→⑤顺序逐一核查，第一个明确成立的即为结果）】\n\n"
        "① 数据错误\n"
        "   成立条件（必须同时满足）：\n"
        "   a. 坐席（历史发言或最终回复）中出现了明确的可提现额度数字\n"
        "   b. 该数字与【用户系统额度】相差超过300元（|坐席金额 - 系统额度| > 300）\n"
        "   如果【规则预分析-数据错误】中显示了金额偏差警告⚠️，请仔细核查该金额的上下文：\n"
        "   只有当坐席是在向用户陈述可提现额度（'您的额度是X元''您还有X元可提现'等）时，\n"
        "   且该金额与系统额度偏差>300元，才算数据错误。\n"
        "   若该金额是建议提现数额、还款金额、举例说明等，则不算数据错误。\n"
        "   以下情况不算数据错误，直接跳②：\n"
        "   ✗ 坐席回复中没有提及任何具体额度金额（只谈操作步骤/无法提现原因/产品简介等）\n"
        "   ✗ 提到的金额是还款金额、手续费、利息、分期月还款等（不是可提现额度）\n"
        "   ✗ 【用户系统额度】为'未提供'时\n"
        "   注意：用户在对话中自述的金额（如'我APP显示三万'）不能用于判断坐席对错\n\n"
        "② 重复询问\n"
        "   成立条件（必须同时满足）：\n"
        "   a. 坐席最终回复的核心话术，与对话历史中某条坐席发言几乎逐字相同或字符重叠超过80%\n"
        "   b. 该话术在历史中确实已出现过（是重复，不是第一次说）\n"
        "   如果【规则预分析-重复询问】中显示了高相似度或精确匹配⚠️，请核查该话术在历史中\n"
        "   是否确实已出现过，且本次是重复而非合理的话术变体。\n"
        "   以下情况不算重复询问：\n"
        "   ✗ 两条发言话题相同但措辞明显不同\n"
        "   ✗ 核实用户姓名或身份的固定开场白（'请问您是XXX先生/女士吗'）\n\n"
        "③ 不当告别\n"
        "   成立条件（必须同时满足）：\n"
        "   a. 坐席最终回复包含明确告别话术（含'再见''不打扰您了''感谢接听''祝您生活愉快'等）\n"
        "   b. 用户最近几条消息中，有一个坐席本轮回复中完全未触及的明确问题或投诉\n"
        "   以下情况说明用户无未解决诉求（不当告别不成立）：\n"
        "   ✗ 用户明确表示不需要/拒绝（'不需要''不借''不用了''没事'）\n"
        "   ✗ 用户表示需要考虑或等待（'我想想''等我想好了''等我跟家人商量'）\n"
        "   ✗ 用户同意去操作或去查看（'好的我去试试''我去APP看看''那行我去弄'）\n"
        "   ✗ 用户只是简短应答（'嗯''哦''好''知道了''行''明白了'）\n"
        "   注意：仅当用户最近消息中有具体的、未被本次回复解答的问题时，才判为不当告别\n\n"
        "④ 答非所问\n"
        "   成立条件（必须同时满足，且门槛较高）：\n"
        "   a. 用户最后一条消息包含非常明确的具体问题（问号或明显询问语气）\n"
        "   b. 坐席最终回复与用户的具体问题属于完全不同的话题，毫无关联\n"
        "   以下情况一律不算答非所问：\n"
        "   ✗ 坐席回答了相关话题，即使不够精确或未完整回答（有涉及就不算）\n"
        "   ✗ 用户问贷款/额度/提现/账户/利率/还款相关，坐席也回复贷款/额度/提现/账户相关\n"
        "   ✗ 坐席在推介产品时未专门解答用户某个细节问题\n"
        "   ✗ 用户表达不满/抱怨/质疑，坐席给出了贷款相关的任何解释\n"
        "   ✗ 坐席承诺查询或核实（'为您查询''我帮您核实'等），算作有效响应\n\n"
        "⑤ 无标签命中\n"
        "   以上①②③④均不明确成立时，选此标签。\n"
        "   正常推介、用户接受/拒绝/同意考虑、正常问答（即使不够精确）均属于无标签命中。\n\n"
        "【输出要求】\n"
        "请先逐条核查①到④，每项写出核查结论（成立/不成立及简要理由）。\n"
        "最后一行必须是且仅是以下格式的JSON（不要加代码块标记）：\n"
        '{"label": "标签名", "reason": "理由（15字以内）"}'
    )

    # 构建规则预分析摘要（注入 user message）
    preanalysis_sections: List[str] = []
    if data_error_hints:
        preanalysis_sections.append(
            "【规则预分析-数据错误】\n" + "\n".join(f"  · {h}" for h in data_error_hints)
        )
    else:
        preanalysis_sections.append("【规则预分析-数据错误】未检测到明显金额偏差")

    if repetition_hint:
        preanalysis_sections.append(f"【规则预分析-重复询问】{repetition_hint}")
    else:
        preanalysis_sections.append(
            f"【规则预分析-重复询问】最高历史相似度 {max_sim:.0%}（<80%，未触发）"
        )

    preanalysis_text = "\n".join(preanalysis_sections)

    user_message = (
        f"【用户系统额度（仅用于①数据错误的判断）】{credit_display}\n\n"
        f"{preanalysis_text}\n\n"
        f"【对话历史（共{len(history)}条，显示最近{len(history_slice)}条）】\n"
        f"{history_text}\n\n"
        f"【坐席最终回复（待评估）】\n"
        f"{reply}\n\n"
        "请逐条核查①→④，最后一行输出JSON。"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    raw = ""
    for attempt in range(3):
        try:
            raw = await llm_client.chat_async(messages=messages, temperature=0.0)
            raw_clean = raw.strip()
            # 去除 markdown 代码块
            if raw_clean.startswith("```"):
                raw_clean = raw_clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            elif raw_clean.startswith("`"):
                raw_clean = raw_clean.strip("`")
            # 去除可能残留的 <think> 标签
            raw_clean = re.sub(r"<think>.*?</think>", "", raw_clean, flags=re.DOTALL).strip()

            # 支持思维链输出：从响应末尾向前扫描，提取最后一个包含 label 字段的 JSON 对象。
            # 目标 JSON 为平层结构 {"label": "...", "reason": "..."}，不含嵌套，
            # 正则 r'\{[^{}]+\}' 可安全匹配（不支持嵌套 JSON，但此处不需要）。
            parsed = None
            for obj_str in reversed(re.findall(r'\{[^{}]+\}', raw_clean)):
                try:
                    obj = json.loads(obj_str)
                    if "label" in obj:
                        parsed = obj
                        break
                except json.JSONDecodeError:
                    continue
            # 若正则未找到，尝试将整体作为 JSON 解析（纯 JSON 响应的向后兼容）
            if parsed is None:
                parsed = json.loads(raw_clean)

            label = parsed.get("label", "无标签命中")
            reason = parsed.get("reason", "")
            if label not in _VALID_LABELS:
                for candidate in _LABEL_PRIORITY:
                    if candidate in raw:
                        return candidate, reason or "从输出提取标签"
                return "无标签命中", f"LLM 返回未知标签: {label}"
            return label, reason
        except json.JSONDecodeError:
            # JSON 解析失败：继续重试，让 LLM 再次生成
            continue
        except Exception as exc:
            return "无标签命中", f"LLM 调用异常: {exc}"

    # 全部重试后仍无法解析 JSON：按优先级从最后一次原始输出中提取标签
    for candidate in _LABEL_PRIORITY:
        if candidate in raw:
            return candidate, "从原始输出提取标签"
    return "无标签命中", "多次尝试后 JSON 解析仍失败"
