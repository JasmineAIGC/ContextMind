"""
安逸花外呼 chat_test_100.json → SGD 格式转换器

将安逸花外呼场景的真实通话数据转换为 Google SGD
（Schema-Guided Dialogue）格式，以适配 PyTOD 算法。

SGD 格式参考：
    https://github.com/google-research-datasets/dstc8-schema-guided-dialogue

ml-pytod 参考：
    https://github.com/apple/ml-pytod

----------------------------------------------------------------------
chat_test_100.json 与 SGD 的字段映射
----------------------------------------------------------------------

可直接映射（100% 可靠）：
  session_id          → dialogue_id
  "坐席：..." 前缀     → speaker = "SYSTEM"
  "用户：..." 前缀     → speaker = "USER"
  对话历史正文         → utterance

高可靠（CRM 结构化数据，≈ 99% 准确）：
  slot_values          → 从 用户信息 字段（parse_user_info）提取 CRM 数据，
                         数值本身完全可信（来自真实系统），仅注入时机可能有偏差

规则推断（近似，约 50–70% 准确）：
  active_intent        → 关键词匹配安逸花意图体系（USER 轮用用户自身话语推断，
                         并向后传递；而非继承 SYSTEM 意图，后者会产生大量错误标注）
  requested_slots      → 用户疑问句中检测槽位请求
  actions              → 从 intent 映射常用对话行为
  service_call         → 从 active_intent 映射 API 方法名（仅当 intent 正确时才正确）
  service_results      → 从 parse_user_info 解析的 CRM 数据

LLM 增强模式（--use-llm 启用，使用 contextmind/infra/llm_client.py）：
  active_intent        → 结合上下文窗口进行语义意图识别（更准确）
  requested_slots      → 从用户疑问句中语义提取正在询问的槽位
  actions (USER)       → 语义识别用户主动告知的信息槽及值
  service_call params  → 从坐席话语中提取 API 调用参数（补充规则层漏失的参数）

注意：规则推断字段属于弱标注近似数据，适合快速原型和 Generation 任务评估；
      生产环境建议使用 --use-llm 启用 LLM 语义补全以获得更准确的标注。

扩展（SGD 无对应，ContextMind 专用）：
  用户信息             → metadata.user_info_raw + metadata.user_info_parsed
  坐席回复             → metadata.reference_response
  人工校验             → metadata.qc_label

----------------------------------------------------------------------
安逸花意图体系（与 contextmind/scenarios/anyihua/generation/schema.py 对齐）
----------------------------------------------------------------------

  verify_identity        — 核实用户身份
  explain_credit_limit   — 告知额度情况
  explain_interest_rate  — 解释利率/还款方式
  calculate_repayment    — 计算月还款额
  explain_displayed_amount — 解释 APP 显示金额
  handle_loan_dispute    — 核实借款记录争议
  guide_loan_operation   — 引导借款操作
  escalate_to_human      — 转接人工
  say_goodbye            — 礼貌告别
  general_inquiry        — 通用询问（无法精确匹配时的默认值）
"""

from __future__ import annotations

import json
import logging
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from contextmind.scenarios.anyihua.utils import parse_user_info

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

#: SGD 服务名称（遵循 "<domain>_<number>" 命名规范）
SERVICE_NAME = "AnYiHua_1"

#: chat_test_100.json 中的发言者前缀
_AGENT_PREFIX = "坐席："
_USER_PREFIX = "用户："

# ---------------------------------------------------------------------------
# 意图推断规则（关键词 → 安逸花意图）
# ---------------------------------------------------------------------------
# 按优先级从高到低排列，第一个匹配的规则生效。
# 规则覆盖顺序重要：dispute（借款争议）优先于 credit_limit（额度查询）

_INTENT_RULES: List[Tuple[List[str], str]] = [
    # 1. 身份核实
    (["本人", "核实", "您是谁", "是您本人", "确认一下", "您这边是", "姓名", "手机尾号"], "verify_identity"),
    # 2. 借款记录争议（优先于额度查询，因"借款"词在两者中都有）
    (["没有借款", "没借过", "没贷过", "异常", "怎么会有", "这笔借款", "这笔贷款",
      "七月", "八月", "九月", "十月", "号的这一笔"], "handle_loan_dispute"),
    # 3. 额度查询
    (["额度", "提额", "提现额", "可以提", "多少额", "额度是多少"], "explain_credit_limit"),
    # 4. 利率/还款方式
    (["利率", "利息", "还款", "分期", "手续费", "月还", "每月还"], "explain_interest_rate"),
    # 5. 计算月还款
    (["借一万", "借多少", "算一下", "计算", "还多少钱"], "calculate_repayment"),
    # 6. APP 显示金额解释
    (["显示", "APP", "页面", "上面写", "显示的", "看到的"], "explain_displayed_amount"),
    # 7. 引导借款操作
    (["怎么借", "如何提现", "操作", "在哪借", "步骤", "怎么用"], "guide_loan_operation"),
    # 8. 转人工
    (["转人工", "人工客服", "投诉", "举报", "上级"], "escalate_to_human"),
    # 9. 告别
    (["再见", "不打扰", "挂电话", "拜拜", "祝您", "感谢来电", "有需要再联系"], "say_goodbye"),
]

# 意图 → 主要对应 CRM API（供 service_call 填充）
_INTENT_TO_API: Dict[str, str] = {
    "verify_identity": "verify_customer",
    "explain_credit_limit": "query_account",
    "explain_interest_rate": "calculate_repayment",
    "calculate_repayment": "calculate_repayment",
    "explain_displayed_amount": "query_account",
    "handle_loan_dispute": "query_loan_records",
    "guide_loan_operation": "query_account",
    "escalate_to_human": None,
    "say_goodbye": "query_unresolved_issues",
    "general_inquiry": None,
}

# 意图 → 主要 SYSTEM 动作类型
_INTENT_TO_SYSTEM_ACT: Dict[str, str] = {
    "verify_identity": "REQUEST",
    "explain_credit_limit": "INFORM",
    "explain_interest_rate": "INFORM",
    "calculate_repayment": "INFORM",
    "explain_displayed_amount": "INFORM",
    "handle_loan_dispute": "INFORM",
    "guide_loan_operation": "INFORM",
    "escalate_to_human": "INFORM",
    "say_goodbye": "GOODBYE",
    "general_inquiry": "INFORM",
}

# 意图 → 关键槽位（供 slot_values 初始化）
_INTENT_TO_SLOTS: Dict[str, List[str]] = {
    "verify_identity": ["customer_name"],
    "explain_credit_limit": ["customer_name", "available_credit"],
    "explain_interest_rate": ["customer_name", "annual_rate_pct"],
    "calculate_repayment": ["customer_name"],
    "explain_displayed_amount": ["customer_name", "available_credit", "temp_credit"],
    "handle_loan_dispute": ["customer_name", "dispute_date"],
    "guide_loan_operation": ["customer_name", "available_credit"],
    "escalate_to_human": ["customer_name"],
    "say_goodbye": ["customer_name"],
    "general_inquiry": ["customer_name"],
}


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _split_utterance(raw: str) -> Tuple[str, str]:
    """
    将 "坐席：内容" / "用户：内容" 拆分为 (speaker_tag, utterance)。

    返回:
        ("SYSTEM", utterance) 或 ("USER", utterance)

    若无法识别前缀，默认返回 ("USER", raw)。
    """
    if raw.startswith(_AGENT_PREFIX):
        return "SYSTEM", raw[len(_AGENT_PREFIX):]
    if raw.startswith(_USER_PREFIX):
        return "USER", raw[len(_USER_PREFIX):]
    return "USER", raw


def _infer_intent(utterance: str, speaker: str) -> str:
    """
    根据关键词规则推断当前轮的意图。

    仅对 SYSTEM 轮推断意图（SYSTEM 轮反映系统正在执行的业务意图）；
    USER 轮的 active_intent 表示用户期望完成的任务意图，
    此处用同一规则检测用户话语中的意图信号。

    参数:
        utterance: 发言文本
        speaker:   "USER" 或 "SYSTEM"

    返回:
        意图名称字符串（如 "verify_identity"），默认为 "general_inquiry"
    """
    for keywords, intent in _INTENT_RULES:
        for kw in keywords:
            if kw in utterance:
                return intent
    return "general_inquiry"


def _extract_requested_slots(utterance: str) -> List[str]:
    """
    从用户发言中提取正在询问的槽位。

    通过检测疑问词 + 关键词的组合来识别用户的槽位请求。

    参数:
        utterance: 用户发言文本

    返回:
        槽位名称列表（可能为空）
    """
    requested: List[str] = []
    question_words = ["多少", "几", "什么", "哪", "怎么", "如何", "能不能", "可以吗", "是多少"]
    is_question = any(q in utterance for q in question_words)

    if not is_question:
        return []

    slot_keyword_map = [
        (["额度", "提现", "多少钱"], "available_credit"),
        (["利率", "利息"], "annual_rate_pct"),
        (["还款", "每月还", "月供"], "monthly_payment"),
        (["手续费", "费用"], "annual_rate_pct"),
        (["账单", "账单日"], "billing_day"),
        (["还款日"], "repayment_date"),
    ]

    for keywords, slot_name in slot_keyword_map:
        if any(kw in utterance for kw in keywords):
            requested.append(slot_name)

    return requested


def _build_crm_slot_values(
    user_info: Dict[str, Any], active_intent: str
) -> Dict[str, List[str]]:
    """
    根据意图从 CRM 用户信息中提取相关槽值。

    SGD 的 slot_values 格式为 {slot_name: [value_str]}，
    此处从 parse_user_info 解析结果中提取与当前意图相关的字段。

    参数:
        user_info:     parse_user_info() 返回的字典
        active_intent: 当前激活的意图名称

    返回:
        SGD 格式的 slot_values 字典
    """
    slot_values: Dict[str, List[str]] = {}

    # 始终包含客户姓名
    if user_info.get("customer_name"):
        slot_values["customer_name"] = [user_info["customer_name"]]

    # 按意图选择相关字段
    if active_intent in ("explain_credit_limit", "guide_loan_operation", "explain_displayed_amount"):
        if user_info.get("available_credit"):
            slot_values["available_credit"] = [str(user_info["available_credit"])]
        if user_info.get("temp_credit"):
            slot_values["temp_credit"] = [str(user_info["temp_credit"])]
        if user_info.get("temp_expired") is not None:
            status = "已过期" if user_info["temp_expired"] else "有效"
            slot_values["temp_credit_status"] = [status]
        if user_info.get("temp_active_days"):
            slot_values["temp_expiry_days"] = [str(user_info["temp_active_days"])]

    if active_intent in ("explain_interest_rate", "calculate_repayment"):
        if user_info.get("annual_rate_pct"):
            slot_values["annual_rate_pct"] = [str(user_info["annual_rate_pct"])]

    if active_intent == "handle_loan_dispute":
        if user_info.get("last_loan_date"):
            slot_values["last_loan_date"] = [user_info["last_loan_date"]]
        if user_info.get("loan_count") is not None:
            slot_values["loan_count"] = [str(user_info["loan_count"])]
        if user_info.get("outstanding_amount") is not None:
            slot_values["outstanding_amount"] = [str(user_info["outstanding_amount"])]

    if active_intent == "verify_identity":
        if user_info.get("phone_suffix"):
            slot_values["phone_suffix"] = [user_info["phone_suffix"]]

    return slot_values


def _build_service_call(active_intent: str, slot_values: Dict[str, List[str]]) -> Optional[Dict]:
    """
    根据意图构建 SGD service_call 字段（模拟系统调用的 API）。

    参数:
        active_intent: 当前意图
        slot_values:   已知槽值

    返回:
        SGD service_call 字典，或 None（不需要 API 调用时）
    """
    api = _INTENT_TO_API.get(active_intent)
    if not api:
        return None

    # 从 slot_values 提取 API 参数
    parameters: Dict[str, str] = {}
    if api == "verify_customer":
        if "customer_name" in slot_values:
            parameters["name"] = slot_values["customer_name"][0]
        if "phone_suffix" in slot_values:
            parameters["phone_suffix"] = slot_values["phone_suffix"][0]
    elif api == "calculate_repayment":
        if "inquiry_amount" in slot_values:
            parameters["amount"] = slot_values["inquiry_amount"][0]
        if "term_months" in slot_values:
            parameters["months"] = slot_values["term_months"][0]

    return {"method": api, "parameters": parameters}


def _build_service_results(
    active_intent: str,
    user_info: Dict[str, Any],
) -> List[Dict[str, str]]:
    """
    根据意图从 CRM 数据构建 SGD service_results 字段。

    service_results 模拟 API 返回的结构化数据，
    每个结果是一个 {slot_name: value_str} 字典。

    参数:
        active_intent: 当前意图
        user_info:     parse_user_info() 返回的字典

    返回:
        service_results 列表（通常只有 1 条）
    """
    result: Dict[str, str] = {}
    api = _INTENT_TO_API.get(active_intent)

    if api == "verify_customer":
        if user_info.get("customer_name"):
            result["customer_name"] = user_info["customer_name"]
        if user_info.get("phone_suffix"):
            result["phone_suffix"] = user_info["phone_suffix"]
        result["identity_confirmed"] = "true"  # 默认已核实（真实通话中坐席已确认）

    elif api == "query_account":
        if user_info.get("available_credit"):
            result["available_credit"] = str(user_info["available_credit"])
        if user_info.get("temp_credit"):
            result["temp_credit"] = str(user_info["temp_credit"])
        if user_info.get("annual_rate_pct"):
            result["annual_rate_pct"] = str(user_info["annual_rate_pct"])
        if user_info.get("bound_bank"):
            result["bound_bank"] = user_info["bound_bank"]
        if user_info.get("billing_day"):
            result["billing_day"] = str(user_info["billing_day"])
        result["temp_credit_status"] = (
            "已过期" if user_info.get("temp_expired") else "有效"
        )
        if user_info.get("temp_active_days"):
            result["temp_expiry_days"] = str(user_info["temp_active_days"])

    elif api == "query_loan_records":
        if user_info.get("last_loan_date"):
            result["last_loan_date"] = user_info["last_loan_date"]
        if user_info.get("loan_count") is not None:
            result["loan_count"] = str(user_info["loan_count"])
        if user_info.get("outstanding_amount") is not None:
            result["outstanding_amount"] = str(user_info["outstanding_amount"])
        result["loan_outstanding"] = str(user_info.get("loan_outstanding", False)).lower()

    elif api == "query_unresolved_issues":
        result["issue_count"] = "0"

    return [result] if result else []


# ---------------------------------------------------------------------------
# SGD Schema 生成
# ---------------------------------------------------------------------------

def build_anyihua_sgd_schema() -> List[Dict]:
    """
    生成安逸花外呼场景的 SGD schema.json 内容。

    与 contextmind/scenarios/anyihua/generation/schema.py 中的
    ANYIHUA_SCHEMA_DICT 保持对齐，但使用 SGD 的 optional_slots（字典格式）
    而非 PyTOD 的 optional_slots（列表格式）。

    返回:
        SGD schema 列表（每个服务一个字典）
    """
    return [
        {
            "service_name": SERVICE_NAME,
            "description": (
                "安逸花外呼促活服务。坐席代表安逸花/马上消费金融主动致电老用户，"
                "目标是激活用户闲置的借款额度。"
                "标准流程：核实身份 → 告知额度 → 解答疑问 → 引导借款 → 礼貌告别。"
            ),
            "slots": [
                # ---- 用户提供槽位 ----
                {
                    "name": "customer_name",
                    "description": "客户姓名（如'高先生'、'杨女士'）",
                    "is_categorical": False,
                    "possible_values": [],
                },
                {
                    "name": "phone_suffix",
                    "description": "手机尾号（3–4 位数字，用于身份核实）",
                    "is_categorical": False,
                    "possible_values": [],
                },
                {
                    "name": "dispute_date",
                    "description": "用户质疑的借款日期（如'七月二十三号'）",
                    "is_categorical": False,
                    "possible_values": [],
                },
                {
                    "name": "inquiry_amount",
                    "description": "用户询问或质疑的金额（元）",
                    "is_categorical": False,
                    "possible_values": [],
                },
                {
                    "name": "term_months",
                    "description": "用户询问的分期期数（如 12）",
                    "is_categorical": False,
                    "possible_values": [],
                },
                # ---- API 返回槽位 ----
                {
                    "name": "identity_confirmed",
                    "description": "身份是否已核实（由 verify_customer API 返回）",
                    "is_categorical": True,
                    "possible_values": ["true", "false"],
                },
                {
                    "name": "available_credit",
                    "description": "当前实际可提现额度（元，由 query_account API 返回）",
                    "is_categorical": False,
                    "possible_values": [],
                },
                {
                    "name": "temp_credit",
                    "description": "临时额度上限（元）",
                    "is_categorical": False,
                    "possible_values": [],
                },
                {
                    "name": "temp_credit_status",
                    "description": "临时额度是否有效",
                    "is_categorical": True,
                    "possible_values": ["有效", "已过期", "无临时额度"],
                },
                {
                    "name": "temp_expiry_days",
                    "description": "临时额度剩余有效天数",
                    "is_categorical": False,
                    "possible_values": [],
                },
                {
                    "name": "annual_rate_pct",
                    "description": "年化利率（%）",
                    "is_categorical": False,
                    "possible_values": [],
                },
                {
                    "name": "loan_count",
                    "description": "当前未还清借款笔数",
                    "is_categorical": False,
                    "possible_values": [],
                },
                {
                    "name": "last_loan_date",
                    "description": "最近一次借款日期（中文格式）",
                    "is_categorical": False,
                    "possible_values": [],
                },
                {
                    "name": "outstanding_amount",
                    "description": "当前未还款金额（元）",
                    "is_categorical": False,
                    "possible_values": [],
                },
                {
                    "name": "billing_day",
                    "description": "账单日（每月几号）",
                    "is_categorical": False,
                    "possible_values": [],
                },
            ],
            "intents": [
                {
                    "name": "verify_identity",
                    "description": "开场身份核实：确认来电者是账户本人",
                    "is_transactional": False,
                    "required_slots": ["customer_name"],
                    "optional_slots": {"phone_suffix": ""},
                    "result_slots": ["identity_confirmed"],
                },
                {
                    "name": "explain_credit_limit",
                    "description": "告知额度情况（必须先调用 query_account API）",
                    "is_transactional": False,
                    "required_slots": ["customer_name", "available_credit"],
                    "optional_slots": {
                        "temp_credit": "",
                        "temp_credit_status": "",
                        "temp_expiry_days": "",
                    },
                    "result_slots": ["available_credit", "temp_credit", "temp_credit_status"],
                },
                {
                    "name": "explain_interest_rate",
                    "description": "解释利率和还款方式",
                    "is_transactional": False,
                    "required_slots": ["customer_name", "annual_rate_pct"],
                    "optional_slots": {"term_months": ""},
                    "result_slots": ["annual_rate_pct"],
                },
                {
                    "name": "calculate_repayment",
                    "description": "计算指定金额和期数的月还款额",
                    "is_transactional": False,
                    "required_slots": ["customer_name"],
                    "optional_slots": {"inquiry_amount": "", "term_months": ""},
                    "result_slots": [],
                },
                {
                    "name": "explain_displayed_amount",
                    "description": "解释 APP 显示金额的构成",
                    "is_transactional": False,
                    "required_slots": ["customer_name", "inquiry_amount"],
                    "optional_slots": {
                        "available_credit": "",
                        "temp_credit": "",
                        "temp_credit_status": "",
                    },
                    "result_slots": ["available_credit", "temp_credit"],
                },
                {
                    "name": "handle_loan_dispute",
                    "description": "核实用户争议的借款记录",
                    "is_transactional": False,
                    "required_slots": ["customer_name", "dispute_date"],
                    "optional_slots": {
                        "last_loan_date": "",
                        "loan_count": "",
                        "outstanding_amount": "",
                    },
                    "result_slots": ["last_loan_date", "loan_count", "outstanding_amount"],
                },
                {
                    "name": "guide_loan_operation",
                    "description": "引导用户在 APP 完成借款操作",
                    "is_transactional": False,
                    "required_slots": ["customer_name"],
                    "optional_slots": {"available_credit": ""},
                    "result_slots": [],
                },
                {
                    "name": "escalate_to_human",
                    "description": "转接人工客服",
                    "is_transactional": True,
                    "required_slots": ["customer_name"],
                    "optional_slots": {"dispute_date": "", "inquiry_amount": ""},
                    "result_slots": [],
                },
                {
                    "name": "say_goodbye",
                    "description": "礼貌告别（必须先确认无未解决诉求）",
                    "is_transactional": False,
                    "required_slots": ["customer_name"],
                    "optional_slots": {},
                    "result_slots": [],
                },
                {
                    "name": "general_inquiry",
                    "description": "通用询问（无法精确匹配其他意图时的默认意图）",
                    "is_transactional": False,
                    "required_slots": [],
                    "optional_slots": {},
                    "result_slots": [],
                },
            ],
        }
    ]


# ---------------------------------------------------------------------------
# 主转换器
# ---------------------------------------------------------------------------


class ChatTestToSGDConverter:
    """
    将 chat_test_100.json 转换为 SGD 格式的转换器。

    转换策略：
    1. `dialogue_id` / `speaker` / `utterance` 直接映射
    2. `active_intent` 通过关键词规则推断
    3. `slot_values` / `service_results` 从 `用户信息` 字段（parse_user_info）提取
    4. `requested_slots` 通过疑问句检测
    5. `service_call` 从 `active_intent` 映射 API 方法名
    6. 扩展元数据存入 `metadata`（非标准 SGD 字段，供 ContextMind 内部使用）

    使用示例::

        converter = ChatTestToSGDConverter()
        schema = converter.build_schema()
        dialogues = converter.convert(input_path="resources/data/chat_test_100.json")
        # 写入 SGD 目录
        converter.save(
            dialogues, schema,
            output_dir="data/anyihua_sgd",
            dialogues_per_file=1000,
        )
    """

    def __init__(self, llm_enricher: Optional[Any] = None) -> None:
        """
        初始化转换器。

        参数:
            llm_enricher: 可选的 LLMEnricher 实例（来自 llm_enricher.py）。
                          提供时，规则层的近似推断字段将被 LLM 语义补全覆盖：
                          active_intent、requested_slots、USER actions、service_call params。
                          未提供时（默认），使用纯规则层（适合快速原型）。
        """
        self._llm_enricher = llm_enricher

    # ------------------------------------------------------------------ #
    # 公开接口
    # ------------------------------------------------------------------ #

    def build_schema(self) -> List[Dict]:
        """生成安逸花外呼场景的 SGD schema.json。"""
        return build_anyihua_sgd_schema()

    def convert(
        self,
        input_path: str,
        limit: Optional[int] = None,
    ) -> List[Dict]:
        """
        将 chat_test_100.json 转换为 SGD 格式的对话列表。

        参数:
            input_path: chat_test_100.json 文件路径
            limit:      最多转换的记录数（None 表示全部）

        返回:
            SGD 格式的对话字典列表
        """
        with open(input_path, encoding="utf-8") as f:
            raw_data: List[Dict] = json.load(f)

        if limit is not None:
            raw_data = raw_data[:limit]

        sgd_dialogues: List[Dict] = []
        for idx, record in enumerate(raw_data):
            try:
                sgd_dialogue = self._convert_record(record, idx)
                # LLM 增强：在规则层结果基础上进行语义补全
                if self._llm_enricher is not None:
                    try:
                        sgd_dialogue = self._llm_enricher.enrich(sgd_dialogue)
                    except Exception as llm_exc:
                        logger.warning(
                            f"LLM 补全失败（session={sgd_dialogue.get('dialogue_id', '?')}），"
                            f"使用规则层结果: {llm_exc}"
                        )
                sgd_dialogues.append(sgd_dialogue)
            except Exception as exc:
                logger.warning(
                    f"跳过第 {idx} 条记录（session_id={record.get('session_id', '?')}）: {exc}"
                )

        logger.info(f"共转换 {len(sgd_dialogues)} / {len(raw_data)} 条记录")
        return sgd_dialogues

    def save(
        self,
        dialogues: List[Dict],
        schema: List[Dict],
        output_dir: str,
        dialogues_per_file: int = 1000,
    ) -> Dict[str, Any]:
        """
        将 SGD 格式数据写入目录（schema.json + dialogues_*.json）。

        参数:
            dialogues:          SGD 对话列表（由 convert() 返回）
            schema:             SGD schema（由 build_schema() 返回）
            output_dir:         输出目录路径
            dialogues_per_file: 每个 dialogues_*.json 最多包含的对话数

        返回:
            包含统计信息的字典
        """
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        # 写 schema.json
        schema_path = out_path / "schema.json"
        schema_path.write_text(
            json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # 写 dialogues_*.json（分块）
        file_count = 0
        total_turns = 0
        for start in range(0, len(dialogues), dialogues_per_file):
            chunk = dialogues[start : start + dialogues_per_file]
            file_count += 1
            file_name = f"dialogues_{file_count:03d}.json"
            (out_path / file_name).write_text(
                json.dumps(chunk, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            for dlg in chunk:
                total_turns += len(dlg["turns"])

        summary = {
            "output_dir": str(out_path),
            "dialogues": len(dialogues),
            "turns": total_turns,
            "services": 1,
            "dialogue_files": file_count,
        }

        # 写汇总文件
        summary_path = out_path / "conversion_summary.json"
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        logger.info(
            f"SGD 数据已写入 {out_path}: "
            f"{summary['dialogues']} 对话, {summary['turns']} 轮次, "
            f"{summary['dialogue_files']} 文件"
        )
        return summary

    # ------------------------------------------------------------------ #
    def convert_record(self, record: Dict, idx: int = 0) -> Dict:
        """
        将单条 chat_test_100.json 记录转换为 SGD dialogue 字典。

        这是 :meth:`_convert_record` 的公共包装，供外部评测器和工具直接调用，
        无需依赖私有方法约定。

        参数:
            record: 原始对话记录（含 session_id / 用户信息 / 对话历史 等字段）
            idx:    记录索引（用于生成 dialogue_id 的备用值，默认为 0）

        返回:
            SGD 格式的 dialogue 字典
        """
        return self._convert_record(record, idx)

    # 内部转换逻辑
    # ------------------------------------------------------------------ #

    def _convert_record(self, record: Dict, idx: int) -> Dict:
        """
        将单条 chat_test_100.json 记录转换为 SGD dialogue 字典。

        参数:
            record: 原始记录（含 session_id / 用户信息 / 对话历史 / 坐席回复 / 人工校验）
            idx:    记录索引（用于生成 dialogue_id fallback）

        返回:
            SGD 格式的 dialogue 字典
        """
        dialogue_id = record.get("session_id") or str(idx)

        # 解析用户信息（CRM 数据）
        raw_user_info = record.get("用户信息", "")
        try:
            user_info = parse_user_info(raw_user_info)
        except Exception as exc:
            logger.debug(f"parse_user_info 失败（session={dialogue_id}）: {exc}")
            user_info = {}

        # 解析对话历史
        history: List[str] = record.get("对话历史", [])

        # 附加当前轮的坐席回复（视为对话历史的最后一个 SYSTEM turn）
        reference_response = record.get("坐席回复", "")

        # 构建完整对话序列（历史 + 参考坐席回复）
        # 注意：参考回复已含标签，作为最后一个系统轮追加
        full_turns_raw = list(history)
        if reference_response:
            full_turns_raw.append(f"{_AGENT_PREFIX}{reference_response}")

        # 转换为 SGD turns
        sgd_turns: List[Dict] = []
        cumulative_slot_values: Dict[str, List[str]] = {}
        # 分别跟踪用户侧和系统侧的意图上下文
        prev_user_intent = "general_inquiry"

        for raw_turn in full_turns_raw:
            speaker, utterance = _split_utterance(raw_turn)

            # 推断当前话语的意图
            intent = _infer_intent(utterance, speaker)

            if speaker == "USER":
                # SGD 规范：state.active_intent 表示用户正在追求的任务意图。
                # 策略：
                #   1. 若用户话语中能检测到明确意图（非 general_inquiry），则更新用户意图状态。
                #   2. 若用户话语无法识别（短语、回应词），则沿用用户上一个已知意图（
                #      而非系统意图——系统正在讲什么与用户想做什么可能不同）。
                # 初始状态：prev_user_intent = "general_inquiry"；第一轮用户回应短句时
                # active_intent 为 "general_inquiry"，直到用户话语中出现可识别的意图信号。
                # 这比直接继承 SYSTEM 意图更准确：系统可能在告知额度，
                # 但用户真正关心的却是借款争议（handle_loan_dispute）。
                if intent != "general_inquiry":
                    prev_user_intent = intent
                active_intent = prev_user_intent
            else:
                # SYSTEM turn：用系统本轮推断出的意图（表示系统正在执行的业务动作）
                active_intent = intent

            # 提取/更新槽值
            if speaker == "SYSTEM":
                new_slots = _build_crm_slot_values(user_info, active_intent)
                cumulative_slot_values.update(new_slots)

            # USER 轮：提取请求槽位
            requested_slots = (
                _extract_requested_slots(utterance) if speaker == "USER" else []
            )

            # 构建 frame
            if speaker == "USER":
                frame = self._build_user_frame(
                    active_intent, cumulative_slot_values, requested_slots, utterance
                )
            else:
                frame = self._build_system_frame(
                    active_intent, cumulative_slot_values, user_info
                )

            sgd_turns.append({
                "speaker": speaker,
                "utterance": utterance,
                "frames": [frame],
            })

        # 构建扩展元数据（非标准 SGD，供 ContextMind 内部使用）
        metadata = {
            "user_info_raw": raw_user_info,
            "user_info_parsed": {
                k: v for k, v in user_info.items()
                if k not in ("raw_fields",) and v is not None
            },
            "reference_response": reference_response,
            "qc_label": record.get("人工校验", ""),
        }

        return {
            "dialogue_id": dialogue_id,
            "services": [SERVICE_NAME],
            "turns": sgd_turns,
            "metadata": metadata,  # 扩展字段
        }

    def _build_user_frame(
        self,
        active_intent: str,
        cumulative_slot_values: Dict[str, List[str]],
        requested_slots: List[str],
        utterance: str,
    ) -> Dict:
        """构建 USER turn 的 SGD frame。

        SGD 规范：USER frame 包含 service / slots / state / actions。
        其中 slots 为字符级标注（本实现留空），state 包含 active_intent / requested_slots / slot_values。
        """
        # 从话语中提取显式信息槽（如用户提到姓名/尾号/日期）
        actions = self._extract_user_actions(utterance, cumulative_slot_values)

        return {
            "service": SERVICE_NAME,
            "slots": [],  # SGD 规范要求，字符级标注，本实现留空
            "state": {
                "active_intent": active_intent,
                "requested_slots": requested_slots,
                "slot_values": dict(cumulative_slot_values),
            },
            "actions": actions,
        }

    def _build_system_frame(
        self,
        active_intent: str,
        cumulative_slot_values: Dict[str, List[str]],
        user_info: Dict[str, Any],
    ) -> Dict:
        """构建 SYSTEM turn 的 SGD frame。

        SGD 规范：SYSTEM frame 包含 service / slots / actions，
        仅当实际发生 API 调用时才包含 service_call / service_results。
        SYSTEM frame 不含 state（只有 USER frame 有 state）。
        """
        # 系统动作
        act_type = _INTENT_TO_SYSTEM_ACT.get(active_intent, "INFORM")
        actions = []

        if act_type == "REQUEST":
            # 核实身份时请求槽位
            requested_slot = (
                "customer_name" if active_intent == "verify_identity" else ""
            )
            actions.append({
                "act": "REQUEST",
                "slot": requested_slot,
                "values": [],
                "canonical_values": [],
            })
        elif act_type == "INFORM":
            # 告知关键槽位
            for slot_name in _INTENT_TO_SLOTS.get(active_intent, []):
                if slot_name in cumulative_slot_values:
                    actions.append({
                        "act": "INFORM",
                        "slot": slot_name,
                        "values": cumulative_slot_values[slot_name],
                        "canonical_values": cumulative_slot_values[slot_name],
                    })
        elif act_type == "GOODBYE":
            actions.append({
                "act": "GOODBYE",
                "slot": "",
                "values": [],
                "canonical_values": [],
            })

        # SGD 规范：service_call 和 service_results 仅当实际调用 API 时存在
        # 条件：意图对应有 API 方法，且已有关键槽值（非 general_inquiry 或空状态）
        api_method = _INTENT_TO_API.get(active_intent)
        frame: Dict[str, Any] = {
            "service": SERVICE_NAME,
            "slots": [],  # SGD 规范要求，字符级标注，本实现留空
            "actions": actions,
        }

        if api_method and active_intent not in ("general_inquiry",):
            service_call = _build_service_call(active_intent, cumulative_slot_values)
            service_results = _build_service_results(active_intent, user_info)
            if service_call is not None:
                frame["service_call"] = service_call
            if service_results:
                frame["service_results"] = service_results

        return frame

    def _extract_user_actions(
        self,
        utterance: str,
        cumulative_slot_values: Dict[str, List[str]],
    ) -> List[Dict]:
        """
        从用户话语中提取显式信息提供行为（INFORM 动作）。

        检测用户话语中明确提及的实体：
        - 姓名（检测"先生"/"女士"）
        - 手机尾号（3–4 位数字）
        - 日期（检测"月"/"号"/"日"）
        - 金额（检测"元"/"万"）

        参数:
            utterance:              用户话语
            cumulative_slot_values: 当前累积槽值（避免重复提取）

        返回:
            INFORM 动作列表
        """
        actions: List[Dict] = []

        # 检测姓名提及
        name_match = re.search(r"([\u4e00-\u9fa5]{1,3}(?:先生|女士))", utterance)
        if name_match and "customer_name" not in cumulative_slot_values:
            name = name_match.group(1)
            actions.append({
                "act": "INFORM",
                "slot": "customer_name",
                "values": [name],
                "canonical_values": [name],
            })

        # 检测手机尾号（3–4 位纯数字，与 schema 中 phone_suffix 规范对齐）
        phone_match = re.search(r"\b(\d{3,4})\b", utterance)
        if phone_match and "phone_suffix" not in cumulative_slot_values:
            suffix = phone_match.group(1)
            actions.append({
                "act": "INFORM",
                "slot": "phone_suffix",
                "values": [suffix],
                "canonical_values": [suffix],
            })

        # 检测日期（如"七月二十三号"）
        date_match = re.search(r"([一二三四五六七八九十]+月[一二三四五六七八九十零百]+[号日])", utterance)
        if date_match:
            date_str = date_match.group(1)
            actions.append({
                "act": "INFORM",
                "slot": "dispute_date",
                "values": [date_str],
                "canonical_values": [date_str],
            })

        return actions
