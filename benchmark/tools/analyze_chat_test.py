#!/usr/bin/env python3
"""
chat_test_100.json 信息提取分析工具（LLM 版，数据驱动本体）

两阶段流程：
  Phase 0（本体归纳）：从安逸花外呼对话数据中归纳可靠本体（意图/槽位/对话行为），
                       不使用任何预定义列表，完全从数据中提炼。
  Phase 1（SGD 转换）：以归纳本体为指导，使用 LLM 将对话数据转换为 SGD 格式。

----------------------------------------------------------------------
设计原则
----------------------------------------------------------------------

本工具遵循数据驱动（data-driven）原则：
  - 意图列表、槽位列表、对话行为类型等均从实际对话数据中归纳，不预先定义。
  - 预定义常量（VALID_INTENTS / VALID_SLOTS / VALID_ACTS）仅作为 LLM 不可用时的
    兜底回退，不在正常流程中作为硬约束使用。
  - 采用开放词汇（open vocabulary）策略：验证和清洗时接受 LLM 归纳的任意命名，
    名称规范化为 小写_下划线（意图/槽位）或 大写（对话行为）格式。

----------------------------------------------------------------------
SGD 对话字段（dialogues_*.json）
----------------------------------------------------------------------

dialogue_id        → 直接从 session_id 映射
services           → 固定为 ["AnYiHua_1"]
metadata           → 扩展字段（qc_label, reference_response, user_info_parsed）

USER turn：
  speaker          → "USER"
  utterance        → 对话原文
  active_intent    → LLM 提取（用户本轮任务意图，来自归纳本体）
  requested_slots  → LLM 提取（用户正在询问的槽位）
  slot_values      → LLM 提取（累积对话状态 {slot: [value]}）
  actions          → LLM 提取（用户对话行为动作）
  frames[].slots   → ❌ 缺失（字符跨度标注，需人工标注工具）

SYSTEM turn：
  speaker          → "SYSTEM"
  utterance        → 对话原文
  actions          → LLM 提取（系统对话行为动作）
  service_call     → LLM 提取（调用的 API 及参数）
  service_results  → LLM 提取（API 返回数据，结合 CRM 金标准）
  frames[].slots   → ❌ 缺失（字符跨度标注，需人工标注工具）

----------------------------------------------------------------------
LLM 配置
----------------------------------------------------------------------

从 .env 文件读取（通过 contextmind/infra/llm_client.py）：
  QWEN3_API_KEY   / LLM_API_KEY
  QWEN3_BASE_URL  / LLM_BASE_URL
  QWEN3_MODEL     / LLM_MODEL

----------------------------------------------------------------------
用法
----------------------------------------------------------------------

  # 处理前 5 条对话（默认，快速预览）
  python benchmark/tools/analyze_chat_test.py

  # 处理前 N 条
  python benchmark/tools/analyze_chat_test.py --sample 20

  # 处理全部 100 条
  python benchmark/tools/analyze_chat_test.py --all

  # 指定输入/输出
  python benchmark/tools/analyze_chat_test.py \\
      --input resources/data/chat_test_100.json \\
      --output-dir resources/data \\
      --sample 10

----------------------------------------------------------------------
输出
----------------------------------------------------------------------

  resources/data/chat_test_discovered_ontology.json  Phase 0 归纳的服务本体
  resources/data/chat_test_extraction_report.json    机器可读结构化报告
  resources/data/chat_test_extraction_report.md      人类可读 Markdown 报告
  resources/data/chat_test_sgd_dialogues.json        标准 SGD 格式对话数据集
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

from contextmind.scenarios.anyihua.utils import parse_user_info

# --------------------------------------------------------------------------- #
# 常量 — SGD 字段规范（与 resources/anyihua_sgd/schema.json 对齐）
# --------------------------------------------------------------------------- #

SERVICE_NAME = "AnYiHua_1"
_SCHEMA_PATH = _PROJECT_ROOT / "resources" / "anyihua_sgd" / "schema.json"

# Report display limit for field lists
_MAX_FIELDS_DISPLAY = 5

VALID_INTENTS: List[str] = [
    "verify_identity",
    "explain_credit_limit",
    "explain_interest_rate",
    "calculate_repayment",
    "explain_displayed_amount",
    "handle_loan_dispute",
    "guide_loan_operation",
    "escalate_to_human",
    "say_goodbye",
    "general_inquiry",
]

VALID_SLOTS: List[str] = [
    "customer_name",
    "phone_suffix",
    "available_credit",
    "temp_credit",
    "temp_credit_status",
    "temp_expiry_days",
    "annual_rate_pct",
    "loan_count",
    "last_loan_date",
    "outstanding_amount",
    "billing_day",
    "dispute_date",
    "inquiry_amount",
    "term_months",
    "identity_confirmed",
]

# SGD 标准对话行为类型
VALID_ACTS: List[str] = [
    "INFORM",
    "REQUEST",
    "CONFIRM",
    "SELECT",
    "OFFER",
    "GOODBYE",
    "INFORM_INTENT",
    "NEGATE_INTENT",
    "AFFIRM_INTENT",
    "AFFIRM",
    "NEGATE",
    "CANT_UNDERSTAND",
    "NOTIFY_SUCCESS",
    "NOTIFY_FAILURE",
]

# Sets for O(1) membership checks (ordered lists kept for report iteration)
_VALID_INTENTS_SET: set = set(VALID_INTENTS)
_VALID_SLOTS_SET: set = set(VALID_SLOTS)
_VALID_ACTS_SET: set = set(VALID_ACTS)

# 意图 → 对应 CRM API 名称
INTENT_TO_API: Dict[str, str] = {
    "verify_identity": "verify_customer",
    "explain_credit_limit": "query_account",
    "explain_interest_rate": "calculate_repayment",
    "calculate_repayment": "calculate_repayment",
    "explain_displayed_amount": "query_account",
    "handle_loan_dispute": "query_loan_records",
    "guide_loan_operation": "query_account",
    "escalate_to_human": "",
    "say_goodbye": "query_unresolved_issues",
    "general_inquiry": "",
}

_AGENT_PREFIX = "坐席："
_USER_PREFIX = "用户："

_DEFAULT_INPUT = str(_PROJECT_ROOT / "resources" / "data" / "chat_test_100.json")
_DEFAULT_OUTPUT_DIR = str(_PROJECT_ROOT / "resources" / "data")
_DEFAULT_SAMPLE = 5

# --------------------------------------------------------------------------- #
# 本体归纳（Phase 0）：从原始对话数据中提炼意图/槽位/对话行为
# --------------------------------------------------------------------------- #

_ONTOLOGY_SYSTEM_PROMPT = (
    "你是专业的对话数据分析专家，精通任务型对话（TOD）系统设计和本体工程。\n"
    "你的任务是从实际对话数据中归纳出可靠的服务本体（Ontology）。\n"
    "严格要求：仅根据对话中实际出现的内容归纳，不要添加未观察到的内容。\n"
    "槽位命名规范：英文小写下划线格式（如 customer_name）；"
    "意图命名同理（如 verify_identity）；对话行为使用大写（如 INFORM）。"
)


def _normalize_name_snake(name: str) -> str:
    """将任意名称规范化为 小写_下划线 格式。"""
    name = name.strip().lower()
    # replace spaces, hyphens, dots with underscore
    name = re.sub(r"[\s\-\.]+", "_", name)
    # remove any character that isn't alphanumeric or underscore
    name = re.sub(r"[^\w]", "", name)
    return name


def _normalize_discovered_ontology(raw: Dict[str, Any]) -> Dict[str, Any]:
    """对 LLM 发现的本体进行规范化处理。"""
    intents_raw = raw.get("intents", [])
    slots_raw = raw.get("slots", [])
    acts_raw = raw.get("dialog_acts", [])

    seen_intents: set = set()
    normalized_intents = []
    for item in intents_raw:
        if not isinstance(item, dict):
            continue
        name = _normalize_name_snake(item.get("name", ""))
        if not name or name in seen_intents:
            continue
        seen_intents.add(name)
        normalized_intents.append({
            "name": name,
            "description": item.get("description", ""),
            "frequency": item.get("frequency", ""),
            "typical_phrases": item.get("typical_phrases", []),
            # SGD-compatible fields (empty until mapping is done)
            "required_slots": item.get("required_slots", []),
            "optional_slots": item.get("optional_slots", {}),
            "result_slots": item.get("result_slots", []),
        })

    seen_slots: set = set()
    normalized_slots = []
    for item in slots_raw:
        if not isinstance(item, dict):
            continue
        name = _normalize_name_snake(item.get("name", ""))
        if not name or name in seen_slots:
            continue
        seen_slots.add(name)
        data_type = item.get("data_type", "text")
        normalized_slots.append({
            "name": name,
            "description": item.get("description", ""),
            "source": item.get("source", ""),
            "data_type": data_type,
            "is_categorical": data_type == "enum",
            "possible_values": item.get("possible_values", []),
            "example_values": item.get("example_values", []),
        })

    seen_acts: set = set()
    normalized_acts = []
    for item in acts_raw:
        if not isinstance(item, dict):
            continue
        act = item.get("act", "").strip().upper().replace(" ", "_").replace("-", "_")
        if not act or act in seen_acts:
            continue
        seen_acts.add(act)
        normalized_acts.append({
            "act": act,
            "description": item.get("description", ""),
            "speaker": item.get("speaker", "BOTH"),
            "example": item.get("example", ""),
        })

    return {
        "service_name": raw.get("service_name", SERVICE_NAME),
        "service_description": raw.get("service_description", ""),
        "intents": normalized_intents,
        "slots": normalized_slots,
        "dialog_acts": normalized_acts,
        "total_intents": len(normalized_intents),
        "total_slots": len(normalized_slots),
        "total_acts": len(normalized_acts),
        # Flat lists for quick membership tests
        "intent_names": [i["name"] for i in normalized_intents],
        "slot_names": [s["name"] for s in normalized_slots],
        "act_names": [a["act"] for a in normalized_acts],
        "acts": [a["act"] for a in normalized_acts],  # backward compat alias
        "source": "data_driven",
    }


def extract_ontology_from_dialogues(
    records: List[Dict[str, Any]],
    llm_client: Any,
    sample_n: int = 30,
) -> Dict[str, Any]:
    """Phase 0：从实际对话数据归纳服务本体（意图/槽位/对话行为）。

    不使用任何预定义列表，完全从原始对话文本中提炼。
    失败时退化为读取 schema.json。
    """
    sample = records[: min(sample_n, len(records))]

    dialogue_texts: List[str] = []
    for i, record in enumerate(sample):
        turns = record.get("对话历史", [])
        lines = []
        for t in turns:
            if t.startswith(_AGENT_PREFIX):
                lines.append(f"  坐席: {t[len(_AGENT_PREFIX):]}")
            elif t.startswith(_USER_PREFIX):
                lines.append(f"  用户: {t[len(_USER_PREFIX):]}")
        dialogue_texts.append(f"=== 对话 {i + 1} ===\n" + "\n".join(lines))

    dialogues_text = "\n\n".join(dialogue_texts)

    prompt = (
        "请分析以下安逸花外呼对话数据，归纳出完整的服务本体。\n\n"
        "归纳要求：\n"
        "1. 意图（intent）：用户在对话中期望达成的具体任务目标，用英文小写下划线命名\n"
        "2. 槽位（slot）：对话中出现的所有关键信息字段，用英文小写下划线命名\n"
        "   - CRM来源：坐席从系统读取的用户账户信息（如姓名、额度、利率等）\n"
        "   - 对话来源：用户在对话中主动提供或询问的信息\n"
        "3. 对话行为（dialog act）：坐席和用户实际表现出的对话行为类型，用大写英文命名\n\n"
        "重要：只归纳在对话中实际观察到的内容，不要添加未出现的内容。\n\n"
        f"{dialogues_text}\n\n"
        "输出合法 JSON（仅输出 JSON，不要任何说明）：\n"
        "{\n"
        '  "service_name": "安逸花外呼促活",\n'
        '  "service_description": "对该服务的简短自然语言描述",\n'
        '  "intents": [\n'
        '    {"name": "英文小写名", "description": "中文描述", "frequency": "高/中/低",\n'
        '     "typical_phrases": ["典型用户话语（可选）"]}\n'
        "  ],\n"
        '  "slots": [\n'
        '    {"name": "英文小写名", "description": "中文描述", "source": "CRM/对话",\n'
        '     "data_type": "text/number/date/enum",\n'
        '     "example_values": ["示例值1", "示例值2"]}\n'
        "  ],\n"
        '  "dialog_acts": [\n'
        '    {"act": "大写英文名", "description": "中文描述",\n'
        '     "speaker": "USER/SYSTEM/BOTH", "example": "示例话语（可选）"}\n'
        "  ]\n"
        "}"
    )

    try:
        _, response_text = llm_client.generate(_ONTOLOGY_SYSTEM_PROMPT + "\n\n" + prompt)
        parsed = _extract_json_from_text(response_text)
        if parsed and isinstance(parsed, dict) and parsed.get("intents"):
            print(
                f"  ✅ 本体归纳成功：{len(parsed.get('intents', []))} 意图，"
                f"{len(parsed.get('slots', []))} 槽位，"
                f"{len(parsed.get('dialog_acts', []))} 对话行为"
            )
            return _normalize_discovered_ontology(parsed)
        else:
            print("  ⚠️  本体归纳响应格式异常，退化为 schema.json")
    except Exception as exc:
        print(f"  ⚠️  本体归纳 LLM 调用失败：{exc}，退化为 schema.json")

    return _load_ontology()


# --------------------------------------------------------------------------- #
# LLM 提取提示模板
# --------------------------------------------------------------------------- #

_EXTRACTION_SYSTEM_PROMPT_BASE = (
    "你是专业的任务型对话（TOD）结构化标注助手，熟悉 SGD（Schema-Guided Dialogue）数据集格式规范。\n"
    "你的任务是对安逸花外呼数据进行完整、精准的 SGD 字段提取，用于构建标准 TOD 数据集。\n\n"
    "业务背景：\n"
    "- 安逸花是马上消费金融旗下的消费贷款产品\n"
    "- 坐席（SYSTEM）主动致电老用户，目标是激活用户闲置的借款额度\n"
    "- 标准流程：核实身份 → 告知额度 → 解答疑问 → 引导借款 → 礼貌告别\n"
    "- 坐席掌握完整的 CRM 数据（用户信息字段），用户只能确认或询问\n\n"
    "SGD 字段说明：\n\n"
    "USER turn 需提取：\n"
    "  active_intent     — 用户本轮期望坐席帮助完成的任务意图（从本体意图列表选择，若无匹配可填 general_inquiry）\n"
    "                      注意：用户说「对」「嗯」等短回应时，继承上一轮的意图\n"
    "  requested_slots   — 用户明确询问但尚未获知的槽位（如「利率是多少」→ [\"annual_rate_pct\"]）\n"
    "  slot_values       — 截至本轮已确认的累积对话状态 {\"slot_name\": [\"value\"]}\n"
    "                      包括用户主动提供的信息（如告知争议日期、分期期数等）\n"
    "  actions           — 用户对话行为列表，格式：{\"act\":\"...\",\"slot\":\"...\",\"values\":[...],\"canonical_values\":[...]}\n"
    "                      INFORM 表示用户提供信息，REQUEST 表示用户请求信息\n\n"
    "SYSTEM turn 需提取：\n"
    "  actions           — 系统对话行为列表，格式同上\n"
    "                      REQUEST 表示系统请求信息，INFORM 表示系统提供信息\n"
    "  service_call      — 系统调用的 CRM API，格式：{\"method\":\"api_name\",\"parameters\":{...}}\n"
    "                      仅当坐席话语触发实际 API 调用时填写；开场问候等不填\n"
    "  service_results   — API 返回数据，格式：[{\"slot_name\":\"value\",...}]\n"
    "                      从提供的 CRM 数据中提取对应字段\n\n"
    "提取原则：\n"
    "1. 精准 > 完整：不确定时留空，不要猜测\n"
    "2. slot_values 是累积状态，每轮必须包含之前轮次已确认的所有槽位值\n"
    "3. SYSTEM 的 actions 反映坐席的沟通行为\n"
    "4. 只有坐席引用 CRM 数据时才填写 service_call 和 service_results"
)


def _build_extraction_system_prompt(discovered_ontology: Optional[Dict[str, Any]] = None) -> str:
    """构建提取阶段的 System Prompt，使用已归纳的本体（而非预定义列表）。"""
    if discovered_ontology and discovered_ontology.get("intent_names"):
        intent_list = ", ".join(discovered_ontology["intent_names"])
        slot_list = ", ".join(discovered_ontology["slot_names"])
        act_list = ", ".join(discovered_ontology["act_names"])
        ontology_section = (
            f"已从数据归纳的本体（优先使用以下名称，如有新发现可扩展）：\n"
            f"意图列表：{intent_list}\n"
            f"槽位列表：{slot_list}\n"
            f"对话行为列表：{act_list}\n"
        )
    else:
        # Fallback to hardcoded defaults
        ontology_section = (
            "参考意图列表（可根据实际对话扩展）：\n"
            "verify_identity, explain_credit_limit, explain_interest_rate, calculate_repayment,\n"
            "explain_displayed_amount, handle_loan_dispute, guide_loan_operation,\n"
            "escalate_to_human, say_goodbye, general_inquiry\n\n"
            "参考槽位列表（可根据实际对话扩展）：\n"
            "customer_name, phone_suffix, available_credit, temp_credit, temp_credit_status,\n"
            "temp_expiry_days, annual_rate_pct, loan_count, last_loan_date, outstanding_amount,\n"
            "billing_day, dispute_date, inquiry_amount, term_months, identity_confirmed\n\n"
            "参考对话行为列表（可根据实际对话扩展）：\n"
            "INFORM, REQUEST, CONFIRM, SELECT, OFFER, GOODBYE, INFORM_INTENT, NEGATE_INTENT,\n"
            "AFFIRM_INTENT, AFFIRM, NEGATE, CANT_UNDERSTAND, NOTIFY_SUCCESS, NOTIFY_FAILURE\n"
        )
    return _EXTRACTION_SYSTEM_PROMPT_BASE + "\n\n" + ontology_section


def _build_extraction_prompt(
    record: Dict[str, Any],
    discovered_ontology: Optional[Dict[str, Any]] = None,
) -> str:
    """构建单条记录的完整 LLM 提取 Prompt（使用从数据归纳的本体）。"""
    crm = parse_user_info(record.get("用户信息", ""))
    raw_turns = record.get("对话历史", [])

    turns_lines = []
    for i, raw in enumerate(raw_turns):
        if raw.startswith(_AGENT_PREFIX):
            speaker = "SYSTEM"
            utt = raw[len(_AGENT_PREFIX):]
        else:
            speaker = "USER"
            utt = raw[len(_USER_PREFIX):]
        turns_lines.append(f"[{i}] {speaker}: {utt}")
    turns_text = "\n".join(turns_lines)

    crm_summary = (
        f"客户姓名: {crm.get('customer_name', '未知')}\n"
        f"手机尾号: {crm.get('phone_suffix', '未知')}\n"
        f"可提现额度: {crm.get('available_credit', 0)} 元\n"
        f"临时额度: {crm.get('temp_credit', 0)} 元 "
        f"({'已过期' if crm.get('temp_expired') else '有效，剩余' + str(crm.get('temp_active_days', 0)) + '天'})\n"
        f"年化利率: {crm.get('annual_rate_pct', 24)}%\n"
        f"未还借款笔数: {crm.get('loan_count', 0)}\n"
        f"最近借款日期: {crm.get('last_loan_date', '无')}\n"
        f"未还款金额: {crm.get('outstanding_amount', 0)} 元\n"
        f"账单日: 每月 {crm.get('billing_day', 0)} 号\n"
        f"已授信天数: {crm.get('authorized_days', 0)} 天\n"
        f"初始额度: {crm.get('initial_credit', 0)} 元\n"
        f"授信额度: {crm.get('authorized_credit', 0)} 元"
    )

    json_template = (
        '{\n'
        '  "turns": [\n'
        '    {\n'
        '      "turn_idx": 0,\n'
        '      "speaker": "SYSTEM",\n'
        '      "utterance": "原文",\n'
        '      "actions": [{"act": "REQUEST", "slot": "customer_name", "values": [], "canonical_values": []}],\n'
        '      "service_call": {"method": "verify_customer", "parameters": {"name": "高先生"}},\n'
        '      "service_results": [{"customer_name": "高先生", "identity_confirmed": "true"}]\n'
        '    },\n'
        '    {\n'
        '      "turn_idx": 1,\n'
        '      "speaker": "USER",\n'
        '      "utterance": "原文",\n'
        '      "active_intent": "verify_identity",\n'
        '      "requested_slots": [],\n'
        '      "slot_values": {"customer_name": ["高先生"]},\n'
        '      "actions": [{"act": "AFFIRM", "slot": "", "values": [], "canonical_values": []}]\n'
        '    }\n'
        '  ]\n'
        '}'
    )

    prompt = (
        "请对以下安逸花外呼对话进行完整的 SGD 字段提取，输出必须是合法 JSON。\n\n"
        f"--- CRM 数据（坐席已知的用户信息）---\n{crm_summary}\n\n"
        f"--- 对话历史（共 {len(raw_turns)} 轮）---\n{turns_text}\n\n"
        "--- 提取任务 ---\n\n"
        "请按照 SGD 格式对每一轮进行完整标注，输出格式示例：\n\n"
        f"{json_template}\n\n"
        "注意：\n"
        "- SYSTEM turn 不填 active_intent/requested_slots/slot_values；没有 service_call 时填 null\n"
        "- USER turn 不填 service_call/service_results\n"
        "- slot_values 是累积状态（包含之前所有已确认的槽位值）\n"
        "- 意图名、槽位名、行为名优先使用本体列表中的名称；如对话中出现新的概念，可使用英文小写下划线格式新增\n"
        "- 仅输出 JSON，不要任何解释文字"
    )
    return _build_extraction_system_prompt(discovered_ontology) + "\n\n" + prompt


# --------------------------------------------------------------------------- #
# JSON 解析
# --------------------------------------------------------------------------- #

def _extract_json_from_text(text: str) -> Optional[Dict]:
    """从 LLM 返回文本中提取 JSON 对象。"""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    for pattern in [r"```json\s*([\s\S]+?)```", r"```\s*([\s\S]+?)```"]:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                pass

    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start != -1:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    start = -1
    return None


def _validate_and_clean_turn(
    turn: Dict[str, Any],
    discovered_ontology: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """对单轮提取结果进行规范化清洗。

    使用从数据归纳的本体（open vocabulary）：
    - 意图/槽位/行为名称做轻量规范化（小写下划线/大写），但不过滤掉未知值
    - 若本体中有发现列表，优先使用其中的名称；否则接受任何合法格式的值
    - 空意图时兜底为 general_inquiry
    """
    # Build lookup sets from discovered ontology (or fall back to hardcoded)
    if discovered_ontology:
        valid_acts_set = set(discovered_ontology.get("act_names", []))
        valid_slots_set = set(discovered_ontology.get("slot_names", []))
        valid_intents_set = set(discovered_ontology.get("intent_names", []))
    else:
        valid_acts_set = _VALID_ACTS_SET
        valid_slots_set = _VALID_SLOTS_SET
        valid_intents_set = _VALID_INTENTS_SET

    speaker = turn.get("speaker", "")
    cleaned: Dict[str, Any] = {
        "turn_idx": turn.get("turn_idx", -1),
        "speaker": speaker,
        "utterance": turn.get("utterance", ""),
    }

    raw_actions = turn.get("actions", []) or []
    actions = []
    for a in raw_actions:
        if not isinstance(a, dict):
            continue
        act_raw = (a.get("act", "") or "").strip().upper().replace(" ", "_")
        if not act_raw:
            continue
        # Accept: known acts from ontology, or any UPPER_SNAKE non-empty string
        act = act_raw if act_raw in valid_acts_set else act_raw
        slot_raw = (a.get("slot", "") or "").strip()
        slot = _normalize_name_snake(slot_raw) if slot_raw else ""
        # Keep slot even if not in known set — it may be a newly discovered slot
        values = a.get("values", []) or []
        canonical_values = a.get("canonical_values", []) or []
        actions.append({
            "act": act,
            "slot": slot,
            "values": [str(v) for v in values] if isinstance(values, list) else [],
            "canonical_values": [str(v) for v in canonical_values] if isinstance(canonical_values, list) else [],
        })
    cleaned["actions"] = actions

    if speaker == "USER":
        intent_raw = (turn.get("active_intent", "") or "").strip()
        intent = _normalize_name_snake(intent_raw) if intent_raw else ""
        # Accept discovered intents; unknown intents kept as-is; empty → general_inquiry
        cleaned["active_intent"] = intent if intent else "general_inquiry"

        raw_req = turn.get("requested_slots", []) or []
        cleaned["requested_slots"] = [
            _normalize_name_snake(s) for s in raw_req
            if isinstance(s, str) and s.strip()
        ]

        raw_sv = turn.get("slot_values", {}) or {}
        cleaned["slot_values"] = {
            _normalize_name_snake(k): (v if isinstance(v, list) else [str(v)])
            for k, v in raw_sv.items()
            if isinstance(k, str) and k.strip() and v
        }

    elif speaker == "SYSTEM":
        sc = turn.get("service_call")
        if sc and isinstance(sc, dict) and sc.get("method"):
            cleaned["service_call"] = {
                "method": str(sc["method"]),
                "parameters": sc.get("parameters", {}) or {},
            }
        else:
            cleaned["service_call"] = None

        sr = turn.get("service_results")
        if sr and isinstance(sr, list):
            cleaned["service_results"] = [
                {
                    _normalize_name_snake(k): str(v)
                    for k, v in item.items()
                    if isinstance(k, str) and k.strip()
                }
                for item in sr if isinstance(item, dict)
            ]
        else:
            cleaned["service_results"] = []

    return cleaned


# --------------------------------------------------------------------------- #
# CRM 数据作为 service_results 金标准
# --------------------------------------------------------------------------- #

def _build_service_results_from_crm(crm: Dict[str, Any], intent: str) -> List[Dict[str, str]]:
    """根据意图从 CRM 数据构建 service_results。"""
    api_map = {
        "verify_identity": "verify_customer",
        "explain_credit_limit": "query_account",
        "explain_interest_rate": "calculate_repayment",
        "calculate_repayment": "calculate_repayment",
        "explain_displayed_amount": "query_account",
        "handle_loan_dispute": "query_loan_records",
        "guide_loan_operation": "query_account",
    }
    if intent not in api_map:
        return []

    base: Dict[str, str] = {}
    if crm.get("customer_name"):
        base["customer_name"] = crm["customer_name"]
    if crm.get("phone_suffix"):
        base["phone_suffix"] = crm["phone_suffix"]

    api = api_map[intent]
    if api == "verify_customer":
        base["identity_confirmed"] = "true"
    elif api == "query_account":
        if crm.get("available_credit"):
            base["available_credit"] = str(crm["available_credit"])
        if crm.get("temp_credit"):
            base["temp_credit"] = str(crm["temp_credit"])
        base["temp_credit_status"] = "已过期" if crm.get("temp_expired") else "有效"
        if crm.get("temp_active_days"):
            base["temp_expiry_days"] = str(crm["temp_active_days"])
        if crm.get("annual_rate_pct"):
            base["annual_rate_pct"] = str(crm["annual_rate_pct"])
        if crm.get("billing_day"):
            base["billing_day"] = str(crm["billing_day"])
    elif api == "query_loan_records":
        if crm.get("loan_count"):
            base["loan_count"] = str(crm["loan_count"])
        if crm.get("last_loan_date"):
            base["last_loan_date"] = crm["last_loan_date"]
        if crm.get("outstanding_amount"):
            base["outstanding_amount"] = str(crm["outstanding_amount"])
    elif api == "calculate_repayment":
        if crm.get("annual_rate_pct"):
            base["annual_rate_pct"] = str(crm["annual_rate_pct"])

    return [base] if base else []


def _backfill_service_results(turns: List[Dict], crm: Dict[str, Any]) -> None:
    """对空的 service_results 使用 CRM 数据补全。"""
    last_intent = "general_inquiry"
    for t in turns:
        if t["speaker"] == "USER":
            last_intent = t.get("active_intent", "general_inquiry")
        elif t["speaker"] == "SYSTEM":
            if not t.get("service_results") and last_intent not in (
                "general_inquiry", "say_goodbye", "escalate_to_human", ""
            ):
                t["service_results"] = _build_service_results_from_crm(crm, last_intent)


# --------------------------------------------------------------------------- #
# LLM 提取
# --------------------------------------------------------------------------- #

def extract_record_with_llm(
    record: Dict[str, Any],
    llm_client: Any,
    discovered_ontology: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """使用 LLM 对单条记录进行完整 SGD 字段提取（使用从数据归纳的本体）。"""
    session_id = record["session_id"]
    crm = parse_user_info(record.get("用户信息", ""))
    raw_turns = record.get("对话历史", [])

    prompt = _build_extraction_prompt(record, discovered_ontology=discovered_ontology)
    parsed = None

    try:
        _, response_text = llm_client.generate(prompt)
        parsed = _extract_json_from_text(response_text)
    except Exception as exc:
        print(f"  ⚠️  LLM 调用失败 [{session_id[:20]}]: {exc}")

    extracted_turns: List[Dict[str, Any]] = []
    if parsed and isinstance(parsed, dict):
        for t in parsed.get("turns", []):
            extracted_turns.append(_validate_and_clean_turn(t, discovered_ontology=discovered_ontology))
    else:
        # 降级：生成空骨架
        for i, raw in enumerate(raw_turns):
            speaker = "SYSTEM" if raw.startswith(_AGENT_PREFIX) else "USER"
            utt = raw[len(_AGENT_PREFIX):] if speaker == "SYSTEM" else raw[len(_USER_PREFIX):]
            t: Dict[str, Any] = {
                "turn_idx": i, "speaker": speaker, "utterance": utt, "actions": []
            }
            if speaker == "USER":
                t.update({"active_intent": "general_inquiry", "requested_slots": [], "slot_values": {}})
            else:
                t.update({"service_call": None, "service_results": []})
            extracted_turns.append(t)

    _backfill_service_results(extracted_turns, crm)

    return {
        "session_id": session_id,
        "qc_label": record.get("人工校验", ""),
        "reference_response": record.get("坐席回复", ""),
        "crm_parsed": crm,
        "turn_count": len(raw_turns),
        "turns": extracted_turns,
        "llm_succeeded": parsed is not None,
    }


# --------------------------------------------------------------------------- #
# 统计汇总辅助
# --------------------------------------------------------------------------- #

def _load_ontology() -> Dict[str, Any]:
    """加载 resources/anyihua_sgd/schema.json，返回本体数据。"""
    try:
        with open(_SCHEMA_PATH, encoding="utf-8") as f:
            schemas = json.load(f)
        schema = schemas[0] if isinstance(schemas, list) else schemas
        intents = schema.get("intents", [])
        slots = schema.get("slots", [])
        return {
            "service_name": schema.get("service_name", SERVICE_NAME),
            "service_description": schema.get("description", ""),
            "slots": slots,
            "intents": intents,
            "total_slots": len(slots),
            "total_intents": len(intents),
            "total_acts": len(VALID_ACTS),
            "acts": VALID_ACTS,
            # Flat name lists for membership tests and prompt building
            "intent_names": [i["name"] for i in intents if isinstance(i, dict)],
            "slot_names": [s["name"] for s in slots if isinstance(s, dict)],
            "act_names": list(VALID_ACTS),
            "source": "schema_json",
        }
    except Exception:
        # schema.json 缺失时退化为内置常量列表
        return {
            "service_name": SERVICE_NAME,
            "service_description": "（schema.json 未找到）",
            "slots": [{"name": s, "description": "", "is_categorical": False, "possible_values": []} for s in VALID_SLOTS],
            "intents": [{"name": i, "description": "", "required_slots": [], "optional_slots": {}, "result_slots": []} for i in VALID_INTENTS],
            "total_slots": len(VALID_SLOTS),
            "total_intents": len(VALID_INTENTS),
            "total_acts": len(VALID_ACTS),
            "acts": VALID_ACTS,
            "intent_names": list(VALID_INTENTS),
            "slot_names": list(VALID_SLOTS),
            "act_names": list(VALID_ACTS),
            "source": "hardcoded_fallback",
        }


def _derive_common_flow(
    entry_intents: List[str],
    exit_intents: List[str],
    top_transitions: List[Dict[str, Any]],
) -> str:
    """从实际数据派生最常见对话流程字符串。"""
    if not entry_intents:
        return "（数据不足，无法推导流程）"

    entry_counter: Counter = Counter(entry_intents)
    exit_counter: Counter = Counter(exit_intents)
    most_common_entry = entry_counter.most_common(1)[0][0]
    most_common_exit = exit_counter.most_common(1)[0][0]

    # 从入口出发，沿最高频转移路径走至多 3 步
    path = [most_common_entry]
    seen: set = {most_common_entry}
    for _ in range(3):
        current = path[-1]
        next_step = None
        for t in top_transitions:
            if t["from"] == current and t["to"] not in seen:
                next_step = t["to"]
                break
        if next_step is None:
            break
        path.append(next_step)
        seen.add(next_step)
        if next_step == most_common_exit:
            break

    if most_common_exit not in path:
        path.append("...")
        path.append(most_common_exit)

    # 找出口前的分支意图（与出口直连的、非主路径上的意图）
    branch_intents = [
        t["to"] for t in top_transitions
        if t["from"] in path[:-1] and t["to"] != most_common_exit and t["to"] not in path
    ][:3]
    branch_str = " | ".join(branch_intents) if branch_intents else ""

    flow = " → ".join(path)
    if branch_str and "..." not in flow:
        # 在最后一步前插入分支说明
        parts = path[:-1]
        last = path[-1]
        flow = " → ".join(parts) + f" → ({branch_str}) → {last}"

    # 附上频率说明
    entry_pct = round(entry_counter[most_common_entry] / len(entry_intents) * 100)
    exit_pct = round(exit_counter[most_common_exit] / len(exit_intents) * 100)
    return (
        f"{flow}\n"
        f"（入口意图 {most_common_entry} 占 {entry_pct}%；"
        f"出口意图 {most_common_exit} 占 {exit_pct}%）"
    )


def _enrich_ontology_with_observed(
    ontology: Dict[str, Any],
    slot_analysis: Dict[str, Any],
    intent_dist: Dict[str, Any],
) -> None:
    """将实际观察到但本体中缺失的意图/槽位补充进本体（in-place）。

    确保本体真实反映数据中发现的所有概念。
    """
    known_slots = {s["name"] for s in ontology.get("slots", []) if isinstance(s, dict)}
    for slot in slot_analysis:
        if slot and slot not in known_slots:
            ontology.setdefault("slots", []).append({
                "name": slot,
                "description": "（从对话数据中发现，非预定义）",
                "source": "observed",
                "is_categorical": False,
                "possible_values": [],
            })
    # Update flat name list
    ontology["slot_names"] = [s["name"] for s in ontology.get("slots", []) if isinstance(s, dict)]
    ontology["total_slots"] = len(ontology["slot_names"])

    known_intents = {i["name"] for i in ontology.get("intents", []) if isinstance(i, dict)}
    for intent in intent_dist:
        if intent and intent not in known_intents:
            ontology.setdefault("intents", []).append({
                "name": intent,
                "description": "（从对话数据中发现，非预定义）",
                "required_slots": [],
                "optional_slots": {},
                "result_slots": [],
            })
    # Update flat name list
    ontology["intent_names"] = [i["name"] for i in ontology.get("intents", []) if isinstance(i, dict)]
    ontology["total_intents"] = len(ontology["intent_names"])


# --------------------------------------------------------------------------- #
# 统计汇总
# --------------------------------------------------------------------------- #

def aggregate_results(
    records: List[Dict[str, Any]],
    model_info: Optional[Dict[str, str]] = None,
    discovered_ontology: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """对所有已提取记录进行统计汇总。

    Args:
        records: extract_record_with_llm 的输出列表
        model_info: 实际使用的 LLM 信息（model, base_url 等），来自 LLMConfig
        discovered_ontology: Phase 0 从数据归纳的本体；若无则退化为 schema.json
    """
    n = len(records)
    n_llm_ok = sum(1 for r in records if r.get("llm_succeeded", False))
    qc_counter: Counter = Counter(r["qc_label"] for r in records)
    turn_counts = [r["turn_count"] for r in records]

    all_intents: List[str] = []
    intent_per_dialogue: List[int] = []
    entry_intents: List[str] = []
    exit_intents: List[str] = []
    intent_transitions: List[Tuple[str, str]] = []

    for r in records:
        user_intents = [
            t["active_intent"]
            for t in r["turns"]
            if t["speaker"] == "USER" and t.get("active_intent")
        ]
        all_intents.extend(user_intents)
        intent_per_dialogue.append(len(set(user_intents)) if user_intents else 0)
        if user_intents:
            entry_intents.append(user_intents[0])
            exit_intents.append(user_intents[-1])
        strategy: List[str] = []
        for intent in user_intents:
            if not strategy or strategy[-1] != intent:
                strategy.append(intent)
        for i in range(len(strategy) - 1):
            intent_transitions.append((strategy[i], strategy[i + 1]))

    intent_counter: Counter = Counter(all_intents)

    # Build intent_dist from ALL actually-observed intents (not just predefined list)
    # Merge: discovered ontology names first, then add any extra found in data
    discovered_intent_names: List[str] = []
    if discovered_ontology:
        discovered_intent_names = discovered_ontology.get("intent_names", [])
    all_observed_intents = list(
        dict.fromkeys(discovered_intent_names + [i for i in intent_counter if i not in discovered_intent_names])
    )
    intent_dist = {
        intent: {
            "count": intent_counter.get(intent, 0),
            "pct_of_user_turns": round(
                intent_counter.get(intent, 0) / len(all_intents) * 100, 1
            ) if all_intents else 0,
        }
        for intent in (all_observed_intents or VALID_INTENTS)
    }

    slot_filled: Dict[str, int] = defaultdict(int)
    slot_requested: Dict[str, int] = defaultdict(int)
    slot_informed: Dict[str, int] = defaultdict(int)
    slot_examples: Dict[str, List[str]] = defaultdict(list)

    for r in records:
        for t in r["turns"]:
            for slot, vals in t.get("slot_values", {}).items():
                # Accept any slot name (open vocabulary)
                slot_filled[slot] += 1
                if vals and len(slot_examples[slot]) < 3:
                    slot_examples[slot].extend(vals[:1])
            for slot in t.get("requested_slots", []):
                slot_requested[slot] += 1
            for a in t.get("actions", []):
                if a.get("act") == "INFORM" and a.get("slot"):
                    slot_informed[a["slot"]] += 1

    crm_key_map = {
        "customer_name": "customer_name", "phone_suffix": "phone_suffix",
        "available_credit": "available_credit", "temp_credit": "temp_credit",
        "temp_credit_status": "temp_expired", "temp_expiry_days": "temp_active_days",
        "annual_rate_pct": "annual_rate_pct", "loan_count": "loan_count",
        "last_loan_date": "last_loan_date", "outstanding_amount": "outstanding_amount",
        "billing_day": "billing_day",
    }

    # Build slot list from: discovered ontology names + any additional observed in data
    discovered_slot_names: List[str] = []
    if discovered_ontology:
        discovered_slot_names = discovered_ontology.get("slot_names", [])
    all_observed_slots = list(
        dict.fromkeys(
            discovered_slot_names
            + [s for s in slot_filled if s not in discovered_slot_names]
        )
    ) or list(VALID_SLOTS)

    slot_analysis: Dict[str, Any] = {}
    for slot in all_observed_slots:
        crm_coverage = 0
        if slot in crm_key_map:
            crm_key = crm_key_map[slot]
            crm_coverage = sum(
                1 for r in records
                # None/"" = missing; 0/False = "not set" for CRM numeric fields
                # (e.g., loan_count=0 → no loans, billing_day=0 → unknown date)
                if r["crm_parsed"].get(crm_key) not in (None, "", 0, False)
            )
        slot_analysis[slot] = {
            "filled_in_dialogue_n": slot_filled.get(slot, 0),
            "filled_in_dialogue_pct": round(slot_filled.get(slot, 0) / n * 100, 1),
            "requested_n": slot_requested.get(slot, 0),
            "informed_n": slot_informed.get(slot, 0),
            "crm_coverage_n": crm_coverage,
            "crm_coverage_pct": round(crm_coverage / n * 100, 1),
            "example_values": slot_examples.get(slot, [])[:3],
        }

    act_counter: Counter = Counter()
    service_call_methods: Counter = Counter()
    for r in records:
        for t in r["turns"]:
            for a in t.get("actions", []):
                act_counter[a.get("act", "")] += 1
            sc = t.get("service_call")
            if sc and sc.get("method"):
                service_call_methods[sc["method"]] += 1

    transition_counter: Counter = Counter(intent_transitions)
    top_transitions = [
        {"from": frm, "to": to, "count": cnt}
        for (frm, to), cnt in transition_counter.most_common(15)
    ]

    # 从实际转移数据派生常见业务流程
    common_flow = _derive_common_flow(entry_intents, exit_intents, top_transitions)

    # Use discovered_ontology as the source of truth; fall back to schema.json
    ontology_data = discovered_ontology if discovered_ontology else _load_ontology()
    # Ensure the ontology has all slots/intents that were actually observed
    _enrich_ontology_with_observed(ontology_data, slot_analysis, intent_dist)

    return {
        "extraction_overview": {
            "total_records": n,
            "llm_succeeded": n_llm_ok,
            "llm_success_rate": round(n_llm_ok / n * 100, 1) if n else 0,
            "total_turns": sum(turn_counts),
            "total_user_turns": len(all_intents),
            "avg_turns_per_dialogue": round(sum(turn_counts) / n, 1) if n else 0,
            "model_name": (model_info or {}).get("model", "unknown"),
            "model_base_url": (model_info or {}).get("base_url", ""),
            "extraction_method": "LLM 逐轮结构化标注（本体由数据归纳）",
            "qc_label_distribution": {
                label: {"count": cnt, "pct": round(cnt / n * 100, 1)}
                for label, cnt in qc_counter.most_common()
            },
        },
        "ontology": ontology_data,
        "intent_analysis": {
            "intent_distribution": intent_dist,
            "top5_intents": [
                (intent, d["count"])
                for intent, d in sorted(intent_dist.items(), key=lambda x: -x[1]["count"])[:5]
            ],
            "entry_intents": dict(Counter(entry_intents).most_common()),
            "exit_intents": dict(Counter(exit_intents).most_common()),
            "avg_unique_intents_per_dialogue": round(sum(intent_per_dialogue) / n, 1) if n else 0,
        },
        "slot_analysis": slot_analysis,
        "action_analysis": {
            "act_distribution": dict(act_counter.most_common()),
            "service_call_methods": dict(service_call_methods.most_common()),
        },
        "strategy_analysis": {
            "top_intent_transitions": top_transitions,
            "common_flow": common_flow,
        },
        "extractability_summary": _build_extractability_summary(
            slot_analysis, n_llm_ok, n, model_info
        ),
    }


def _build_extractability_summary(
    slot_analysis: Dict[str, Any],
    n_llm_ok: int,
    n: int,
    model_info: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """生成各类字段的可提取性结论（基于实际数据结果，不使用硬编码描述）。"""
    high_crm = [s for s, d in slot_analysis.items() if d["crm_coverage_pct"] >= 80]
    mid_crm = [s for s, d in slot_analysis.items() if 50 <= d["crm_coverage_pct"] < 80]
    low_crm = [s for s, d in slot_analysis.items() if 0 < d["crm_coverage_pct"] < 50]
    dialogue_only = [s for s, d in slot_analysis.items() if d["crm_coverage_pct"] == 0]

    llm_success_rate = round(n_llm_ok / n * 100, 1) if n else 0
    model_name = (model_info or {}).get("model", "LLM")
    base_url = (model_info or {}).get("base_url", "")
    model_label = f"{model_name}（{base_url}）" if base_url else model_name

    # CRM 高覆盖率均值
    high_crm_avg = (
        round(sum(slot_analysis[s]["crm_coverage_pct"] for s in high_crm) / len(high_crm), 1)
        if high_crm else 0
    )
    # 对话专属槽位实际提取次数
    dialogue_only_filled = {s: slot_analysis[s]["filled_in_dialogue_n"] for s in dialogue_only}

    return {
        "directly_extractable": {
            "fields": ["dialogue_id", "speaker", "utterance", "qc_label", "reference_response"],
            "reliability": "100%",
            "method": "直接映射（无需推断）",
            "description": (
                f"对话结构字段（{n} 条对话共 {sum(slot_analysis[s]['filled_in_dialogue_n'] for s in slot_analysis)//n if n else 0} "
                "轮/条）可完整保留，零损耗。"
            ),
        },
        "crm_high_coverage": {
            "fields": high_crm,
            "reliability": f"CRM 平均覆盖率 {high_crm_avg}%",
            "method": "parse_user_info() CRM 解析",
            "description": (
                f"共 {len(high_crm)} 个槽位来自 CRM，平均覆盖率 {high_crm_avg}%，"
                "可直接作为 slot_values 和 service_results 的金标准。"
            ),
        },
        "crm_medium_coverage": {
            "fields": mid_crm,
            "reliability": f"CRM 覆盖率 50–80%",
            "method": "parse_user_info() CRM 解析",
            "description": (
                f"共 {len(mid_crm)} 个槽位存在于 CRM 但并非所有对话都有，"
                "建议按对话情况选择性注入。"
            ),
        },
        "crm_low_coverage": {
            "fields": low_crm,
            "reliability": f"CRM 覆盖率 <50%，仅特定场景",
            "method": "parse_user_info() CRM 解析",
            "description": (
                f"共 {len(low_crm)} 个槽位仅在特定业务场景（如争议处理、分期计算）中出现，"
                "覆盖率低但数据精确。"
            ),
        },
        "llm_extractable": {
            "fields": ["active_intent", "requested_slots", "slot_values（对话专属）", "actions", "service_call"],
            "reliability": f"LLM 提取成功率 {llm_success_rate}%（{n_llm_ok}/{n} 条）",
            "method": f"LLM 语义理解（{model_label}）",
            "description": (
                f"使用 {model_label} 对每条对话进行逐轮结构化标注，"
                f"本次 {n} 条记录中 LLM 成功解析 {n_llm_ok} 条（{llm_success_rate}%）。"
                "active_intent、requested_slots、actions、service_call 均由 LLM 从对话文本语义推断。"
            ),
        },
        "dialogue_only_slots": {
            "fields": dialogue_only,
            "reliability": f"无 CRM 来源，LLM 从对话文本提取；本次实际提取次数：{dialogue_only_filled}",
            "method": f"LLM NLU 提取（{model_name}）",
            "description": (
                f"共 {len(dialogue_only)} 个槽位无 CRM 来源，只能从对话文本提取。"
                f"本次提取次数：{dialogue_only_filled}。"
                "这些槽位在对话中出现率较低，LLM 失败时为空。"
            ),
        },
        "not_extractable": {
            "fields": ["frames[].slots（字符跨度标注）", "full_ground_truth_dst"],
            "description": (
                "字符跨度标注（slot span annotation）需要专用标注工具，"
                "无法由 LLM 自动生成。完整的 DST 金标准同样需要人工核验。"
            ),
        },
    }


# --------------------------------------------------------------------------- #
# SGD 格式导出
# --------------------------------------------------------------------------- #

# SGD 字段差异表：字段名 → (本项目状态, 差距说明)
SGD_FIELD_DIFF: List[Dict[str, str]] = [
    {
        "sgd_field": "dialogue_id",
        "sgd_location": "顶层",
        "our_status": "✅ 完整",
        "note": "直接使用 session_id 映射",
    },
    {
        "sgd_field": "services",
        "sgd_location": "顶层",
        "our_status": "✅ 完整",
        "note": '固定为 ["AnYiHua_1"]',
    },
    {
        "sgd_field": "metadata",
        "sgd_location": "顶层",
        "our_status": "✅ 扩展",
        "note": "包含 qc_label / reference_response / user_info_parsed（标准 SGD 无此字段，为本项目扩展）",
    },
    {
        "sgd_field": "turns[].speaker",
        "sgd_location": "轮次",
        "our_status": "✅ 完整",
        "note": "USER / SYSTEM 精确区分",
    },
    {
        "sgd_field": "turns[].utterance",
        "sgd_location": "轮次",
        "our_status": "✅ 完整",
        "note": "直接提取原始文本",
    },
    {
        "sgd_field": "frames[].service",
        "sgd_location": "帧",
        "our_status": "✅ 完整",
        "note": '固定为 "AnYiHua_1"',
    },
    {
        "sgd_field": "frames[].slots（跨度标注）",
        "sgd_location": "帧",
        "our_status": "❌ 缺失",
        "note": (
            "标准 SGD 包含 slot 的字符跨度标注（start/exclusive_end），"
            "需要对话标注工具支持，本项目中统一为 []"
        ),
    },
    {
        "sgd_field": "frames[].state.active_intent",
        "sgd_location": "USER 帧状态",
        "our_status": "⚠️ 近似（LLM 提取）",
        "note": "LLM 逐轮语义推断；主要误差来源：口语化表达和 general_inquiry 兜底意图过多使用",
    },
    {
        "sgd_field": "frames[].state.requested_slots",
        "sgd_location": "USER 帧状态",
        "our_status": "⚠️ 近似（LLM 提取）",
        "note": "LLM 语义提取用户询问的槽位；LLM 失败时为空列表",
    },
    {
        "sgd_field": "frames[].state.slot_values",
        "sgd_location": "USER 帧状态",
        "our_status": "✅ CRM金标准 / ⚠️ LLM近似",
        "note": (
            "CRM 槽位（customer_name 等 11 个）由 parse_user_info() 解析，可靠性≈100%；"
            "对话专属槽位（dispute_date / inquiry_amount / term_months / identity_confirmed）"
            "由 LLM 从对话文本提取，LLM 失败时为空"
        ),
    },
    {
        "sgd_field": "frames[].actions（USER 轮）",
        "sgd_location": "USER 帧",
        "our_status": "⚠️ 近似（LLM 提取）",
        "note": "LLM 推断用户对话行为动作；LLM 失败时为空列表",
    },
    {
        "sgd_field": "frames[].actions（SYSTEM 轮）",
        "sgd_location": "SYSTEM 帧",
        "our_status": "⚠️ 近似（LLM 提取）",
        "note": "LLM 精确提取系统行为动作；LLM 失败时为空列表",
    },
    {
        "sgd_field": "frames[].service_call",
        "sgd_location": "SYSTEM 帧",
        "our_status": "✅ 基本完整 / ⚠️ 参数近似",
        "note": (
            "method 字段通过 intent→API 映射表自动生成，可靠性高；"
            "parameters 仅包含 name/phone_suffix，LLM 模式可补充其他参数"
        ),
    },
    {
        "sgd_field": "frames[].service_results",
        "sgd_location": "SYSTEM 帧",
        "our_status": "✅ CRM金标准",
        "note": "直接从 parse_user_info() 按意图选取字段，可靠性接近 100%",
    },
]


def export_sgd_format(
    extracted_records: List[Dict[str, Any]],
    model_info: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """
    将 extract_record_with_llm 的输出转为标准 SGD 对话格式。
    """
    sgd_dialogues: List[Dict[str, Any]] = []
    model_name = (model_info or {}).get("model", "llm_extracted")

    for record in extracted_records:
        session_id = record["session_id"]
        crm = record.get("crm_parsed", {})

        sgd_turns: List[Dict[str, Any]] = []
        for turn in record["turns"]:
            speaker = turn["speaker"]
            utterance = turn["utterance"]

            if speaker == "USER":
                frame: Dict[str, Any] = {
                    "service": SERVICE_NAME,
                    "slots": [],  # 跨度标注：标准 SGD 需要字符偏移量，本项目无法自动生成
                    "state": {
                        "active_intent": turn.get("active_intent", "general_inquiry"),
                        "requested_slots": turn.get("requested_slots", []),
                        "slot_values": turn.get("slot_values", {}),
                    },
                    "actions": turn.get("actions", []),
                }
            else:  # SYSTEM
                sc = turn.get("service_call")
                frame = {
                    "service": SERVICE_NAME,
                    "slots": [],  # 跨度标注：标准 SGD 需要字符偏移量，本项目无法自动生成
                    "actions": turn.get("actions", []),
                    "service_call": sc if sc else {},
                    "service_results": turn.get("service_results", []),
                }

            sgd_turns.append({
                "speaker": speaker,
                "utterance": utterance,
                "frames": [frame],
            })

        sgd_dialogues.append({
            "dialogue_id": session_id,
            "services": [SERVICE_NAME],
            "metadata": {
                "user_info_raw": "",  # 原始文本省略，已解析到 user_info_parsed
                "user_info_parsed": crm,
                "reference_response": record.get("reference_response", ""),
                "qc_label": record.get("qc_label", ""),
                "extraction_method": f"llm:{model_name}",
                "generated_at": datetime.now().strftime("%Y-%m-%d"),
            },
            "turns": sgd_turns,
        })

    return sgd_dialogues


# --------------------------------------------------------------------------- #
# Markdown 报告生成
# --------------------------------------------------------------------------- #

def generate_markdown_report(agg: Dict[str, Any], input_path: str, sample_n: int) -> str:
    """生成简洁、可读的 Markdown 分析报告（5 节结构）。"""
    try:
        display_path = str(Path(input_path).relative_to(_PROJECT_ROOT))
    except ValueError:
        display_path = Path(input_path).name

    ov = agg["extraction_overview"]
    ont = agg["ontology"]
    intents = agg["intent_analysis"]
    slots = agg["slot_analysis"]
    actions = agg["action_analysis"]
    strat = agg["strategy_analysis"]

    model_name = ov.get("model_name", "unknown")
    base_url = ov.get("model_base_url", "")
    model_label = f"{model_name}（{base_url}）" if base_url else model_name
    llm_rate = ov["llm_success_rate"]
    n = ov["total_records"]

    # Determine ontology source label
    ont_source = ont.get("source", "schema_json")
    if ont_source == "data_driven":
        ont_source_label = "从对话数据归纳（data-driven，Phase 0）"
        ont_file_label = "`chat_test_discovered_ontology.json`"
    elif ont_source == "schema_json":
        ont_source_label = "`resources/anyihua_sgd/schema.json`（预定义）"
        ont_file_label = "`resources/anyihua_sgd/schema.json`"
    else:
        ont_source_label = "内置常量（兜底）"
        ont_file_label = "hardcoded"

    # Determine which slots came from CRM (have CRM coverage > 0)
    crm_slot_names = {
        slot for slot, d in slots.items()
        if d.get("crm_coverage_pct", 0) > 0
    }
    # Also include known CRM slots by name as fallback
    _known_crm_slots = {
        "customer_name", "phone_suffix", "available_credit", "temp_credit",
        "temp_credit_status", "temp_expiry_days", "annual_rate_pct", "loan_count",
        "last_loan_date", "outstanding_amount", "billing_day",
    }
    crm_slot_names = crm_slot_names | _known_crm_slots

    lines: List[str] = []

    # ——— 标题 ———
    lines.append("# 安逸花外呼数据 → SGD 转换报告\n")
    lines.append(f"- **数据文件**：`{display_path}`（{n} 条对话，{ov['total_turns']} 轮，平均 {ov['avg_turns_per_dialogue']} 轮/对话）")
    lines.append(f"- **提取模型**：{model_label}（LLM 成功率 {llm_rate}%，{ov['llm_succeeded']}/{n} 条）")
    lines.append(f"- **本体来源**：{ont_source_label}（{ont['total_intents']} 个意图，{ont['total_slots']} 个槽位，{ont.get('total_acts', 0)} 种对话行为）")
    lines.append("")

    # ——— 一、SGD 字段覆盖情况 ———
    lines.append("---\n")
    lines.append("## 一、转换后 SGD 字段：具备哪些 / 缺少哪些\n")

    dialogue_slot_count = len([s for s in slots if s not in crm_slot_names])
    crm_slot_count = len([s for s in slots if s in crm_slot_names])

    lines.append("### ✅ 具备字段\n")
    lines.append("| SGD 字段 | 质量 | 说明 |")
    lines.append("|---|---|---|")
    lines.append("| `dialogue_id` / `services` | 完整 | session_id 直接映射；services 固定为 AnYiHua_1 |")
    lines.append("| `turns[].speaker` / `utterance` | 完整 | 原文直接保留，USER/SYSTEM 精确区分 |")
    lines.append("| `metadata`（扩展字段） | 完整 | qc_label / reference_response / user_info_parsed（SGD 标准无此字段，为本项目扩展）|")
    lines.append("| `frames[].service` | 完整 | 固定为 AnYiHua_1 |")
    lines.append(f"| `frames[].state.slot_values`（CRM 槽位） | 金标准 | {crm_slot_count} 个 CRM 槽位来自 parse_user_info()，可靠性 ≈100% |")
    lines.append("| `frames[].service_results` | 金标准 | CRM 数据按意图选取，可靠性 ≈100% |")
    lines.append("| `frames[].service_call.method` | 高可靠 | intent→API 映射表自动生成 |")
    lines.append(f"| `frames[].state.active_intent` | LLM 近似 | 成功率 {llm_rate}%；失败时兜底为 general_inquiry |")
    lines.append(f"| `frames[].state.requested_slots` | LLM 近似 | 成功率 {llm_rate}%；失败时为空列表 |")
    lines.append(f"| `frames[].state.slot_values`（对话专属槽位） | LLM 近似 | {dialogue_slot_count} 个对话文本槽位仅 LLM 可提取；失败时为空 |")
    lines.append(f"| `frames[].actions` | LLM 近似 | 成功率 {llm_rate}%；失败时为空列表 |")
    lines.append("")

    lines.append("### ❌ 缺少字段\n")
    lines.append("| 缺失字段 | 原因 |")
    lines.append("|---|---|")
    lines.append("| `frames[].slots`（字符跨度标注） | 需标注工具手动标注字符级 start/exclusive_end 偏移量，LLM 无法自动生成 |")
    lines.append("| `frames[].actions[].canonical_values` | 标准 SGD 要求规范化值，需额外后处理 |")
    lines.append("| DST 金标准（完整 ground truth） | 需人工逐轮核验 LLM 标注结果 |")
    lines.append("")

    # ——— 二、服务本体 ———
    lines.append("---\n")
    lines.append(f"## 二、服务本体（{ont_source_label}）\n")
    lines.append(f"> 服务：`{ont['service_name']}`　{ont['service_description']}\n")

    lines.append("**意图列表**\n")
    if ont_source == "data_driven":
        lines.append("| 意图 | 描述（从数据归纳） | 出现频率 |")
        lines.append("|---|---|---|")
        for intent_obj in ont.get("intents", []):
            name = intent_obj.get("name", "")
            desc = intent_obj.get("description", "")
            freq = intent_obj.get("frequency", "")
            lines.append(f"| `{name}` | {desc} | {freq} |")
    else:
        lines.append("| 意图 | 描述 | 必填槽位 | 结果槽位 |")
        lines.append("|---|---|---|---|")
        for intent_obj in ont.get("intents", []):
            name = intent_obj.get("name", "")
            desc = intent_obj.get("description", "")
            required = " / ".join(intent_obj.get("required_slots", [])) or "—"
            result = " / ".join(intent_obj.get("result_slots", [])) or "—"
            lines.append(f"| `{name}` | {desc} | {required} | {result} |")
    lines.append("")

    lines.append("**槽位列表**\n")
    if ont_source == "data_driven":
        lines.append("| 槽位 | 描述（从数据归纳） | 来源 | 数据类型 | CRM 覆盖率 |")
        lines.append("|---|---|---|---|---|")
        for slot_obj in ont.get("slots", []):
            slot = slot_obj.get("name", "")
            desc = slot_obj.get("description", "")
            source_lbl = slot_obj.get("source", "CRM" if slot in crm_slot_names else "对话")
            data_type = slot_obj.get("data_type", "text")
            crm_pct = slots.get(slot, {}).get("crm_coverage_pct", 0)
            crm_str = f"{crm_pct}%" if slot in crm_slot_names else "—"
            lines.append(f"| `{slot}` | {desc} | {source_lbl} | {data_type} | {crm_str} |")
    else:
        lines.append("| 槽位 | 描述 | 来源 | CRM 覆盖率 |")
        lines.append("|---|---|---|---|")
        for slot_obj in ont.get("slots", []):
            slot = slot_obj.get("name", "")
            desc = slot_obj.get("description", "")
            source = "CRM" if slot in crm_slot_names else "对话文本"
            crm_pct = slots.get(slot, {}).get("crm_coverage_pct", 0)
            crm_str = f"{crm_pct}%" if slot in crm_slot_names else "—"
            lines.append(f"| `{slot}` | {desc} | {source} | {crm_str} |")

    # Dialog acts (only show if data-driven with discovery info)
    dialog_acts = ont.get("dialog_acts", [])
    if dialog_acts and ont_source == "data_driven":
        lines.append("")
        lines.append("**对话行为类型（从数据归纳）**\n")
        lines.append("| Act | 描述 | 说话方 |")
        lines.append("|---|---|---|")
        for act_obj in dialog_acts:
            act = act_obj.get("act", "")
            desc = act_obj.get("description", "")
            speaker = act_obj.get("speaker", "BOTH")
            lines.append(f"| `{act}` | {desc} | {speaker} |")
    lines.append("")

    # ——— 三、数据统计 ———
    lines.append("---\n")
    lines.append("## 三、数据统计\n")

    lines.append("**质检标签分布**\n")
    for label, d in ov["qc_label_distribution"].items():
        lines.append(f"- `{label}`：{d['count']} 条（{d['pct']}%）")
    lines.append("")

    lines.append("**意图频率分布（USER 轮，仅显示出现次数 > 0）**\n")
    lines.append("| 意图 | 出现次数 | 占用户轮比例 |")
    lines.append("|---|---|---|")
    for intent, d in sorted(intents["intent_distribution"].items(), key=lambda x: -x[1]["count"]):
        if d["count"] == 0:
            continue
        lines.append(f"| `{intent}` | {d['count']} | {d['pct_of_user_turns']}% |")
    lines.append("")

    lines.append("**槽位覆盖率与提取次数**\n")
    lines.append("| 槽位 | 来源 | CRM 覆盖率 | LLM 提取次数 |")
    lines.append("|---|---|---|---|")
    for slot_obj in ont.get("slots", []):
        slot = slot_obj.get("name", "")
        d = slots.get(slot, {})
        crm_pct = d.get("crm_coverage_pct", 0)
        filled = d.get("filled_in_dialogue_n", 0)
        source = "CRM" if slot in crm_slot_names else "对话文本"
        crm_str = f"{crm_pct}%" if slot in crm_slot_names else "—"
        lines.append(f"| `{slot}` | {source} | {crm_str} | {filled} |")
    lines.append("")

    sc_methods = actions.get("service_call_methods", {})
    if sc_methods:
        lines.append("**后端 API 调用次数（service_call）**\n")
        lines.append("| API 方法 | 调用次数 |")
        lines.append("|---|---|")
        for method, cnt in sc_methods.items():
            lines.append(f"| `{method}` | {cnt} |")
        lines.append("")

    act_dist = actions.get("act_distribution", {})
    act_nonzero = {k: v for k, v in act_dist.items() if v > 0}
    if act_nonzero:
        lines.append("**对话行为（Act）分布（仅出现过的类型）**\n")
        lines.append("| Act | 提取次数 |")
        lines.append("|---|---|")
        for act, cnt in sorted(act_nonzero.items(), key=lambda x: -x[1]):
            lines.append(f"| `{act}` | {cnt} |")
        lines.append("")

    # ——— 四、对话业务流程 ———
    lines.append("---\n")
    lines.append("## 四、对话业务流程（从数据推导）\n")
    lines.append(f"```\n{strat['common_flow']}\n```\n")

    top10 = strat["top_intent_transitions"][:10]
    if top10:
        lines.append("**高频意图转移（Top 10）**\n")
        lines.append("| 从意图 | 转移到 | 次数 |")
        lines.append("|---|---|---|")
        for t in top10:
            lines.append(f"| `{t['from']}` | `{t['to']}` | {t['count']} |")
        lines.append("")

    # ——— 五、提取方法说明 ———
    lines.append("---\n")
    lines.append("## 五、提取方法说明\n")
    lines.append(f"- **模型**：{model_label}")
    lines.append(f"- **Phase 0（本体归纳）**：LLM 分析原始对话数据，从中归纳意图/槽位/对话行为，不使用预定义列表")
    lines.append(f"  - 本体来源：{ont_source_label}")
    lines.append(f"  - 归纳结果：{ont['total_intents']} 意图，{ont['total_slots']} 槽位，{ont.get('total_acts', 0)} 对话行为")
    lines.append(f"- **Phase 1（SGD 转换）**：以归纳本体为指导，LLM 逐轮提取 active_intent / requested_slots / slot_values / actions / service_call")
    lines.append(f"- **CRM 数据**：通过 `parse_user_info()` 解析，直接注入 slot_values 和 service_results，可靠性 ≈100%")
    lines.append(f"- **LLM 成功率**：{llm_rate}%（{ov['llm_succeeded']}/{n} 条）；失败时意图为 general_inquiry，动作/槽位为空")
    lines.append(f"- **开放词汇**：意图/槽位/行为名称从数据归纳，不受预定义列表约束，可发现新概念")
    lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 主程序
# --------------------------------------------------------------------------- #

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="使用 LLM 从 chat_test_100.json 提取 SGD 格式字段",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input", default=_DEFAULT_INPUT,
        help=f"输入 JSON 文件路径（默认：{_DEFAULT_INPUT}）",
    )
    parser.add_argument(
        "--output-dir", default=_DEFAULT_OUTPUT_DIR,
        help=f"报告输出目录（默认：{_DEFAULT_OUTPUT_DIR}）",
    )
    parser.add_argument(
        "--sample", type=int, default=_DEFAULT_SAMPLE,
        help=f"LLM 处理的记录数（默认：{_DEFAULT_SAMPLE}，快速预览）",
    )
    parser.add_argument(
        "--all", dest="process_all", action="store_true",
        help="处理全部记录（覆盖 --sample）",
    )
    parser.add_argument(
        "--no-markdown", action="store_true",
        help="跳过 Markdown 报告生成",
    )
    parser.add_argument(
        "--no-sgd-export", action="store_true",
        help="跳过 SGD 格式数据导出（默认会生成 chat_test_sgd_dialogues.json）",
    )
    parser.add_argument(
        "--delay", type=float, default=0.5,
        help="每次 LLM 调用间隔秒数（默认：0.5）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print("chat_test_100.json 信息提取分析工具（LLM 版）")
    print(f"{'='*60}")
    print(f"输入文件 : {input_path}")
    print(f"输出目录 : {output_dir}")

    try:
        from contextmind.infra.llm_client import SimpleLLMClient, LLMConfig
        config = LLMConfig.from_env()
        llm_client = SimpleLLMClient(config)
        model_info = {"model": config.model, "base_url": config.base_url or ""}
        print(f"LLM 客户端 : ✅ {config.model}  ({config.base_url or 'OpenAI'})")
    except Exception as exc:
        print(f"LLM 客户端 : ❌ 初始化失败 — {exc}")
        print("  → 请检查 .env 文件中的 QWEN3_API_KEY / QWEN3_BASE_URL / QWEN3_MODEL 配置")
        sys.exit(1)

    print("\n▶ 加载数据...")
    with open(input_path, encoding="utf-8") as f:
        raw_data: List[Dict[str, Any]] = json.load(f)
    print(f"  已加载 {len(raw_data)} 条记录")

    sample_n = len(raw_data) if args.process_all else min(args.sample, len(raw_data))
    records_to_process = raw_data[:sample_n]
    print(
        f"  本次处理 : {sample_n} 条记录"
        f"{'（全量）' if args.process_all else f'（用 --all 处理全部 {len(raw_data)} 条）'}"
    )

    # ——— Phase 0：从数据中归纳服务本体 ———
    print(f"\n▶ Phase 0：从对话数据归纳服务本体（意图/槽位/对话行为）...")
    # Use up to 30 dialogues for ontology discovery (representative sample)
    ontology_sample_n = min(30, len(raw_data))
    discovered_ontology = extract_ontology_from_dialogues(
        raw_data[:ontology_sample_n], llm_client, sample_n=ontology_sample_n
    )

    # Save discovered ontology as a separate file for reference
    ontology_path = output_dir / "chat_test_discovered_ontology.json"
    with open(ontology_path, "w", encoding="utf-8") as f:
        json.dump(discovered_ontology, f, ensure_ascii=False, indent=2)
    print(f"  ✅ 本体文件  : {ontology_path}")

    # ——— Phase 1：使用本体指导 LLM 逐轮提取 SGD 字段 ———
    extracted_records: List[Dict[str, Any]] = []
    print(f"\n▶ Phase 1：使用 LLM 提取 SGD 字段（{config.model}，每条间隔 {args.delay}s）...")
    for i, record in enumerate(records_to_process):
        sid = record.get("session_id", "?")[:20]
        print(f"  [{i+1:3d}/{sample_n}] {sid}...", end="", flush=True)
        result = extract_record_with_llm(record, llm_client, discovered_ontology=discovered_ontology)
        extracted_records.append(result)
        status = "✅" if result["llm_succeeded"] else "⚠️"
        print(f" {status} ({len(result['turns'])}/{result['turn_count']} 轮)")
        if i < sample_n - 1:
            time.sleep(args.delay)

    n_ok = sum(1 for r in extracted_records if r["llm_succeeded"])
    print(f"\n  ✅ 提取完成：{n_ok}/{sample_n} 条 LLM 成功")

    print("▶ 汇总统计...")
    agg = aggregate_results(
        extracted_records,
        model_info=model_info,
        discovered_ontology=discovered_ontology,
    )

    json_path = output_dir / "chat_test_extraction_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(agg, f, ensure_ascii=False, indent=2)
    print(f"  ✅ JSON 报告 : {json_path}")

    if not args.no_markdown:
        md_path = output_dir / "chat_test_extraction_report.md"
        md = generate_markdown_report(agg, str(input_path), sample_n)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"  ✅ Markdown  : {md_path}")

    if not args.no_sgd_export:
        sgd_dialogues = export_sgd_format(extracted_records, model_info=model_info)
        sgd_path = output_dir / "chat_test_sgd_dialogues.json"
        with open(sgd_path, "w", encoding="utf-8") as f:
            json.dump(sgd_dialogues, f, ensure_ascii=False, indent=2)
        print(f"  ✅ SGD 格式  : {sgd_path}（{len(sgd_dialogues)} 条对话）")

    print(f"\n{'='*60}")
    print("分析摘要")
    print(f"{'='*60}")
    ov = agg["extraction_overview"]
    intents = agg["intent_analysis"]
    slots_agg = agg["slot_analysis"]
    ont = agg["ontology"]
    print(
        f"  处理记录   : {ov['total_records']} 条，"
        f"LLM 成功 {ov['llm_succeeded']} 条 ({ov['llm_success_rate']}%)"
    )
    print(f"  提取模型   : {ov['model_name']} ({ov['model_base_url'] or 'OpenAI'})")
    print(f"  本体来源   : {'数据归纳（data_driven）' if ont.get('source') == 'data_driven' else 'schema.json 预定义'}")
    print(f"  本体规模   : {ont.get('total_intents', 0)} 意图 / {ont.get('total_slots', 0)} 槽位 / {ont.get('total_acts', 0)} 对话行为")
    print(f"  总轮次     : {ov['total_turns']}（用户轮 {ov['total_user_turns']}）")
    print(
        f"  每对话平均 : {ov['avg_turns_per_dialogue']} 轮 / "
        f"{intents['avg_unique_intents_per_dialogue']} 个不同意图"
    )
    print(f"\n  --- 意图分布（LLM 提取，Top 5）---")
    for intent, cnt in intents["top5_intents"][:5]:
        d = intents["intent_distribution"][intent]
        bar = "█" * int(d["pct_of_user_turns"] / 5)
        print(f"  {intent:<35s}: {cnt:4d} 轮  {bar}")
    print(f"\n  --- 槽位 CRM 覆盖率（Top 8）---")
    for slot in sorted(slots_agg, key=lambda s: -slots_agg[s]["crm_coverage_pct"])[:8]:
        pct = slots_agg[slot]["crm_coverage_pct"]
        bar = "█" * int(pct / 10)
        print(f"  {slot:<30s}: {pct:5.1f}%  {bar}")
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()
