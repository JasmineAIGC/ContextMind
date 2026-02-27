"""
安逸花外呼促活场景 · ExecutionEngine 构建

将解析后的 用户信息 字段注册为可调用 API 函数，接入 PyTOD ExecutionEngine。

注册的 API 函数模拟真实 CRM 接口，供动作解析器生成 PyTOD 程序、
执行引擎调用、对话管理器基于真实数据生成回复。

注册的 API 列表：
    query_account(customer_name)              - 查询账户基本信息（额度/利率/银行）
    query_loan_records(customer_name, target_date) - 查询借款记录（含争议日期核实）
    calculate_monthly_payment(amount, term_months, annual_rate_pct) - 计算月还款额
    check_farewell_preconditions(customer_name) - 检查是否满足告别前提
    check_repetition(utterance)               - 检查话语是否历史重复
    escalate_to_human(customer_name, issue, priority) - 提交转人工工单

基于 docs/analysis/pytod-on-chat-test-100.md §3.3 和 §7.1 实现。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from contextmind.modes.pytod import ExecutionEngine

from .utils import parse_user_info


def build_anyihua_engine(session: Dict[str, Any]) -> ExecutionEngine:
    """
    为安逸花外呼场景构建 ExecutionEngine，将 用户信息 字段注册为可调用 CRM API。

    每次针对一个会话调用，返回绑定了该会话数据的 ExecutionEngine 实例。
    动作解析器可在 PyTOD 程序中调用这些 API 获取当前客户的真实数据，
    从根本上避免 AI 坐席引用错误金额数字（幻觉）。

    参数:
        session: chat_test_100.json 中的单条记录，包含键：
                 - "用户信息": "#" 分隔的客户属性字段串
                 - "对话历史": 对话历史列表
                 - "session_id": 会话唯一标识

    返回:
        ExecutionEngine 实例，已注册以下 6 个 API 函数：
        query_account / query_loan_records / calculate_monthly_payment /
        check_farewell_preconditions / check_repetition / escalate_to_human

    使用示例::

        engine = build_anyihua_engine(session)
        result = engine.execute_program('''
            x1 query_account(customer_name='高先生')
            x2 say(x1)
        ''')
        # result.variable_values['x1'] 包含真实账户数据
        # result.say_output 为格式化输出
    """
    engine = ExecutionEngine()
    info = parse_user_info(session["用户信息"])
    history: list = session.get("对话历史", [])
    session_id: str = session.get("session_id", "UNKNOWN")

    @engine.register
    def query_account(customer_name: str = None) -> dict:
        """
        查询客户账户基本信息。

        返回额度、利率、绑定银行、借款状态等核心字段。
        这是防止数据错误最关键的 API：
        坐席必须引用此 API 返回的 available_credit，不得自行估算。
        """
        return {
            "customer_name": info["customer_name"],
            "available_credit": info["available_credit"],
            "temp_credit": info["temp_credit"],
            "temp_expired": info["temp_expired"],
            "temp_active_days": info["temp_active_days"],
            "annual_rate_pct": info["annual_rate_pct"],
            "bound_bank": info["bound_bank"],
            "loan_count": info["loan_count"],
            "outstanding_amount": info["outstanding_amount"],
            "loan_outstanding": info["loan_outstanding"],
            # 重要说明：当临时额度有效时，APP 显示的总可借额度
            # = available_credit（含有效临时额度效果）；
            # 过期后 APP 显示回落到基础额度。
            # 坐席回复应只引用 available_credit，不要自行叠加 temp_credit。
            "effective_credit": info["available_credit"],
        }

    @engine.register
    def query_loan_records(
        customer_name: str = None,
        target_date: str = None,
    ) -> dict:
        """
        查询借款记录。

        target_date 用于核实用户争议的借款日期，
        例如用户声称"七月二十三号借过款"但系统无记录时，
        将 target_date='七月二十三号' 传入进行核实。
        """
        last_date = info["last_loan_date"]
        has_loan_on_date: Optional[bool] = None
        if target_date:
            has_loan_on_date = target_date in last_date
        return {
            "customer_name": info["customer_name"],
            "loan_count": info["loan_count"],
            "last_loan_date": last_date,
            "has_loan_on_date": has_loan_on_date,
            "loan_outstanding": info["loan_outstanding"],
            "outstanding_amount": info["outstanding_amount"],
        }

    @engine.register
    def calculate_monthly_payment(
        amount: float = None,
        term_months: int = 12,
        annual_rate_pct: float = None,
    ) -> dict:
        """
        计算月还款额和总手续费（等额还款公式）。

        用于处理用户询问"分12期每月还多少钱"的场景。
        等额还款公式：M = P * r(1+r)^n / ((1+r)^n - 1)
        其中 P=本金，r=月利率，n=期数。

        参数:
            amount:          借款金额（元），默认使用 available_credit
            term_months:     分期期数，默认 12
            annual_rate_pct: 年化利率（%），默认使用 用户信息 中的利率

        返回:
            principal / term_months / annual_rate_pct /
            monthly_payment / total_interest / total_payment
        """
        rate = (annual_rate_pct or info["annual_rate_pct"]) / 100 / 12
        n = term_months
        amt = amount or info["available_credit"]
        if rate == 0:
            monthly = round(amt / n, 2)
        else:
            monthly = round(amt * rate * (1 + rate) ** n / ((1 + rate) ** n - 1), 2)
        total_interest = round(monthly * n - amt, 2)
        return {
            "principal": amt,
            "term_months": n,
            "annual_rate_pct": annual_rate_pct or info["annual_rate_pct"],
            "monthly_payment": monthly,
            "total_interest": total_interest,
            "total_payment": round(monthly * n, 2),
        }

    @engine.register
    def check_farewell_preconditions(customer_name: str = None) -> dict:
        """
        检查是否满足告别前提条件。

        通过分析对话历史中用户最近几轮发言的关键词，
        判断用户是否仍有未解决的诉求。
        如果 can_farewell=False，坐席不应执行告别话术。
        """
        concern_words = [
            "为什么", "怎么", "没有", "借不出", "不对", "不是", "投诉",
            "能不能", "可不可以", "怎么办", "解冻", "申请", "问一下",
        ]
        last_user_turns = [t.removeprefix("用户：") for t in history[-8:] if t.startswith("用户：")]
        unresolved = [
            t for t in last_user_turns if any(w in t for w in concern_words)
        ]
        return {
            "can_farewell": len(unresolved) == 0,
            "unresolved_issues": unresolved,
            "recommendation": (
                "可以礼貌告别"
                if not unresolved
                else f"用户尚有问题未解决：{unresolved[-1][:30]}…"
            ),
        }

    @engine.register
    def check_repetition(utterance: str = None, threshold: float = 0.85) -> dict:
        """
        检查即将发出的回复是否已在对话历史中出现过。

        实测数据：15 条重复询问中 13 条（87%）可通过精确字符串匹配检出。
        先做精确匹配（Layer 1），再做字符重叠相似度匹配（Layer 2）。

        参数:
            utterance:  即将发出的坐席话语
            threshold:  字符相似度阈值（Layer 2），默认 0.85
        """
        agent_turns = [t.removeprefix("坐席：").strip() for t in history if t.startswith("坐席：")]
        utt = (utterance or "").strip()

        is_exact = utt in agent_turns
        count = agent_turns.count(utt)

        max_sim = 0.0
        for past in agent_turns:
            if not past:
                continue
            common = sum(1 for c in utt if c in past)
            denom = len(utt) + len(past)
            sim = 2 * common / denom if denom > 0 else 0.0
            max_sim = max(max_sim, sim)

        return {
            "is_exact_repeat": is_exact,
            "repeat_count": count,
            "max_similarity": round(max_sim, 3),
            "recommendation": (
                f"已重复 {count + 1} 次，建议换方式解释或转人工"
                if is_exact and count >= 1
                else "首次出现"
            ),
        }

    @engine.register
    def escalate_to_human(
        customer_name: str = None,
        issue: str = None,
        priority: str = "普通",
    ) -> dict:
        """
        提交转人工工单。

        适用场景：
        - 同一说法重复 2 次以上仍无法解决用户问题
        - 用户明确要求投诉或转人工
        - 账单争议等复杂问题坐席无法独立处理

        参数:
            customer_name: 客户姓名
            issue:         问题描述（转接原因）
            priority:      优先级，可选 "普通" / "高" / "紧急"
        """
        wait_map = {"紧急": "约1分钟", "高": "约3分钟"}
        return {
            "status": "转接中",
            "customer_name": customer_name or info["customer_name"],
            "issue": issue or "用户有未解决问题",
            "priority": priority,
            "estimated_wait": wait_map.get(priority, "约5分钟"),
            "ticket_id": f"TKT-{session_id[-8:]}",
        }

    return engine
