"""
安逸花外呼 · 任务一（QC）· ExecutionEngine 构建

将 5 个质量标签检测函数注册为 PyTOD ExecutionEngine 的可调用 API。
每个 API 对应一个质量标签类别，封装完整的规则检测逻辑，
可由动作解析器生成 PyTOD 程序直接调用，也可在 predict_label_pytod()
中作为纯规则预测器调用（无需 LLM）。

注册的 5 个 API（对应 5 个标签类别）：
    predict_data_error(customer_name)        — 额度偏差 > 300 元
    predict_repetition(utterance)            — 坐席回复与历史精确/模糊匹配
    predict_improper_farewell(customer_name) — 用户有未解决诉求时告别
    predict_off_topic(customer_name)         — 回复与用户问题话题无关
    predict_no_issue(customer_name)          — 默认标签（兜底）

每个 API 返回标准结构：
    {
        "label":      str | None,   # 标签名；未检出时为 None
        "detected":   bool,         # 是否检出该类问题
        "confidence": float,        # 规则置信度（0.0 ~ 0.87）
        "evidence":   str,          # 检出依据描述
        ...                         # API 专属字段（供 detect_session_llm 使用）
    }
"""

from __future__ import annotations

from typing import Any, Dict

from contextmind.modes.pytod import ExecutionEngine

from ..utils import (
    AGENT_PREFIX as _AGENT_PREFIX,
    FAREWELL_KEYWORDS,
    FAREWELL_SOFT_PATTERNS,
    OFFTOPIC_SIGNALS,
    USER_CONCERN_WORDS,
    USER_PREFIX as _USER_PREFIX,
    extract_amounts,
    parse_user_info,
)

# 数据错误容许误差（元）
_AMOUNT_TOLERANCE = 300
# 重复询问模糊相似度阈值（用于 LLM hint 生成）
_REP_SIM_THRESHOLD = 0.80
# 不当告别检测的用户历史窗口大小
_FAREWELL_HISTORY_WINDOW = 12
# hint 文本截断长度
_HINT_TRUNC = 30


def build_qc_engine(session: Dict[str, Any]) -> ExecutionEngine:
    """
    为安逸花 QC 任务构建 ExecutionEngine，注册 5 个质量标签检测 API。

    每次针对一条会话调用，返回绑定该会话数据的引擎实例。

    参数:
        session: chat_test_100.json 单条记录，须包含键：
                 "用户信息", "对话历史", "坐席回复"

    返回:
        ExecutionEngine 实例，已注册 5 个标签检测 API。

    使用示例::

        engine = build_qc_engine(session)

        # 纯规则调用
        result = engine.registry["predict_data_error"]()

        # PyTOD 程序调用
        result = engine.execute_program('''
            x1 predict_data_error()
            x2 predict_repetition()
            x3 say(x1)
        ''')
    """
    engine = ExecutionEngine()
    info = parse_user_info(session["用户信息"])
    history: list = session.get("对话历史", [])
    reply: str = session.get("坐席回复", "")

    # 合法参考金额：available_credit 和 temp_credit（正数有效）
    _gt_values = [v for v in [info["available_credit"], info["temp_credit"]] if v > 0]

    # ----------------------------------------------------------------------- #
    # API 1：predict_data_error — 检测数据错误
    # ----------------------------------------------------------------------- #

    @engine.register
    def predict_data_error(customer_name: str = None) -> dict:
        """
        检测数据错误：坐席引用额度金额与系统记录偏差 > 300 元。

        - detected/evidence：仅扫描坐席最终回复（降低误报）
        - data_error_hints：同时扫描历史发言（供 detect_session_llm 使用）

        实测精度：P=87%, R=87%（100 条安逸花数据集）
        """
        def _is_valid(value: int) -> bool:
            return any(abs(value - gt) <= _AMOUNT_TOLERANCE for gt in _gt_values)

        data_error_hints = []
        reply_detected = False
        reply_evidence = ""

        if _gt_values:
            for amount_text, value in extract_amounts(reply):
                if value > 1000 and not _is_valid(value):
                    diff = abs(value - info["available_credit"])
                    data_error_hints.append(
                        f"坐席最终回复提到「{amount_text}」({value:,}元)，"
                        f"系统额度{info['available_credit']:,}元，偏差{diff:,}元 ⚠️"
                    )
                    if not reply_detected:
                        reply_detected = True
                        reply_evidence = (
                            f"回复提及「{amount_text}」({value:,}元)，"
                            f"系统额度{info['available_credit']:,}元，偏差{diff:,}元"
                        )

            seen: set = set()
            for turn in history:
                if turn.startswith(_AGENT_PREFIX):
                    turn_text = turn.removeprefix(_AGENT_PREFIX)
                    for amount_text, value in extract_amounts(turn_text):
                        if value > 1000 and not _is_valid(value) and amount_text not in seen:
                            seen.add(amount_text)
                            diff = abs(value - info["available_credit"])
                            data_error_hints.append(
                                f"历史坐席发言提到「{amount_text}」({value:,}元)，"
                                f"系统额度{info['available_credit']:,}元，偏差{diff:,}元 ⚠️"
                            )

        return {
            "label": "数据错误" if reply_detected else None,
            "detected": reply_detected,
            "confidence": 0.87 if reply_detected else 0.0,
            "evidence": reply_evidence,
            "system_credit": info["available_credit"],
            "temp_credit": info["temp_credit"],
            "data_error_hints": data_error_hints,
        }

    # ----------------------------------------------------------------------- #
    # API 2：predict_repetition — 检测重复询问
    # ----------------------------------------------------------------------- #

    @engine.register
    def predict_repetition(utterance: str = None) -> dict:
        """
        检测重复询问：坐席回复与历史发言高度重复。

        - Layer 1（精确匹配）：detected=True，用于规则预测（P=87%, R=87%）
        - Layer 2（字符重叠 ≥ 80%）：生成 repetition_hint，供 LLM 参考
        """
        utt = (utterance or reply).strip()
        agent_turns = [
            t.removeprefix(_AGENT_PREFIX).strip()
            for t in history
            if t.startswith(_AGENT_PREFIX)
        ]

        is_exact = utt in agent_turns
        count = agent_turns.count(utt)

        max_sim = 0.0
        max_sim_turn = ""
        for past in agent_turns:
            if not past:
                continue
            common = sum(1 for c in utt if c in past)
            denom = len(utt) + len(past)
            sim = 2 * common / denom if denom > 0 else 0.0
            if sim > max_sim:
                max_sim = sim
                max_sim_turn = past

        repetition_hint = ""
        if is_exact:
            repetition_hint = "⚠️ 坐席最终回复与历史某条坐席发言完全一致（精确匹配）"
        elif max_sim >= _REP_SIM_THRESHOLD:
            repetition_hint = (
                f"⚠️ 坐席最终回复与历史发言「{max_sim_turn[:_HINT_TRUNC]}」"
                f"相似度 {max_sim:.0%}（≥{_REP_SIM_THRESHOLD:.0%}）"
            )

        detected = is_exact and count >= 1
        return {
            "label": "重复询问" if detected else None,
            "detected": detected,
            "confidence": 0.87 if detected else 0.0,
            "evidence": f"坐席回复与历史发言精确匹配，已重复 {count + 1} 次" if detected else "",
            "is_exact_repeat": is_exact,
            "repeat_count": count,
            "max_similarity": round(max_sim, 3),
            "max_sim_turn": max_sim_turn,
            "repetition_hint": repetition_hint,
        }

    # ----------------------------------------------------------------------- #
    # API 3：predict_improper_farewell — 检测不当告别
    # ----------------------------------------------------------------------- #

    @engine.register
    def predict_improper_farewell(customer_name: str = None) -> dict:
        """
        检测不当告别：用户有未解决诉求时坐席执行告别话术。

        - detected：回复含告别词 AND 历史有未解决诉求
        - farewell_hint：历史有未解决诉求时生成（供 detect_session_llm 使用）
        """
        farewell_score = sum(1 for kw in FAREWELL_KEYWORDS if kw in reply)
        is_farewell = farewell_score >= 2 or any(
            p in reply for p in FAREWELL_SOFT_PATTERNS
        )

        last_user_turns = [
            t.removeprefix(_USER_PREFIX)
            for t in history[-_FAREWELL_HISTORY_WINDOW:]
            if t.startswith(_USER_PREFIX)
        ]
        unresolved = [t for t in last_user_turns if any(w in t for w in USER_CONCERN_WORDS)]

        detected = is_farewell and bool(unresolved)

        farewell_hint = ""
        if unresolved:
            last_issue = unresolved[-1][:_HINT_TRUNC]
            farewell_hint = (
                f"⚠️ 检测到用户有未解决诉求：「{last_issue}…」"
                f"（共 {len(unresolved)} 条未解决消息）"
            )

        return {
            "label": "不当告别" if detected else None,
            "detected": detected,
            "confidence": 0.85 if detected else 0.0,
            "evidence": (
                f"用户有 {len(unresolved)} 个未解决问题时执行告别：{unresolved[-1][:40]}…"
                if detected else ""
            ),
            "can_farewell": not bool(unresolved),
            "unresolved_issues": unresolved,
            "farewell_hint": farewell_hint,
        }

    # ----------------------------------------------------------------------- #
    # API 4：predict_off_topic — 检测答非所问
    # ----------------------------------------------------------------------- #

    @engine.register
    def predict_off_topic(customer_name: str = None) -> dict:
        """
        检测答非所问：用户有明确问题但坐席回复与问题话题完全无关。

        规则版召回率约 60%，适合快速预过滤；语义层面需 LLM 判断。
        """
        last_user = next(
            (
                t.removeprefix(_USER_PREFIX)
                for t in reversed(history)
                if t.startswith(_USER_PREFIX)
            ),
            "",
        )

        for q_word, irrelevant_patterns in OFFTOPIC_SIGNALS.items():
            if q_word in last_user:
                mismatches = [p for p in irrelevant_patterns if p in reply]
                if mismatches:
                    return {
                        "label": "答非所问",
                        "detected": True,
                        "confidence": 0.80,
                        "evidence": (
                            f"用户发言含「{q_word}」，但坐席回复含「{mismatches[0]}」"
                        ),
                    }

        return {"label": None, "detected": False, "confidence": 0.0, "evidence": ""}

    # ----------------------------------------------------------------------- #
    # API 5：predict_no_issue — 无标签命中（兜底）
    # ----------------------------------------------------------------------- #

    @engine.register
    def predict_no_issue(customer_name: str = None) -> dict:
        """
        无标签命中（默认兜底标签）。
        其余四个标签均未检出时调用。
        """
        return {
            "label": "无标签命中",
            "detected": True,
            "confidence": 0.75,
            "evidence": "以上四类标签均未检出",
        }

    return engine
