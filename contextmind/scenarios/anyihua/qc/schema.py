"""
安逸花外呼 · 任务一（QC）· ServiceSchema 定义

定义动作解析器（Action Parser）在质量检测任务中可调用的意图和槽位。
Schema 约束 LLM 只从预定义意图中选择，按规定格式填写槽位，
确保执行引擎 API 的调用与返回数据被正确解析。

设计原则（PyTOD 哲学）：
    执行引擎 API 只负责提供"事实数据"（get_*_data）；
    所有标签判断和语义推理均由 LLM（动作解析器 + 对话管理器）完成。
    这样做的好处：
      · 规则层仅做数值提取，不做主观判断，降低误报
      · LLM 负责语义层的理解，对"答非所问""不当告别"等模糊边界更准确
      · 引擎 API 可复用，schema 约束可独立迭代

五个质量标签（对应五个检测意图）：
    数据错误   ← check_credit_accuracy   → get_credit_data()
    重复询问   ← check_reply_repetition  → get_repetition_data()
    不当告别   ← check_farewell_context  → get_farewell_data()
    答非所问   ← check_topic_relevance   → get_topic_data()
    无标签命中 ← assign_quality_label    → (LLM 综合以上数据后直接判断)

槽位设计说明：
    evidence_* 槽位：从对话历史中提取的客观事实，由 Action Parser 填写
    quality_label：动作解析器综合所有 evidence_* 槽位后最终给出的标签
"""

from __future__ import annotations

from contextmind.modes.pytod import ServiceSchema, load_schema_from_dict

ANYIHUA_QC_SCHEMA_DICT = {
    "service_name": "AnYiHua_OutboundCall_QC",
    "description": (
        "安逸花外呼对话质量检测服务。"
        "通过调用执行引擎提供的事实数据 API，"
        "对坐席最终回复进行五分类质量标注。"
    ),
    "slots": [
        # ---- 信用额度检测槽位（数据错误检测）----
        {
            "name": "system_credit",
            "description": "CRM 系统记录的客户当前可提现额度（元），是判断数据错误的唯一客观参照",
            "is_categorical": False,
        },
        {
            "name": "credit_discrepancy",
            "description": "坐席回复中金额与系统额度的最大偏差（元）；偏差超过合理容差时为数据错误的强信号",
            "is_categorical": False,
        },
        {
            "name": "discrepant_amount_text",
            "description": "坐席回复中与系统额度偏差 > 300 元的具体金额文本",
            "is_categorical": False,
        },
        # ---- 重复询问检测槽位 ----
        {
            "name": "exact_repeat",
            "description": "坐席最终回复是否与历史某条坐席发言完全一致（True/False）",
            "is_categorical": True,
            "possible_values": ["True", "False"],
        },
        {
            "name": "repeat_count",
            "description": "坐席最终回复在历史发言中的精确出现次数",
            "is_categorical": False,
        },
        {
            "name": "similarity_score",
            "description": "坐席最终回复与历史发言的最高字符相似度（0.0~1.0）；高相似度为重复询问的参考信号",
            "is_categorical": False,
        },
        # ---- 不当告别检测槽位 ----
        {
            "name": "has_farewell",
            "description": "坐席最终回复是否含告别话术（True/False）",
            "is_categorical": True,
            "possible_values": ["True", "False"],
        },
        {
            "name": "unresolved_issue_count",
            "description": "用户最近消息中尚未被坐席解决的诉求数量（> 0 时应避免告别）",
            "is_categorical": False,
        },
        {
            "name": "last_unresolved_issue",
            "description": "最近一个未解决的用户诉求文本（供 LLM 判断是否真正未解决）",
            "is_categorical": False,
        },
        # ---- 答非所问检测槽位 ----
        {
            "name": "last_user_question",
            "description": "用户最近一条发言的完整内容（含问题/诉求）",
            "is_categorical": False,
        },
        {
            "name": "user_has_inquiry",
            "description": (
                "用户是否提出了需要坐席正面回应的实质性诉求（True/False）。"
                "不仅限于金额询问，也包含'在哪里''显示X''申请了Y'等账户相关问题"
            ),
            "is_categorical": True,
            "possible_values": ["True", "False"],
        },
        {
            "name": "topic_mismatch_hint",
            "description": "坐席回复与用户问题话题不匹配的初步信号（由引擎规则生成，供 LLM 参考）",
            "is_categorical": False,
        },
        # ---- 最终标签槽位 ----
        {
            "name": "quality_label",
            "description": (
                "最终质量标签。动作解析器依次核查数据错误→重复询问→不当告别→答非所问，"
                "第一个明确成立的即为结果；均不成立则为无标签命中"
            ),
            "is_categorical": True,
            "possible_values": ["数据错误", "重复询问", "不当告别", "答非所问", "无标签命中"],
        },
    ],
    "intents": [
        {
            "name": "check_credit_accuracy",
            "description": (
                "获取信用额度事实数据，检测坐席回复中引用的金额是否与系统额度一致。"
                "调用执行引擎 get_credit_data() API，"
                "返回 system_credit、credit_discrepancy、discrepant_amount_text。"
                "偏差超过合理容差时须标注为【数据错误】。"
                "注意：仅当坐席在陈述用户当前可提现额度时才检测；"
                "促销奖励额度、活动固定额度等不纳入检测范围"
            ),
            "required_slots": ["system_credit"],
            "optional_slots": ["credit_discrepancy", "discrepant_amount_text"],
        },
        {
            "name": "check_reply_repetition",
            "description": (
                "获取重复度量数据，检测坐席最终回复是否与历史发言高度重复。"
                "调用执行引擎 get_repetition_data() API，"
                "返回 exact_repeat、repeat_count、similarity_score。"
                "精确重复（exact_repeat=True）时须标注为【重复询问】；"
                "高相似度时由 LLM 进一步判断是否为实质重复"
            ),
            "required_slots": ["exact_repeat", "repeat_count"],
            "optional_slots": ["similarity_score"],
        },
        {
            "name": "check_farewell_context",
            "description": (
                "获取告别上下文数据，检测坐席是否在用户有未解决诉求时执行告别话术。"
                "调用执行引擎 get_farewell_data() API，"
                "返回 has_farewell、unresolved_issue_count、last_unresolved_issue。"
                "has_farewell=True 且 unresolved_issue_count > 0 时，"
                "由 LLM 判断未解决诉求是否真实，是则标注为【不当告别】"
            ),
            "required_slots": ["has_farewell", "unresolved_issue_count"],
            "optional_slots": ["last_unresolved_issue"],
        },
        {
            "name": "check_topic_relevance",
            "description": (
                "获取话题相关性数据，检测坐席回复是否切题。"
                "调用执行引擎 get_topic_data() API，"
                "返回 last_user_question、user_has_inquiry、topic_mismatch_hint。"
                "由 LLM 判断坐席回复是否与用户问题在同一话题范围内；"
                "仅当回复与问题完全无关时才标注为【答非所问】"
            ),
            "required_slots": ["last_user_question", "user_has_inquiry"],
            "optional_slots": ["topic_mismatch_hint"],
        },
        {
            "name": "assign_quality_label",
            "description": (
                "综合以上所有检测数据，给出最终质量标签。"
                "须按顺序依次核查：数据错误 → 重复询问 → 不当告别 → 答非所问；"
                "第一个明确成立的即为最终标签；均不成立则返回【无标签命中】。"
                "此意图不调用额外 API，由 LLM 基于已填充的槽位进行综合推理"
            ),
            "required_slots": ["quality_label"],
            "optional_slots": [
                "system_credit",
                "credit_discrepancy",
                "exact_repeat",
                "repeat_count",
                "has_farewell",
                "unresolved_issue_count",
                "last_user_question",
            ],
        },
    ],
}

ANYIHUA_QC_SCHEMA: ServiceSchema = load_schema_from_dict(ANYIHUA_QC_SCHEMA_DICT)
