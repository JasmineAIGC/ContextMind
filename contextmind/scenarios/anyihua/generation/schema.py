"""
安逸花外呼 · 任务二（Generation）· ServiceSchema 定义

定义动作解析器（Action Parser）可生成的意图列表和槽位列表。
Schema 约束 LLM 只从预定义意图中选择，按规定格式填写槽位，
防止动作解析器生成与 generation/engine.py 中 API 不匹配的调用。

槽位分类：
    用户提供槽位（Action Parser 从对话中提取）：
        customer_name, phone_suffix, dispute_date, inquiry_amount, term_months

    API 返回槽位（Action Parser 从 API 结果中读取，供对话管理器使用）：
        available_credit, temp_credit, temp_credit_status, temp_expiry_days,
        annual_rate_pct, loan_count, last_loan_date, outstanding_amount

意图设计原则（基于 chat_test_100.json 数据分析）：
    verify_identity         — 开场核实身份（用户提供姓名和手机尾号）
    explain_credit_limit    — 告知额度（调用 query_account API）
    explain_interest_rate   — 解释利率和还款方式（可调用 calculate_repayment API）
    calculate_repayment     — 计算月还款额（调用 calculate_repayment API）
    explain_displayed_amount — 解释 APP 显示金额（调用 query_account API）
    handle_loan_dispute     — 核实借款争议（调用 query_loan_records API）
    guide_loan_operation    — 引导借款操作（调用 get_agent_history API）
    escalate_to_human       — 转接人工（重复无效时使用）
    say_goodbye             — 礼貌告别（必须先调用 query_unresolved_issues API）
"""

from __future__ import annotations

from contextmind.modes.pytod import ServiceSchema, load_schema_from_dict

ANYIHUA_SCHEMA_DICT = {
    "service_name": "AnYiHua_OutboundCall_Generation",
    "description": "安逸花外呼促活服务 - 核实身份、告知额度、解答疑问、推动借款",
    "slots": [
        # ---- 用户提供槽位 ----
        {"name": "customer_name", "description": "客户姓名（先生/女士）", "is_categorical": False},
        {"name": "phone_suffix", "description": "手机尾号（3-4 位，身份验证用）", "is_categorical": False},
        {
            "name": "dispute_date",
            "description": "用户有异议的账单日期（如 '七月二十三号'）",
            "is_categorical": False,
        },
        {
            "name": "inquiry_amount",
            "description": "用户询问或质疑的具体金额（元）",
            "is_categorical": False,
        },
        {"name": "term_months", "description": "用户询问的分期期数（如 12）", "is_categorical": False},
        # ---- API 返回槽位（由 query_account / calculate_repayment 填充）----
        {
            "name": "available_credit",
            "description": "当前实际可提现额度（元）——由 query_account API 返回，禁止估算",
            "is_categorical": False,
        },
        {"name": "temp_credit", "description": "临时额度上限（元）", "is_categorical": False},
        {
            "name": "temp_credit_status",
            "description": "临时额度有效性",
            "is_categorical": True,
            "possible_values": ["有效", "已过期", "无临时额度"],
        },
        {"name": "temp_expiry_days", "description": "临时额度剩余有效天数", "is_categorical": False},
        {"name": "annual_rate_pct", "description": "年化利率（%，通常为 24）", "is_categorical": False},
        {"name": "loan_count", "description": "当前未还清借款笔数", "is_categorical": False},
        {"name": "last_loan_date", "description": "最近一次借款日期", "is_categorical": False},
        {"name": "outstanding_amount", "description": "当前未还款金额（元）", "is_categorical": False},
    ],
    "intents": [
        {
            "name": "verify_identity",
            "description": "开场身份核实：确认客户姓名和手机尾号",
            "required_slots": ["customer_name"],
            "optional_slots": ["phone_suffix"],
        },
        {
            "name": "explain_credit_limit",
            "description": (
                "告知额度情况。"
                "必须先调用 query_account API 获取 available_credit，"
                "不得自行计算或估算金额（防止数据错误）"
            ),
            "required_slots": ["customer_name", "available_credit"],
            "optional_slots": ["temp_credit", "temp_credit_status", "temp_expiry_days"],
        },
        {
            "name": "explain_interest_rate",
            "description": "解释利率和还款方式，可调用 calculate_repayment API 获取具体数据",
            "required_slots": ["customer_name", "annual_rate_pct"],
            "optional_slots": ["term_months"],
        },
        {
            "name": "calculate_repayment",
            "description": (
                "计算指定金额和期数的月还款额。"
                "调用 calculate_repayment API，传入用户指定的 amount 和 months"
            ),
            "required_slots": ["customer_name"],
            "optional_slots": ["inquiry_amount", "term_months"],
        },
        {
            "name": "explain_displayed_amount",
            "description": (
                "解释 APP 显示金额的构成（用户质疑账户显示数字时使用）。"
                "调用 query_account 获取 available_credit 和 temp_credit，"
                "结合用户提到的 inquiry_amount 进行说明"
            ),
            "required_slots": ["customer_name", "inquiry_amount"],
            "optional_slots": ["available_credit", "temp_credit", "temp_credit_status"],
        },
        {
            "name": "handle_loan_dispute",
            "description": "核实用户争议的借款记录，调用 query_loan_records API 获取事实数据",
            "required_slots": ["customer_name", "dispute_date"],
            "optional_slots": ["last_loan_date", "loan_count", "outstanding_amount"],
        },
        {
            "name": "guide_loan_operation",
            "description": (
                "引导用户在 APP 完成借款操作。"
                "先调用 query_account 获取 available_credit，再调用 get_agent_history API；"
                "历史中同一话术出现 2 次以上时改为 escalate_to_human"
            ),
            "required_slots": ["customer_name"],
            "optional_slots": ["available_credit"],
        },
        {
            "name": "escalate_to_human",
            "description": (
                "转接人工客服。"
                "触发条件：同一问题重复解释 2 次以上无效、用户明确投诉、复杂账单争议"
            ),
            "required_slots": ["customer_name"],
            "optional_slots": ["dispute_date", "inquiry_amount"],
        },
        {
            "name": "say_goodbye",
            "description": (
                "礼貌告别。"
                "必须先调用 query_unresolved_issues API，"
                "确认 issue_count=0（无未解决诉求）才可执行告别，否则继续解决用户问题或转人工"
            ),
            "required_slots": ["customer_name"],
            "optional_slots": [],
        },
    ],
}

ANYIHUA_SCHEMA: ServiceSchema = load_schema_from_dict(ANYIHUA_SCHEMA_DICT)
