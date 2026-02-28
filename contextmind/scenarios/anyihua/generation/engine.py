"""
安逸花外呼 · 任务二（Generation）· ExecutionEngine 构建

将 CRM 查询 API 注册为 PyTOD ExecutionEngine 的可调用函数，
供动作解析器（Action Parser）在 PyTOD 程序中调用，
以便对话管理器（Dialogue Manager）基于真实数据生成坐席回复。

注册的 6 个 API（均为纯数据查询，不返回建议或决策）：
    verify_customer(name, phone_suffix) — 验证客户身份（核实姓名和手机尾号）
    query_account()                     — 查询账户额度信息（核心数据源）
    calculate_repayment(amount, months) — 计算月还款额和总手续费
    get_agent_history()                 — 获取历史坐席话术列表（供对话管理器避免重复）
    query_unresolved_issues()           — 查询用户未解决诉求（供对话管理器决定是否告别）
    query_loan_records()                — 查询借款记录

API 设计原则：
    - 所有 API 只返回原始数据，不做推断或建议（决策由对话管理器 LLM 负责）
    - 与 QC 引擎（qc/engine.py）完全独立，目的和数据均不同
"""

from __future__ import annotations

from typing import Any, Dict

from contextmind.modes.pytod import ExecutionEngine

from ..utils import (
    AGENT_PREFIX as _AGENT_PREFIX,
    USER_CONCERN_WORDS,
    USER_PREFIX as _USER_PREFIX,
    parse_user_info,
)

# 不当告别检测历史窗口大小
_FAREWELL_HISTORY_WINDOW = 12


def build_generation_engine(session: Dict[str, Any]) -> ExecutionEngine:
    """
    为安逸花生成任务构建 ExecutionEngine，注册 6 个 CRM 数据查询 API。

    动作解析器（LLM）根据 ANYIHUA_SCHEMA 生成 PyTOD 程序，
    执行引擎调用这些 API 获取真实 CRM 数据，
    对话管理器（LLM）再基于数据生成准确的坐席回复。

    参数:
        session: chat_test_100.json 单条记录，须包含键：
                 "用户信息", "对话历史"

    返回:
        ExecutionEngine 实例，已注册 5 个 CRM 数据查询 API。

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
    # API 1：verify_customer — 核实客户身份
    # ----------------------------------------------------------------------- #

    def _check_name_match(provided: str, stored: str) -> bool:
        """姓名匹配：支持部分匹配（如'高先生'匹配'高'或反向）"""
        if not provided or not stored:
            return False
        return stored in provided or provided in stored

    def _check_phone_match(provided: str, stored: str) -> bool:
        """手机尾号匹配：忽略'末'字前缀，检查尾号是否出现在提供值中"""
        if not provided or not stored:
            return False
        normalized = stored.replace("末", "").strip()
        return normalized in provided

    @engine.register
    def verify_customer(name: str = None, phone_suffix: str = None) -> dict:
        """
        核实客户身份：验证来电人提供的姓名和手机尾号与系统记录是否一致。

        动作解析器在 verify_identity 意图时调用此 API，
        通过对比用户提供的姓名和手机尾号来确认来电者是账户本人。

        返回的 identity_confirmed 字段供对话管理器（LLM）决策：
        · identity_confirmed=True：可继续告知账户信息并推介借款
        · identity_confirmed=False：不应告知账户详情，应礼貌询问或终止通话
        """
        name_match = _check_name_match(name, info["customer_name"]) if name is not None else None
        phone_match = _check_phone_match(phone_suffix, info["phone_suffix"]) if phone_suffix is not None else None

        return {
            "customer_name": info["customer_name"],
            "phone_suffix": info["phone_suffix"],
            "name_provided": name,
            "phone_suffix_provided": phone_suffix,
            "name_match": name_match,
            "phone_match": phone_match,
            "identity_confirmed": bool(name_match),
        }

    # ----------------------------------------------------------------------- #
    # API 2：query_account — 查询账户信息（核心数据源）
    # ----------------------------------------------------------------------- #

    @engine.register
    def query_account() -> dict:
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
    # API 3：calculate_repayment — 计算还款信息
    # ----------------------------------------------------------------------- #

    @engine.register
    def calculate_repayment(amount: int = None, months: int = None) -> dict:
        """
        计算指定金额和期数的月还款额和总手续费。

        在 calculate_repayment / explain_interest_rate 意图时调用。
        LLM 有时以字符串形式传入数值参数，此处强制转为整数以避免类型错误。
        """
        principal = int(amount) if amount is not None else info["available_credit"]
        n = int(months) if months is not None else 12
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
    # API 4：get_agent_history — 获取历史坐席话术
    # ----------------------------------------------------------------------- #

    @engine.register
    def get_agent_history() -> dict:
        """
        返回对话历史中所有坐席发言的列表。

        对话管理器在生成回复前调用此 API，
        对照历史话术避免重复说完全相同的内容；
        若历史中同一话术已出现 2 次以上，应改变表达或转人工。
        """
        agent_turns = [
            t.removeprefix(_AGENT_PREFIX).strip()
            for t in history
            if t.startswith(_AGENT_PREFIX)
        ]
        return {
            "agent_turns": agent_turns,
            "turn_count": len(agent_turns),
        }

    # ----------------------------------------------------------------------- #
    # API 5：query_unresolved_issues — 查询用户未解决诉求
    # ----------------------------------------------------------------------- #

    @engine.register
    def query_unresolved_issues() -> dict:
        """
        返回最近对话中用户尚未得到回答的诉求列表。

        对话管理器在执行 say_goodbye 意图前调用此 API，
        仅当 issue_count=0（无未解决诉求）时才可礼貌告别，
        否则应继续解决问题或转人工，不得直接告别。
        """
        last_user_turns = [
            t.removeprefix(_USER_PREFIX)
            for t in history[-_FAREWELL_HISTORY_WINDOW:]
            if t.startswith(_USER_PREFIX)
        ]
        unresolved = [t for t in last_user_turns if any(w in t for w in USER_CONCERN_WORDS)]
        return {
            "unresolved_issues": unresolved,
            "issue_count": len(unresolved),
        }

    # ----------------------------------------------------------------------- #
    # API 6：query_loan_records — 查询借款记录
    # ----------------------------------------------------------------------- #

    @engine.register
    def query_loan_records() -> dict:
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
