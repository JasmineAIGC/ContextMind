"""
安逸花外呼 · 任务一（QC）· ExecutionEngine 构建

将 4 个事实数据提取函数注册为 PyTOD ExecutionEngine 的可调用 API，
供动作解析器（LLM）获取客观事实数据，用于质量标签判断。

设计原则（PyTOD 哲学）：
    执行引擎 API 只返回"客观事实"，不做主观的标签预测。
    所有标签判断由 LLM（动作解析器）完成，规则门限在 predictor.py 中维护。
    这样做的好处：
      · 引擎接口稳定、可测试，输出无歧义
      · LLM 拥有完整语义推理空间，不受规则误判干扰
      · 规则阈值可在 predictor.py 独立调整，无需修改引擎

注册的 4 个 API（对应 schema.py 中的 4 个检测意图）：
    get_credit_data()        — 额度事实（数据错误检测用）
    get_repetition_data()    — 重复度量（重复询问检测用）
    get_farewell_data()      — 告别 & 未解决诉求（不当告别检测用）
    get_topic_data()         — 话题相关性（答非所问检测用）

每个 API 返回纯事实结构（无 label / detected / confidence 字段）：
    get_credit_data() →
        {system_credit, temp_credit, reply_amounts, withdrawal_amounts,
         discrepant_amounts, max_discrepancy, hints}
    get_repetition_data() →
        {exact_repeat, repeat_count, max_similarity, most_similar_turn, hint}
    get_farewell_data() →
        {has_farewell, unresolved_issues, unresolved_count, hint}
    get_topic_data() →
        {last_user_message, user_asks_amount, topic_mismatch_hint}
"""

from __future__ import annotations

import re
from typing import Any, Dict

from contextmind.modes.pytod import ExecutionEngine

from ..utils import (
    AGENT_PREFIX as _AGENT_PREFIX,
    FAREWELL_KEYWORDS,
    FAREWELL_SOFT_PATTERNS,
    OFFTOPIC_SIGNALS,
    USER_CONCERN_WORDS,
    USER_PREFIX as _USER_PREFIX,
    cn2int,
    extract_amounts,
    parse_user_info,
)

# 额度偏差阈值（元）：超出此值的金额才计入 discrepant_amounts 列表
# 注：此阈值用于事实提取（哪些金额应被记录），而非标签判断；
#     标签判断逻辑在 predictor.py 中根据 discrepant_amounts 是否为空来决定
_AMOUNT_TOLERANCE = 300
# 重复询问模糊相似度提示阈值：超出此值才生成 hint 文字（仅供 LLM 参考）
# 注：此阈值用于 hint 文字生成，而非标签预测；标签判断依赖 exact_repeat 字段
_REP_SIM_THRESHOLD = 0.80
# 不当告别检测的用户历史窗口大小
_FAREWELL_HISTORY_WINDOW = 12
# hint 文本截断长度
_HINT_TRUNC = 30
# 奖励/促销额度的上下文模式：这类金额不是用户当前可提现额度，不作偏差检测
# 匹配前缀引导词 + 中文金额 + 促销额度后缀（如"固定额度""活动额度""奖励额度"等）
_BONUS_CREDIT_RE = re.compile(
    r"(?:最高|额外|奖励|活动|另外|再给您|另给您|承诺)[^，。！？]*?"
    r"([零一二三四五六七八九十百千万亿两]+)"
    r"(?:元|块钱)(?:的)?(?:固定额度|额度奖励|活动额度|专属额度|补充额度|奖励额度)"
)
# 坐席引导提现/借款的上下文模式（金额在前，动作词在后，无显式货币单位后缀）
# 覆盖多种常见的外呼坐席引导话术表达方式（含全量/按需/一次性等变体）
_WITHDRAWAL_RE = re.compile(
    r"([零一二三四五六七八九十百千万亿两]+)"
    r"(?:给它按需|暂时提现|按需全部|全部提现|全部提出|按需提现|按需借出"
    r"|一次性提出|全额提出|先提出|都可以提|一并提出)"
)
# 额度前缀模式：坐席提及用户账户额度时金额跟在"额度"之后但无"元"后缀
# 排除"最高额度"等通用营销描述（负向回溯 (?<!最高)），覆盖如"额度五万两千五百嘛"
_CREDIT_LEAD_RE = re.compile(
    r"(?<!最高)额度[为是到]?([零一二三四五六七八九十百千万亿两]+)"
)
# 额度后缀模式：金额出现在"的额度"前，无"元"前缀，覆盖如"三万六千九百的额度"
_CREDIT_SUFFIX_RE = re.compile(
    r"([零一二三四五六七八九十百千万亿两]+)(?:元)?的额度"
)
# 答非所问检测：用于判断用户是否在询问具体金额的关键词
_AMOUNT_QUESTION_WORDS: tuple = ("多少", "几钱", "多少钱", "多少啊", "多少元")
# 答非所问检测：坐席进行品牌/身份自我介绍的信号（而非回答用户问题）
_AGENT_INTRO_RE = re.compile(r"(?:我是|我这边是|我这里是|我说).{0,6}(?:安逸花|马上消费)")
# 答非所问检测：坐席将用户问题反问回去的信号（未给出实质答案）
_AGENT_ECHO_RE = re.compile(r"您(?:是说|这边|这里)?[^，。]{0,15}(?:吗[？?]|是吗[？?])")


def build_qc_engine(session: Dict[str, Any]) -> ExecutionEngine:
    """
    为安逸花 QC 任务构建 ExecutionEngine，注册 4 个事实数据提取 API。

    每次针对一条会话调用，返回绑定该会话数据的引擎实例。
    引擎 API 只提供客观事实（金额、相似度、告别词等），
    标签判断由调用方（LLM 或 predictor.py 中的规则）负责。

    参数:
        session: 包含"用户信息"、"对话历史"、"坐席回复"的会话记录

    返回:
        ExecutionEngine 实例，已注册 4 个事实数据 API。

    使用示例::

        engine = build_qc_engine(session)

        # 直接调用（predictor.py / 测试）
        credit_facts = engine.registry["get_credit_data"]()
        rep_facts    = engine.registry["get_repetition_data"]()

        # PyTOD 程序调用（Action Parser 生成）
        result = engine.execute_program('''
            x1 get_credit_data()
            x2 get_repetition_data()
        ''')
    """
    engine = ExecutionEngine()
    info = parse_user_info(session["用户信息"])
    history: list = session.get("对话历史", [])
    reply: str = session.get("坐席回复", "")

    # 合法参考金额：available_credit 和 temp_credit（正数有效）
    _gt_values = [v for v in [info["available_credit"], info["temp_credit"]] if v > 0]

    # ----------------------------------------------------------------------- #
    # API 1：get_credit_data — 额度事实（数据错误检测用）
    # ----------------------------------------------------------------------- #

    @engine.register
    def get_credit_data() -> dict:
        """
        提取信用额度相关的客观事实数据。

        提取内容：
          · system_credit     — CRM 记录的可提现额度（唯一客观参照）
          · reply_amounts     — 坐席最终回复中提及的金额（排除奖励额度）
          · withdrawal_amounts — 坐席提现引导语中提及的金额（无货币后缀）
          · discrepant_amounts — 偏差 > 300 元的金额（(文本, 值, 偏差) 列表）
          · max_discrepancy   — 最大偏差金额（元），0 表示无偏差
          · hints             — 供 LLM 参考的文字描述列表

        注意：本 API 不判断是否为"数据错误"，判断由调用方（LLM / predictor）负责。
        """
        def _is_close(value: int) -> bool:
            return any(abs(value - gt) <= _AMOUNT_TOLERANCE for gt in _gt_values)

        hints: list = []
        reply_amounts: list = []       # (text, value)
        withdrawal_amounts: list = []  # (text, value)
        discrepant_amounts: list = []  # (text, value, discrepancy)

        if _gt_values:
            bonus_in_reply = {m.group(1) for m in _BONUS_CREDIT_RE.finditer(reply)}

            # 提取回复中的显式金额
            for amount_text, value in extract_amounts(reply):
                if amount_text in bonus_in_reply:
                    continue
                reply_amounts.append((amount_text, value))
                if value > 1000 and not _is_close(value):
                    diff = abs(value - info["available_credit"])
                    discrepant_amounts.append((amount_text, value, diff))
                    hints.append(
                        f"坐席最终回复提到「{amount_text}」({value:,}元)，"
                        f"系统额度{info['available_credit']:,}元，偏差{diff:,}元 ⚠️"
                    )

            # 提取提现引导语中的金额（无货币后缀）
            seen_w: set = set()
            for m in _WITHDRAWAL_RE.finditer(reply):
                amount_text = m.group(1)
                if amount_text in bonus_in_reply or amount_text in seen_w:
                    continue
                seen_w.add(amount_text)
                value = cn2int(amount_text)
                withdrawal_amounts.append((amount_text, value))
                if value > 1000 and not _is_close(value):
                    diff = abs(value - info["available_credit"])
                    discrepant_amounts.append((amount_text, value, diff))
                    hints.append(
                        f"坐席引导提现提到「{amount_text}」({value:,}元)，"
                        f"系统额度{info['available_credit']:,}元，偏差{diff:,}元 ⚠️"
                    )

            # 补充：额度前缀/后缀模式（无显式"元"后缀，如"额度五万两千五百嘛""三万六千九百的额度"）
            seen_credit_amounts: set = set(t for t, _ in reply_amounts) | seen_w
            for pattern in (_CREDIT_LEAD_RE, _CREDIT_SUFFIX_RE):
                for m in pattern.finditer(reply):
                    amount_text = m.group(1)
                    if amount_text in bonus_in_reply or amount_text in seen_credit_amounts:
                        continue
                    seen_credit_amounts.add(amount_text)
                    value = cn2int(amount_text)
                    if value > 1000 and not _is_close(value):
                        diff = abs(value - info["available_credit"])
                        discrepant_amounts.append((amount_text, value, diff))
                        hints.append(
                            f"坐席回复提及「{amount_text}」({value:,}元)，"
                            f"系统额度{info['available_credit']:,}元，偏差{diff:,}元 ⚠️"
                        )

            # 扫描历史坐席发言（供 LLM hints 参考）
            seen_h: set = set()
            for turn in history:
                if turn.startswith(_AGENT_PREFIX):
                    turn_text = turn.removeprefix(_AGENT_PREFIX)
                    turn_bonus = {m.group(1) for m in _BONUS_CREDIT_RE.finditer(turn_text)}
                    for amount_text, value in extract_amounts(turn_text):
                        if amount_text in turn_bonus or amount_text in seen_h:
                            continue
                        if value > 1000 and not _is_close(value):
                            seen_h.add(amount_text)
                            diff = abs(value - info["available_credit"])
                            hints.append(
                                f"历史坐席发言提到「{amount_text}」({value:,}元)，"
                                f"系统额度{info['available_credit']:,}元，偏差{diff:,}元 ⚠️"
                            )

        max_discrepancy = max((d for _, _, d in discrepant_amounts), default=0)
        return {
            "system_credit": info["available_credit"],
            "temp_credit": info["temp_credit"],
            "reply_amounts": reply_amounts,
            "withdrawal_amounts": withdrawal_amounts,
            "discrepant_amounts": discrepant_amounts,
            "max_discrepancy": max_discrepancy,
            "hints": hints,
        }

    # ----------------------------------------------------------------------- #
    # API 2：get_repetition_data — 重复度量（重复询问检测用）
    # ----------------------------------------------------------------------- #

    @engine.register
    def get_repetition_data(utterance: str = None) -> dict:
        """
        提取坐席回复与历史发言的重复度量数据。

        提取内容：
          · exact_repeat      — 是否与历史某条坐席发言完全一致
          · repeat_count      — 完全一致的历史出现次数
          · max_similarity    — 最高字符相似度（0.0~1.0）
          · most_similar_turn — 相似度最高的历史发言片段
          · hint              — 供 LLM 参考的文字描述

        注意：本 API 不判断是否为"重复询问"，判断由调用方（LLM / predictor）负责。
              精确重复（exact_repeat=True）是强信号，
              相似度 ≥ 0.80 时由 LLM 进一步确认是否实质重复。
        """
        utt = (utterance or reply).strip()
        agent_turns = [
            t.removeprefix(_AGENT_PREFIX).strip()
            for t in history
            if t.startswith(_AGENT_PREFIX)
        ]

        exact_repeat = utt in agent_turns
        repeat_count = agent_turns.count(utt)

        max_sim = 0.0
        most_similar = ""
        for past in agent_turns:
            if not past:
                continue
            common = sum(1 for c in utt if c in past)
            denom = len(utt) + len(past)
            sim = 2 * common / denom if denom > 0 else 0.0
            if sim > max_sim:
                max_sim = sim
                most_similar = past

        hint = ""
        if exact_repeat:
            hint = (
                f"⚠️ 坐席最终回复与历史某条发言完全一致"
                f"（已出现 {repeat_count + 1} 次）"
            )
        elif max_sim >= _REP_SIM_THRESHOLD:
            hint = (
                f"⚠️ 坐席回复与历史发言「{most_similar[:_HINT_TRUNC]}」"
                f"相似度 {max_sim:.0%}（≥{_REP_SIM_THRESHOLD:.0%}）"
            )

        return {
            "exact_repeat": exact_repeat,
            "repeat_count": repeat_count,
            "max_similarity": round(max_sim, 3),
            "most_similar_turn": most_similar,
            "hint": hint,
        }

    # ----------------------------------------------------------------------- #
    # API 3：get_farewell_data — 告别 & 未解决诉求（不当告别检测用）
    # ----------------------------------------------------------------------- #

    @engine.register
    def get_farewell_data() -> dict:
        """
        提取告别话术和用户未解决诉求的事实数据。

        提取内容：
          · has_farewell        — 坐席最终回复是否含告别话术
          · farewell_evidence   — 检测到的告别词/模式
          · last_user_message   — 用户实际最后一条发言（坐席回复前的最后一句话）
          · unresolved_issues   — 最近窗口内用户含诉求词的发言列表
          · unresolved_count    — 未解决诉求数量
          · hint                — 供 LLM 参考的文字描述

        注意：本 API 不判断是否为"不当告别"，判断由调用方（LLM / predictor）负责。
              has_farewell=True 且 unresolved_count > 0 时，
              LLM 需进一步判断诉求是否真实未解决（用户可能已表示同意/拒绝）。
              hint 区分两种情形：⚠️ 表示用户最后一条消息本身含诉求词（当前诉求），
              无 ⚠️ 表示仅历史消息含诉求词而用户最后消息无诉求词（历史诉求，可能已解决）。
        """
        farewell_score = sum(1 for kw in FAREWELL_KEYWORDS if kw in reply)
        farewell_evidence = [kw for kw in FAREWELL_KEYWORDS if kw in reply]
        soft_matches = [p for p in FAREWELL_SOFT_PATTERNS if p in reply]

        has_farewell = farewell_score >= 1 or bool(soft_matches)
        if soft_matches:
            farewell_evidence.extend(soft_matches)

        last_user_turns = [
            t.removeprefix(_USER_PREFIX)
            for t in history[-_FAREWELL_HISTORY_WINDOW:]
            if t.startswith(_USER_PREFIX)
        ]
        unresolved_issues = [
            t for t in last_user_turns if any(w in t for w in USER_CONCERN_WORDS)
        ]

        # 用户实际最后一条发言（不受窗口限制；逆序遍历取第一条用户发言）
        last_user_msg = next(
            (t.removeprefix(_USER_PREFIX) for t in reversed(history) if t.startswith(_USER_PREFIX)),
            "",
        )
        last_msg_has_concern = any(w in last_user_msg for w in USER_CONCERN_WORDS)

        hint = ""
        if unresolved_issues:
            last_issue = unresolved_issues[-1][:_HINT_TRUNC]
            last_user_short = last_user_msg[:_HINT_TRUNC]
            if last_msg_has_concern:
                # 用户最后一条消息本身含诉求词：当前诉求，重要信号
                hint = (
                    f"⚠️ 用户最后一条消息含诉求词：「{last_user_short}」"
                    f"（近期共 {len(unresolved_issues)} 条含诉求词消息）"
                )
            else:
                # 用户最后一条消息无诉求词：历史诉求，可能已解决
                hint = (
                    f"用户最后一条消息：「{last_user_short}」（无诉求词）；"
                    f"历史含诉求词 {len(unresolved_issues)} 条"
                    f"（最近：「{last_issue}」）"
                )

        return {
            "has_farewell": has_farewell,
            "farewell_evidence": farewell_evidence,
            "last_user_message": last_user_msg,
            "unresolved_issues": unresolved_issues,
            "unresolved_count": len(unresolved_issues),
            "hint": hint,
        }

    # ----------------------------------------------------------------------- #
    # API 4：get_topic_data — 话题相关性（答非所问检测用）
    # ----------------------------------------------------------------------- #

    @engine.register
    def get_topic_data() -> dict:
        """
        提取用户最近问题和话题相关性的事实数据。

        提取内容：
          · last_user_message   — 用户最近一条发言的完整内容
          · user_asks_amount    — 用户是否在询问具体金额（"多少"类问题）
          · topic_mismatch_hint — 话题不匹配的初步信号（由规则生成，供 LLM 参考）

        注意：本 API 不判断是否为"答非所问"，判断由调用方（LLM / predictor）负责。
              topic_mismatch_hint 是弱信号，LLM 需结合语义判断是否真正答非所问。
              多数情况下坐席回复贷款相关话题即视为切题，不应轻易标注为答非所问。
        """
        last_user = next(
            (
                t.removeprefix(_USER_PREFIX)
                for t in reversed(history)
                if t.startswith(_USER_PREFIX)
            ),
            "",
        )

        # 判断用户是否在询问具体金额
        user_asks_amount = any(w in last_user for w in _AMOUNT_QUESTION_WORDS)

        # 判断坐席回复是否包含中文数字金额（有实质数字信息）
        agent_has_amount = bool(
            re.search(r"[零一二三四五六七八九十百千万亿两]+(?:元|万|千|百)", reply)
        )
        # 判断坐席是否进行品牌/身份自我介绍而非回答问题
        agent_is_intro = bool(_AGENT_INTRO_RE.search(reply))
        # 判断坐席是否将问题反问回用户而非给出答案
        agent_echoes_question = bool(_AGENT_ECHO_RE.search(reply))

        topic_mismatch_hint = ""

        # 首先使用已有 OFFTOPIC_SIGNALS 规则生成 hint
        for q_word, irrelevant_patterns in OFFTOPIC_SIGNALS.items():
            if q_word in last_user:
                mismatches = [p for p in irrelevant_patterns if p in reply]
                if mismatches:
                    topic_mismatch_hint = (
                        f"初步信号：用户发言含「{q_word}」，"
                        f"但坐席回复含「{mismatches[0]}」（仅供参考，需 LLM 语义确认）"
                    )
                    break

        # 补充：结构性不匹配信号（优先级更高，覆盖 OFFTOPIC_SIGNALS 未覆盖的场景）
        if not topic_mismatch_hint:
            if user_asks_amount and agent_is_intro:
                topic_mismatch_hint = (
                    f"⚠️ 用户询问「{last_user[:_HINT_TRUNC]}」，"
                    f"坐席进行了品牌/身份自我介绍而未提供金额"
                )
            elif user_asks_amount and agent_echoes_question:
                topic_mismatch_hint = (
                    f"⚠️ 用户询问「{last_user[:_HINT_TRUNC]}」，"
                    f"坐席将问题反问回用户（未给出实质答案）"
                )
            elif user_asks_amount and not agent_has_amount:
                topic_mismatch_hint = (
                    f"用户询问金额「{last_user[:_HINT_TRUNC]}」，"
                    f"坐席回复未含明确数字（若坐席正在核实身份或做引导性回复，不算答非所问）"
                )

        return {
            "last_user_message": last_user,
            "user_asks_amount": user_asks_amount,
            "topic_mismatch_hint": topic_mismatch_hint,
        }

    return engine

