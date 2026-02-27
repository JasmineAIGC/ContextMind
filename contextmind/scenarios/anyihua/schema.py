"""
安逸花外呼促活场景 · ServiceSchema 定义

定义 PyTOD Schema 驱动模式所需的意图列表和槽位列表。
Schema 用于约束动作解析器（Action Parser）的输出范围，
使 LLM 只从预定义意图中选择，并按规定格式填写槽位。

意图设计原则（基于 chat_test_100.json 数据分析）：
    - verify_identity:         开场核实（姓名+手机尾号）
    - explain_credit_limit:    告知额度（必须引用 query_account API）
    - explain_interest_rate:   解释利率/还款方式
    - calculate_repayment:     计算月还款额
    - explain_displayed_amount: 解释 APP 显示金额（防止答非所问）
    - handle_loan_dispute:     核实借款争议（防止不当告别）
    - guide_loan_operation:    引导借款操作（防止重复话术）
    - escalate_to_human:       转接人工（重复无效时使用）
    - say_goodbye:             礼貌告别（前置条件：问题已解决）

基于 docs/analysis/pytod-on-chat-test-100.md §4 实现。
"""

from __future__ import annotations

from contextmind.modes.pytod import ServiceSchema, load_schema_from_dict

# --------------------------------------------------------------------------- #
# Schema 字典定义
# --------------------------------------------------------------------------- #

ANYIHUA_SCHEMA_DICT = {
    "service_name": "AnYiHua_OutboundCall",
    "description": "安逸花外呼促活服务 - 核实身份、告知额度、解答疑问、推动借款",
    "slots": [
        {
            "name": "customer_name",
            "description": "客户姓名（先生/女士）",
            "is_categorical": False,
        },
        {
            "name": "phone_suffix",
            "description": "手机尾号（3-4 位，身份验证用）",
            "is_categorical": False,
        },
        {
            "name": "available_credit",
            "description": "当前实际可提现额度（元），来自 query_account API",
            "is_categorical": False,
        },
        {
            "name": "temp_credit",
            "description": "临时额度上限（元）",
            "is_categorical": False,
        },
        {
            "name": "temp_credit_status",
            "description": "临时额度有效性",
            "is_categorical": True,
            "possible_values": ["有效", "已过期", "无临时额度"],
        },
        {
            "name": "temp_expiry_days",
            "description": "临时额度剩余有效天数",
            "is_categorical": False,
        },
        {
            "name": "annual_rate_pct",
            "description": "年化利率（%，通常为 24）",
            "is_categorical": False,
        },
        {
            "name": "loan_count",
            "description": "当前未还清借款笔数",
            "is_categorical": False,
        },
        {
            "name": "last_loan_date",
            "description": "最近一次借款日期",
            "is_categorical": False,
        },
        {
            "name": "outstanding_amount",
            "description": "当前未还款金额（元）",
            "is_categorical": False,
        },
        {
            "name": "dispute_date",
            "description": "用户有异议的账单日期（如 '七月二十三号'）",
            "is_categorical": False,
        },
        {
            "name": "inquiry_amount",
            "description": "用户询问或质疑的具体金额数字（元）",
            "is_categorical": False,
        },
        {
            "name": "term_months",
            "description": "用户询问的分期期数（如 12）",
            "is_categorical": False,
        },
        {
            "name": "user_issue_resolved",
            "description": "用户核心诉求是否已解决（say_goodbye 前必须确认）",
            "is_categorical": True,
            "possible_values": ["是", "否", "进行中"],
        },
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
            "description": "解释利率和还款方式",
            "required_slots": ["customer_name", "annual_rate_pct"],
            "optional_slots": ["term_months"],
        },
        {
            "name": "calculate_repayment",
            "description": "计算指定金额和期数的月还款额和总手续费",
            "required_slots": ["customer_name", "available_credit", "annual_rate_pct"],
            "optional_slots": ["inquiry_amount", "term_months"],
        },
        {
            "name": "explain_displayed_amount",
            "description": (
                "解释 APP 显示金额的构成（用户质疑账户显示数字时使用）。"
                "需从 query_account 获取 available_credit 和 temp_credit，"
                "解释两者加和与 APP 显示的关系"
            ),
            "required_slots": ["customer_name", "available_credit", "inquiry_amount"],
            "optional_slots": ["temp_credit", "temp_credit_status"],
        },
        {
            "name": "handle_loan_dispute",
            "description": "核实用户争议的借款记录，调用 query_loan_records 获取事实数据",
            "required_slots": ["customer_name", "dispute_date"],
            "optional_slots": ["last_loan_date", "loan_count", "outstanding_amount"],
        },
        {
            "name": "guide_loan_operation",
            "description": (
                "引导用户在 APP 完成借款操作。"
                "检测到即将重复已说过的引导话术时，应先调用 check_repetition，"
                "若重复次数 >= 2 则改为 escalate_to_human"
            ),
            "required_slots": ["customer_name", "available_credit"],
            "optional_slots": [],
        },
        {
            "name": "escalate_to_human",
            "description": (
                "转接人工客服。"
                "触发条件：同一问题重复解释 2 次以上无效、用户明确投诉、"
                "复杂账单争议坐席无法独立解决"
            ),
            "required_slots": ["customer_name"],
            "optional_slots": ["dispute_date", "inquiry_amount"],
        },
        {
            "name": "say_goodbye",
            "description": (
                "礼貌告别。"
                "前置条件：必须先调用 check_farewell_preconditions，"
                "确认 can_farewell=True（即用户无未解决诉求）才可执行告别。"
                "否则应继续解决用户问题或转人工"
            ),
            "required_slots": ["user_issue_resolved"],
            "optional_slots": [],
        },
    ],
}

# --------------------------------------------------------------------------- #
# 加载为 ServiceSchema 实例（供 PyTODPromptBuilder 使用）
# --------------------------------------------------------------------------- #

ANYIHUA_SCHEMA: ServiceSchema = load_schema_from_dict(ANYIHUA_SCHEMA_DICT)
