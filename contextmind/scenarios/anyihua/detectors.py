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


def detect_data_error_full_history(session: Dict[str, Any]) -> Tuple[bool, str]:
    """
    扩展版：在完整对话历史中检测数据错误（覆盖率 14/15）。

    相比 detect_data_error，额外扫描 对话历史 中所有坐席发言，
    可检出本轮回复未引用具体金额、但历史轮次已引用过错误金额的情况。

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

    # 合并历史中所有坐席发言 + 本轮回复
    all_agent_text = " ".join(
        t for t in session["对话历史"] if t.startswith("坐席：")
    )
    all_agent_text += " " + session["坐席回复"]

    for amount_text_cn, value in extract_amounts(all_agent_text):
        if value <= 1000:
            continue
        if not any(abs(value - gt) < 300 for gt in gt_values):
            return True, (
                f"对话中引用金额 {amount_text_cn}({value:,}) 与用户信息不符"
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

    messages = [
        {
            "role": "system",
            "content": (
                "你是一个对话质量检测助手。判断坐席回复是否响应了用户的当前意图。\n"
                "只输出 JSON：{\"is_off_topic\": true/false, \"reason\": \"...\"}，"
                "不要输出其他内容。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"用户最后发言：{last_user}\n"
                f"坐席回复：{reply}\n\n"
                "坐席回复是否答非所问？"
            ),
        },
    ]

    try:
        raw = await llm_client.chat_async(messages=messages)
        parsed = json.loads(raw.strip().strip("`"))
        if parsed.get("is_off_topic"):
            return True, parsed.get("reason", "意图不对齐")
    except Exception:
        pass

    return False, ""
