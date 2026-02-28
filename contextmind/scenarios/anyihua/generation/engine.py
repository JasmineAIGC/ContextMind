"""
安逸花外呼 · 任务二（Generation）· ExecutionEngine 构建

将 CRM 查询 API 注册为 PyTOD ExecutionEngine 的可调用函数，
供动作解析器（Action Parser）在 PyTOD 程序中调用，
以便对话管理器（Dialogue Manager）基于真实数据生成坐席回复。

注册的 5 个 API：
    query_account(customer_name)             — 查询账户额度信息（核心数据源）
    calculate_repayment(amount, months)      — 计算月还款额和总手续费
    check_repetition(utterance)              — 检测话术是否已重复说过
    check_farewell_preconditions(customer_name) — 检查是否可以告别
    query_loan_records(customer_name)        — 查询借款记录

与 QC 引擎的区别：
    - QC 引擎（qc/engine.py）注册的是「标签检测器」，用于判断对话质量
    - 生成引擎（本文件）注册的是「CRM 查询器」，用于获取数据以生成回复
    - 两者目的不同、数据不同，不可共用
"""

from __future__ import annotations

from typing import Any, Dict

from contextmind.modes.pytod import ExecutionEngine

from ..utils import (
    AGENT_PREFIX as _AGENT_PREFIX,
    FAREWELL_KEYWORDS,
    FAREWELL_SOFT_PATTERNS,
    USER_CONCERN_WORDS,
    USER_PREFIX as _USER_PREFIX,
    parse_user_info,
)

# 不当告别检测历史窗口大小
_FAREWELL_HISTORY_WINDOW = 12


def build_generation_engine(session: Dict[str, Any]) -> ExecutionEngine:
    """
    为安逸花生成任务构建 ExecutionEngine，注册 5 个 CRM 查询 API。

    动作解析器（LLM）根据 ANYIHUA_SCHEMA 生成 PyTOD 程序，
    执行引擎调用这些 API 获取真实 CRM 数据，
    对话管理器（LLM）再基于数据生成准确的坐席回复。

    参数:
        session: chat_test_100.json 单条记录，须包含键：
                 "用户信息", "对话历史"

    返回:
        ExecutionEngine 实例，已注册 5 个 CRM 查询 API。

    使用示例::

        from contextmind.modes.pytod import PyTODTracker, PyTODPromptBuilder
        from contextmind.scenarios.anyihua.generation import (
            build_generation_engine, ANYIHUA_SCHEMA
        )

        engine = build_generation_engine(session)
        builder = PyTODPromptBuilder(schema=ANYIHUA_SCHEMA, response_language="中文")
        tracker = PyTODTracker(llm_client=llm, execution_engine=engine, prompt_builder=builder)
        result = await tracker.process_turn(user_utterance="我的额度是多少？")
    """
    engine = ExecutionEngine()
    info = parse_user_info(session["用户信息"])
    history: list = session.get("对话历史", [])

    # ----------------------------------------------------------------------- #
    # API 1：query_account — 查询账户信息（核心数据源）
    # ----------------------------------------------------------------------- #

    @engine.register
    def query_account(customer_name: str = None) -> dict:
        """
        查询客户账户信息（额度、利率、借款状态等）。

        动作解析器在 explain_credit_limit / explain_displayed_amount 意图时
        必须先调用此 API 获取 available_credit，不得自行估算（防止数据错误）。
        """
        temp_status = (
            "已过期" if info["temp_expired"]
            else f"有效（剩余{info['temp_active_days']}天）" if info["temp_active_days"] > 0
            else "无临时额度"
        )
        return {
            "customer_name": info["customer_name"],
            "available_credit": info["available_credit"],
            "temp_credit": info["temp_credit"],
            "temp_credit_status": temp_status,
            "temp_active_days": info["temp_active_days"],
            "annual_rate_pct": info["annual_rate_pct"],
            "loan_count": info["loan_count"],
            "last_loan_date": info["last_loan_date"],
            "outstanding_amount": info["outstanding_amount"],
            "loan_outstanding": info["loan_outstanding"],
        }

    # ----------------------------------------------------------------------- #
    # API 2：calculate_repayment — 计算还款信息
    # ----------------------------------------------------------------------- #

    @engine.register
    def calculate_repayment(amount: int = None, months: int = None) -> dict:
        """
        计算指定金额和期数的月还款额和总手续费。

        在 calculate_repayment / explain_interest_rate 意图时调用。
        """
        principal = amount or info["available_credit"]
        n = months or 12
        rate = info["annual_rate_pct"] / 100 / 12
        if rate > 0:
            monthly = principal * rate * (1 + rate) ** n / ((1 + rate) ** n - 1)
        else:
            monthly = principal / n
        total = monthly * n
        return {
            "amount": principal,
            "months": n,
            "monthly_payment": round(monthly),
            "total_payment": round(total),
            "total_interest": round(total - principal),
            "annual_rate_pct": info["annual_rate_pct"],
        }

    # ----------------------------------------------------------------------- #
    # API 3：check_repetition — 检测话术是否已重复
    # ----------------------------------------------------------------------- #

    @engine.register
    def check_repetition(utterance: str = None) -> dict:
        """
        检测坐席即将说的话是否与历史发言重复。

        在 guide_loan_operation 意图时调用：
        - repeat_count >= 2 时建议改为 escalate_to_human
        - repeat_count == 1 时提示换一种说法
        """
        utt = (utterance or "").strip()
        agent_turns = [
            t.removeprefix(_AGENT_PREFIX).strip()
            for t in history
            if t.startswith(_AGENT_PREFIX)
        ]
        is_exact = utt in agent_turns
        count = agent_turns.count(utt)
        return {
            "is_repetitive": is_exact,
            "repeat_count": count,
            "recommendation": (
                "建议转人工" if count >= 2
                else "建议换一种方式说明" if count == 1
                else "可以继续"
            ),
        }

    # ----------------------------------------------------------------------- #
    # API 4：check_farewell_preconditions — 检查告别前提
    # ----------------------------------------------------------------------- #

    @engine.register
    def check_farewell_preconditions(customer_name: str = None) -> dict:
        """
        检查是否满足礼貌告别的前提条件（用户无未解决诉求）。

        say_goodbye 意图执行前必须调用此 API，
        can_farewell=False 时应先解决用户问题或转人工。
        """
        last_user_turns = [
            t.removeprefix(_USER_PREFIX)
            for t in history[-_FAREWELL_HISTORY_WINDOW:]
            if t.startswith(_USER_PREFIX)
        ]
        unresolved = [t for t in last_user_turns if any(w in t for w in USER_CONCERN_WORDS)]
        return {
            "can_farewell": not bool(unresolved),
            "unresolved_issues": unresolved,
            "recommendation": "可以告别" if not unresolved else "请先解决用户问题或转人工",
        }

    # ----------------------------------------------------------------------- #
    # API 5：query_loan_records — 查询借款记录
    # ----------------------------------------------------------------------- #

    @engine.register
    def query_loan_records(customer_name: str = None) -> dict:
        """
        查询客户借款记录（用于 handle_loan_dispute 意图）。

        提供历史借款笔数、最近借款日期和未还款金额，
        帮助坐席核实用户争议的借款事实。
        """
        return {
            "customer_name": info["customer_name"],
            "loan_count": info["loan_count"],
            "last_loan_date": info["last_loan_date"],
            "outstanding_amount": info["outstanding_amount"],
            "loan_outstanding": info["loan_outstanding"],
        }

    return engine
