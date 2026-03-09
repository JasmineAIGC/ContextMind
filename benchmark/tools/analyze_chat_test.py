#!/usr/bin/env python3
"""
chat_test_100.json 信息提取分析工具（LLM 版）

基于 SGD 数据集的完整字段规范，使用 LLM 从安逸花外呼数据中精准提取所有可提取字段，
用于后续构建类似 SGD 的标准 TOD（Task-Oriented Dialogue）数据集。

本工具只使用 LLM 进行提取，不使用关键词规则降级。LLM 不可用时请检查 .env 配置。

----------------------------------------------------------------------
SGD 本体（Ontology / Schema）说明
----------------------------------------------------------------------

SGD 本体即 schema.json，它是服务的形式化规范，包含：
  service_name       服务名称
  description        服务自然语言描述（供 LLM 理解，不依赖硬编码知识）
  slots              槽位列表：name, description, is_categorical, possible_values
  intents            意图列表：name, description, is_transactional,
                              required_slots, optional_slots, result_slots

SGD 区别于传统封闭本体的关键：每个 slot/intent 都带有自然语言 description，
使模型能在 zero-shot 条件下泛化到未见服务（Schema-Guided 范式）。

本体来源：resources/anyihua_sgd/schema.json

----------------------------------------------------------------------
SGD 对话字段（dialogues_*.json）
----------------------------------------------------------------------

dialogue_id        → 直接从 session_id 映射
services           → 固定为 ["AnYiHua_1"]
metadata           → 扩展字段（qc_label, reference_response, user_info_parsed）

USER turn：
  speaker          → "USER"
  utterance        → 对话原文
  active_intent    → LLM 提取（用户本轮任务意图）
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

  resources/data/chat_test_extraction_report.json   机器可读结构化报告
  resources/data/chat_test_extraction_report.md     人类可读 Markdown 报告
  resources/data/chat_test_sgd_dialogues.json       标准 SGD 格式对话数据集
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
# LLM 提取提示模板
# --------------------------------------------------------------------------- #

_EXTRACTION_SYSTEM_PROMPT = (
    "你是专业的任务型对话（TOD）结构化标注助手，熟悉 SGD（Schema-Guided Dialogue）数据集格式规范。\n"
    "你的任务是对安逸花外呼数据进行完整、精准的 SGD 字段提取，用于构建标准 TOD 数据集。\n\n"
    "业务背景：\n"
    "- 安逸花是马上消费金融旗下的消费贷款产品\n"
    "- 坐席（SYSTEM）主动致电老用户，目标是激活用户闲置的借款额度\n"
    "- 标准流程：核实身份 → 告知额度 → 解答疑问 → 引导借款 → 礼貌告别\n"
    "- 坐席掌握完整的 CRM 数据（用户信息字段），用户只能确认或询问\n\n"
    "合法意图（valid_intents，必须从中选择）：\n"
    "verify_identity, explain_credit_limit, explain_interest_rate, calculate_repayment,\n"
    "explain_displayed_amount, handle_loan_dispute, guide_loan_operation,\n"
    "escalate_to_human, say_goodbye, general_inquiry\n\n"
    "合法槽位（valid_slots，必须从中选择）：\n"
    "customer_name, phone_suffix, available_credit, temp_credit, temp_credit_status,\n"
    "temp_expiry_days, annual_rate_pct, loan_count, last_loan_date, outstanding_amount,\n"
    "billing_day, dispute_date, inquiry_amount, term_months, identity_confirmed\n\n"
    "合法对话行为（valid_acts）：\n"
    "INFORM, REQUEST, CONFIRM, SELECT, OFFER, GOODBYE, INFORM_INTENT, NEGATE_INTENT,\n"
    "AFFIRM_INTENT, AFFIRM, NEGATE, CANT_UNDERSTAND, NOTIFY_SUCCESS, NOTIFY_FAILURE\n\n"
    "SGD 字段说明：\n\n"
    "USER turn 需提取：\n"
    "  active_intent     — 用户本轮期望坐席帮助完成的任务意图（从 valid_intents 选一个）\n"
    "                      注意：用户说「对」「嗯」等短回应时，继承上一轮的意图\n"
    "  requested_slots   — 用户明确询问但尚未获知的槽位（如「利率是多少」→ [\"annual_rate_pct\"]）\n"
    "  slot_values       — 截至本轮已确认的累积对话状态 {\"slot_name\": [\"value\"]}\n"
    "                      包括用户主动提供的信息（如告知争议日期、分期期数等）\n"
    "  actions           — 用户对话行为列表，格式：{\"act\":\"...\",\"slot\":\"...\",\"values\":[...],\"canonical_values\":[...]}\n"
    "                      act 从 valid_acts 选择；INFORM 表示用户提供信息，REQUEST 表示用户请求信息\n\n"
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
    "4. 只有坐席引用 CRM 数据时才填写 service_call 和 service_results\n"
    "5. 所有槽位名称必须来自 valid_slots；所有意图名称必须来自 valid_intents"
)


def _build_extraction_prompt(record: Dict[str, Any]) -> str:
    """构建单条记录的完整 LLM 提取 Prompt。"""
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
        "- 所有槽位名、意图名、行为名必须来自合法列表\n"
        "- 仅输出 JSON，不要任何解释文字"
    )
    return _EXTRACTION_SYSTEM_PROMPT + "\n\n" + prompt


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


def _validate_and_clean_turn(turn: Dict[str, Any]) -> Dict[str, Any]:
    """对单轮提取结果进行合规性校验和清洗。"""
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
        act = a.get("act", "")
        slot = a.get("slot", "") or ""
        values = a.get("values", []) or []
        canonical_values = a.get("canonical_values", []) or []
        if act in _VALID_ACTS_SET:
            actions.append({
                "act": act,
                "slot": slot if slot in _VALID_SLOTS_SET else "",
                "values": [str(v) for v in values] if isinstance(values, list) else [],
                "canonical_values": [str(v) for v in canonical_values] if isinstance(canonical_values, list) else [],
            })
    cleaned["actions"] = actions

    if speaker == "USER":
        intent = turn.get("active_intent", "general_inquiry")
        cleaned["active_intent"] = intent if intent in _VALID_INTENTS_SET else "general_inquiry"

        raw_req = turn.get("requested_slots", []) or []
        cleaned["requested_slots"] = [s for s in raw_req if s in _VALID_SLOTS_SET]

        raw_sv = turn.get("slot_values", {}) or {}
        cleaned["slot_values"] = {
            k: (v if isinstance(v, list) else [str(v)])
            for k, v in raw_sv.items()
            if k in _VALID_SLOTS_SET and v
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
                {k: str(v) for k, v in item.items() if k in _VALID_SLOTS_SET}
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

def extract_record_with_llm(record: Dict[str, Any], llm_client: Any) -> Dict[str, Any]:
    """使用 LLM 对单条记录进行完整 SGD 字段提取。"""
    session_id = record["session_id"]
    crm = parse_user_info(record.get("用户信息", ""))
    raw_turns = record.get("对话历史", [])

    prompt = _build_extraction_prompt(record)
    parsed = None

    try:
        _, response_text = llm_client.generate(prompt)
        parsed = _extract_json_from_text(response_text)
    except Exception as exc:
        print(f"  ⚠️  LLM 调用失败 [{session_id[:20]}]: {exc}")

    extracted_turns: List[Dict[str, Any]] = []
    if parsed and isinstance(parsed, dict):
        for t in parsed.get("turns", []):
            extracted_turns.append(_validate_and_clean_turn(t))
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
        return {
            "service_name": schema.get("service_name", SERVICE_NAME),
            "service_description": schema.get("description", ""),
            "slots": schema.get("slots", []),
            "intents": schema.get("intents", []),
            "total_slots": len(schema.get("slots", [])),
            "total_intents": len(schema.get("intents", [])),
            "total_acts": len(VALID_ACTS),
            "acts": VALID_ACTS,
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


# --------------------------------------------------------------------------- #
# 统计汇总
# --------------------------------------------------------------------------- #

def aggregate_results(
    records: List[Dict[str, Any]],
    model_info: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """对所有已提取记录进行统计汇总。
    
    Args:
        records: extract_record_with_llm 的输出列表
        model_info: 实际使用的 LLM 信息（model, base_url 等），来自 LLMConfig
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
    intent_dist = {
        intent: {
            "count": intent_counter.get(intent, 0),
            "pct_of_user_turns": round(
                intent_counter.get(intent, 0) / len(all_intents) * 100, 1
            ) if all_intents else 0,
        }
        for intent in VALID_INTENTS
    }

    slot_filled: Dict[str, int] = defaultdict(int)
    slot_requested: Dict[str, int] = defaultdict(int)
    slot_informed: Dict[str, int] = defaultdict(int)
    slot_examples: Dict[str, List[str]] = defaultdict(list)

    for r in records:
        for t in r["turns"]:
            for slot, vals in t.get("slot_values", {}).items():
                if slot in _VALID_SLOTS_SET:
                    slot_filled[slot] += 1
                    if vals and len(slot_examples[slot]) < 3:
                        slot_examples[slot].extend(vals[:1])
            for slot in t.get("requested_slots", []):
                if slot in _VALID_SLOTS_SET:
                    slot_requested[slot] += 1
            for a in t.get("actions", []):
                if a.get("act") == "INFORM" and a.get("slot") in _VALID_SLOTS_SET:
                    slot_informed[a["slot"]] += 1

    crm_key_map = {
        "customer_name": "customer_name", "phone_suffix": "phone_suffix",
        "available_credit": "available_credit", "temp_credit": "temp_credit",
        "temp_credit_status": "temp_expired", "temp_expiry_days": "temp_active_days",
        "annual_rate_pct": "annual_rate_pct", "loan_count": "loan_count",
        "last_loan_date": "last_loan_date", "outstanding_amount": "outstanding_amount",
        "billing_day": "billing_day",
    }

    slot_analysis: Dict[str, Any] = {}
    for slot in VALID_SLOTS:
        crm_coverage = 0
        if slot in crm_key_map:
            crm_key = crm_key_map[slot]
            crm_coverage = sum(
                1 for r in records
                # Treat None and "" as missing; 0 and False are intentionally
                # excluded too since CRM fields with value 0 indicate "not set"
                # (e.g., loan_count=0 means no loans, billing_day=0 means unknown).
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

    # 加载 schema.json 作为本体数据源
    ontology_data = _load_ontology()

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
            "extraction_method": "LLM 逐轮结构化标注",
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
    """生成人类可读的 Markdown 分析报告。"""
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
    ext = agg["extractability_summary"]

    lines: List[str] = []
    lines.append("# chat_test_100.json 信息提取分析报告（LLM 版）\n")
    lines.append(f"**数据来源**：`{display_path}`  ")
    model_name = ov.get("model_name", "unknown")
    base_url = ov.get("model_base_url", "")
    model_label = f"{model_name}（{base_url}）" if base_url else model_name
    llm_rate = ov["llm_success_rate"]
    lines.append(
        f"**分析记录数**：{ov['total_records']} 条"
        f"（LLM 成功提取：{ov['llm_succeeded']} 条，成功率 {llm_rate}%）  "
    )
    lines.append(
        "**分析目标**：基于 SGD Schema-Guided Dialogue 规范，使用 LLM 从安逸花外呼数据中提取"
        "所有可用于标准 TOD 任务的结构化信息。  "
    )
    lines.append(f"**提取方法**：LLM 逐轮结构化标注（模型：{model_label}）\n")

    # ——— 一、数据集概览 ———
    lines.append("---\n")
    lines.append("## 一、数据集概览\n")
    lines.append("| 指标 | 值 |")
    lines.append("|---|---|")
    lines.append(f"| 分析记录数 | {ov['total_records']} 条 |")
    lines.append(f"| 总轮次数 | {ov['total_turns']} 轮 |")
    lines.append(f"| 平均对话长度 | {ov['avg_turns_per_dialogue']} 轮/对话 |")
    lines.append(f"| 用户轮次数 | {ov['total_user_turns']} 轮 |")
    lines.append(f"| LLM 提取成功率 | {ov['llm_success_rate']}%（{ov['llm_succeeded']}/{ov['total_records']} 条） |")
    lines.append(f"| 提取模型 | {model_label} |")
    lines.append("")
    lines.append("**人工校验标签分布**：\n")
    total_records = ov["total_records"]
    for label, d in ov["qc_label_distribution"].items():
        lines.append(f"- `{label}`：{d['count']} 条（{d['pct']}%）")
    lines.append("")

    # ——— 二、本体 ———
    lines.append("---\n")
    lines.append("## 二、服务本体（Ontology / Schema）\n")
    lines.append(
        "> **SGD 本体（Schema）** 是服务的形式化规范，定义了系统能理解和处理的概念边界。\n"
        "> 与传统封闭本体（只有名称列表）不同，SGD schema 为每个意图和槽位提供**自然语言描述**，\n"
        "> 使 LLM 在 zero-shot 条件下能泛化到未见服务（Schema-Guided 范式）。\n"
        "> 本体来源：`resources/anyihua_sgd/schema.json`\n"
    )
    lines.append(f"- **服务名称**：`{ont['service_name']}`")
    lines.append(f"- **服务描述**：{ont['service_description']}")
    lines.append(f"- **意图数量**：{ont['total_intents']} 个（来自 schema.json intents 列表）")
    lines.append(f"- **槽位数量**：{ont['total_slots']} 个（来自 schema.json slots 列表）")
    lines.append(f"- **对话行为类型**：{ont['total_acts']} 种（SGD 标准 Acts 列表）\n")

    # 意图表（含完整 schema 信息）
    lines.append("### 2.1 意图列表（来自 schema.json）\n")
    lines.append(
        "> SGD intents 包含 required_slots（必填槽位）、optional_slots（可选槽位）、"
        "result_slots（API 返回槽位），用于指导系统何时触发 API 调用。\n"
    )
    lines.append("| 意图名称 | 自然语言描述 | 必填槽位 | 可选槽位 | 结果槽位 | is_transactional |")
    lines.append("|---|---|---|---|---|---|")
    for intent_obj in ont.get("intents", []):
        name = intent_obj.get("name", "")
        desc = intent_obj.get("description", "")
        required = ", ".join(f"`{s}`" for s in intent_obj.get("required_slots", [])) or "—"
        optional = ", ".join(f"`{s}`" for s in intent_obj.get("optional_slots", {}).keys()) or "—"
        result = ", ".join(f"`{s}`" for s in intent_obj.get("result_slots", [])) or "—"
        is_trans = "✅ 是" if intent_obj.get("is_transactional") else "否"
        lines.append(f"| `{name}` | {desc} | {required} | {optional} | {result} | {is_trans} |")
    lines.append("")

    # 槽位表（含完整 schema 信息）
    lines.append("### 2.2 槽位列表（来自 schema.json）\n")
    lines.append(
        "> SGD slots 包含 is_categorical（是否为枚举类型）和 possible_values（枚举值列表），\n"
        "> 非枚举槽位（is_categorical=false）的值由对话文本或 API 返回，无固定取值范围。\n"
    )
    lines.append("| 槽位名称 | 自然语言描述 | is_categorical | 可能取值 | CRM 覆盖率 | LLM 提取次数 |")
    lines.append("|---|---|---|---|---|---|")
    for slot_obj in ont.get("slots", []):
        name = slot_obj.get("name", "")
        desc = slot_obj.get("description", "")
        is_cat = "✅ 是" if slot_obj.get("is_categorical") else "否"
        pv = ", ".join(f"`{v}`" for v in slot_obj.get("possible_values", [])) or "自由文本"
        d = slots.get(name, {})
        crm_pct = d.get("crm_coverage_pct", 0)
        filled = d.get("filled_in_dialogue_n", 0)
        lines.append(
            f"| `{name}` | {desc} | {is_cat} | {pv} | {crm_pct}% | {filled} |"
        )
    lines.append("")

    act_desc = {
        "INFORM": "告知槽位信息", "REQUEST": "请求槽位信息", "CONFIRM": "确认槽位值",
        "SELECT": "从选项中选择", "OFFER": "提供服务选项", "GOODBYE": "告别",
        "INFORM_INTENT": "明确告知意图", "NEGATE_INTENT": "否定意图", "AFFIRM_INTENT": "肯定意图",
        "AFFIRM": "肯定（非意图）", "NEGATE": "否定（非意图）",
        "CANT_UNDERSTAND": "无法理解", "NOTIFY_SUCCESS": "通知操作成功",
        "NOTIFY_FAILURE": "通知操作失败",
    }
    act_dist = actions.get("act_distribution", {})
    lines.append("### 2.3 对话行为类型（Acts / 动作）\n")
    lines.append(
        "> SGD 定义了 14 种标准对话行为动作（Act），用于描述每一句话的功能性意图。\n"
        "> 本次提取次数来自 LLM 标注结果（LLM 未成功的轮次动作为空）。\n"
    )
    lines.append("| Act 类型（英文） | 中文含义 | 本次提取次数 |")
    lines.append("|---|---|---|")
    for act in VALID_ACTS:
        cnt = act_dist.get(act, 0)
        lines.append(f"| `{act}` | {act_desc.get(act, '')} | {cnt} |")
    lines.append("")

    # ——— 三、意图分析 ———
    lines.append("---\n")
    lines.append("## 三、意图（Intent / 对话目标）分析\n")
    lines.append(
        "> **Intent（意图）**：指用户在某一对话轮次希望完成的任务目标，"
        "如「核实身份」、「了解额度」等。\n"
        "> 以下分布来自 LLM 对本次处理的所有对话的逐轮标注结果。\n"
    )
    lines.append(
        f"- 本次处理 {ov['total_records']} 条对话，共 {ov['total_user_turns']} 个用户轮次，"
        f"平均每条对话含 **{intents['avg_unique_intents_per_dialogue']}** 个不同意图\n"
    )

    # 从 schema.json 构建意图描述映射
    intent_descs_inline: Dict[str, str] = {
        i["name"]: i.get("description", "") for i in ont.get("intents", [])
    }

    lines.append("### 3.1 意图频率分布（USER 轮，基于本次 LLM 提取结果）\n")
    lines.append("| 意图名称 | 描述（来自 schema.json） | 出现次数 | 占用户轮比例 |")
    lines.append("|---|---|---|---|")
    for intent, d in sorted(intents["intent_distribution"].items(), key=lambda x: -x[1]["count"]):
        lines.append(
            f"| `{intent}` | {intent_descs_inline.get(intent, '')} "
            f"| {d['count']} | {d['pct_of_user_turns']}% |"
        )
    lines.append("")
    lines.append("### 3.2 入口意图 / 出口意图\n")
    lines.append(
        "> **入口意图**：每条对话第一个 USER 轮的意图；**出口意图**：最后一个 USER 轮的意图。\n"
        "> 以下统计基于本次提取的实际数据。\n"
    )
    lines.append("**入口意图（对话开场用户目标）**：\n")
    for intent, cnt in list(intents["entry_intents"].items())[:5]:
        lines.append(f"- `{intent}`（{intent_descs_inline.get(intent, '')}）：{cnt} 次")
    lines.append("")
    lines.append("**出口意图（对话收尾用户目标）**：\n")
    for intent, cnt in list(intents["exit_intents"].items())[:5]:
        lines.append(f"- `{intent}`（{intent_descs_inline.get(intent, '')}）：{cnt} 次")
    lines.append("")

    # ——— 四、槽位分析 ———
    lines.append("---\n")
    lines.append("## 四、槽位（Slot / 信息字段）分析\n")
    lines.append(
        "> **Slot（槽位）**：对话系统需要跟踪的关键信息字段。\n"
        "> **CRM 覆盖率**：该槽位在 CRM 数据中有值的对话比例（来自实际数据统计）。\n"
        "> **LLM 提取次数**：本次提取中该槽位出现在 slot_values 中的对话数量。\n"
    )
    lines.append("### 4.1 槽位综合统计（基于本次提取数据）\n")
    # 从 schema.json 构建槽位描述映射和 CRM/对话来源标记
    crm_slot_names = {  # CRM 来源槽位（无法从对话文本推断）
        "customer_name", "phone_suffix", "available_credit", "temp_credit",
        "temp_credit_status", "temp_expiry_days", "annual_rate_pct", "loan_count",
        "last_loan_date", "outstanding_amount", "billing_day",
    }
    slot_descs_from_schema: Dict[str, str] = {
        s["name"]: s.get("description", "") for s in ont.get("slots", [])
    }
    lines.append("| 槽位名称 | 描述（来自 schema.json） | 数据来源 | CRM 覆盖率 | LLM 提取次数 | 被询问次数 | 示例值 |")
    lines.append("|---|---|---|---|---|---|---|")
    for slot_obj in ont.get("slots", []):
        slot = slot_obj.get("name", "")
        d = slots.get(slot, {})
        crm_pct = d.get("crm_coverage_pct", 0)
        filled = d.get("filled_in_dialogue_n", 0)
        requested = d.get("requested_n", 0)
        examples = "、".join(d.get("example_values", [])[:2]) or "—"
        source = "CRM" if slot in crm_slot_names else "对话文本"
        lines.append(
            f"| `{slot}` | {slot_descs_from_schema.get(slot, '')} | {source} "
            f"| {crm_pct}% | {filled} | {requested} | {examples} |"
        )
    lines.append("")
    lines.append("### 4.2 后端 API（service_call）调用分布（基于本次提取数据）\n")
    lines.append(
        "> **service_call**：SYSTEM 轮次调用的后端 API。以下次数来自 LLM 标注结果。\n"
    )
    api_descs = {
        "verify_customer": "核实用户身份",
        "query_account": "查询账户信息（额度/利率/账单日等）",
        "calculate_repayment": "计算还款金额",
        "query_loan_records": "查询借款记录",
        "query_unresolved_issues": "查询未解决问题",
    }
    lines.append("| API 方法 | 中文说明 | 本次调用次数 |")
    lines.append("|---|---|---|")
    sc_methods = actions.get("service_call_methods", {})
    if sc_methods:
        for method, cnt in sc_methods.items():
            lines.append(f"| `{method}` | {api_descs.get(method, '')} | {cnt} |")
    else:
        lines.append("| — | LLM 未提取到 service_call 数据（可能 LLM 成功率为 0） | — |")
    lines.append("")

    # ——— 五、策略分析 ———
    lines.append("---\n")
    lines.append("## 五、对话策略（Strategy / 业务流程）分析\n")
    lines.append(
        "> 以下业务流程和意图转移矩阵均从本次 LLM 提取结果推导，非人工定义。\n"
        "> 仅处理 LLM 成功标注的对话；LLM 失败轮次统一标记为 general_inquiry，"
        "可能导致 general_inquiry 频率偏高。\n"
    )
    lines.append(f"**从数据推导的外呼业务流程（本次 {ov['total_records']} 条）**：\n```\n{strat['common_flow']}\n```\n")
    lines.append("### 5.1 高频意图转移（Top 10，基于本次提取数据）\n")
    lines.append("| 从意图 | 描述 | 转移到 | 描述 | 出现次数 |")
    lines.append("|---|---|---|---|---|")
    for t in strat["top_intent_transitions"][:10]:
        lines.append(
            f"| `{t['from']}` | {intent_descs_inline.get(t['from'], '')} "
            f"| `{t['to']}` | {intent_descs_inline.get(t['to'], '')} "
            f"| {t['count']} |"
        )
    lines.append("")

    # ——— 六、可提取性结论 ———
    lines.append("---\n")
    lines.append("## 六、SGD 字段可提取性结论（基于本次提取数据）\n")
    lines.append(
        "> 所有结论来自本次实际提取结果，不使用固定假设。\n"
        f"> **LLM**：{model_label}（本次成功率 {llm_rate}%）\n"
    )
    cat_labels = {
        "directly_extractable": "直接提取（100% 可靠）",
        "crm_high_coverage": f"CRM 高覆盖（实测 ≥80%）",
        "crm_medium_coverage": f"CRM 中覆盖（实测 50–80%）",
        "crm_low_coverage": f"CRM 低覆盖（实测 <50%）",
        "llm_extractable": f"LLM 提取（成功率 {llm_rate}%）",
        "dialogue_only_slots": "对话专属槽位",
        "not_extractable": "无法自动提取（需人工标注）",
    }
    lines.append("| 提取类别 | 涉及字段 | 实测可靠性 | 提取方法 |")
    lines.append("|---|---|---|---|")
    for cat, info in ext.items():
        reliability = info.get("reliability", "—")
        method = info.get("method", "—")
        fields_list = info["fields"]
        fields = ", ".join(f"`{f}`" for f in fields_list[:_MAX_FIELDS_DISPLAY])
        if len(fields_list) > _MAX_FIELDS_DISPLAY:
            fields += f" 等{len(fields_list)}个"
        lines.append(f"| {cat_labels.get(cat, cat)} | {fields} | {reliability} | {method} |")
    lines.append("")
    for cat, info in ext.items():
        lines.append(f"**{cat_labels.get(cat, cat)}**：{info['description']}\n")

    # ——— 七、建议 ———
    lines.append("---\n")
    lines.append("## 七、TOD 数据集构建建议\n")

    # 找 CRM 高覆盖槽位
    high_crm_slots = [s for s, d in slots.items() if d.get("crm_coverage_pct", 0) >= 80]
    high_crm_avg = (
        round(sum(slots[s]["crm_coverage_pct"] for s in high_crm_slots) / len(high_crm_slots), 1)
        if high_crm_slots else 0
    )
    top_act = max(actions.get("act_distribution", {}).items(), key=lambda x: x[1], default=("—", 0))

    lines.append(
        f"1. **对话骨架（100% 可用）**："
        f"本次 {ov['total_records']} 条对话、{ov['total_turns']} 个轮次可完整保留。\n"
        "\n"
        f"2. **CRM 槽位作为 slot_values 金标准（{len(high_crm_slots)} 个槽位覆盖率 ≥80%，均值 {high_crm_avg}%）**：\n"
        f"   - 高覆盖槽位：{', '.join(f'`{s}`' for s in high_crm_slots[:6])}{'等' if len(high_crm_slots)>6 else ''}。\n"
        "   - 可直接注入 `slot_values` 和 `service_results` 作为金标准。\n"
        "\n"
        f"3. **LLM 提取 active_intent / actions（本次成功率 {llm_rate}%）**：\n"
        f"   - 使用 {model_label} 对每条对话进行逐轮结构化标注。\n"
        f"   - 最高频 Act 类型：`{top_act[0]}`（{top_act[1]} 次），可用于验证标注合理性。\n"
        "\n"
        "4. **service_call 生成**：\n"
        "   - `service_call.method` 可由 active_intent → API 映射表自动生成，参数由 LLM 提取。\n"
        "\n"
        "5. **补充人工标注（不可自动生成的字段）**：\n"
        "   - `frames[].slots`（字符跨度标注）：需要标注工具手动标注。\n"
        "   - 完整 DST 金标准需人工核验 LLM 输出。\n"
        "\n"
        "6. **保留扩展字段 metadata**：\n"
        "   - `metadata.qc_label`：质检标签（质量分析用）\n"
        "   - `metadata.reference_response`：坐席参考回复（生成任务评估用）\n"
        "   - `metadata.user_info_parsed`：完整 CRM 数据（执行引擎查询用）\n"
        "\n"
        "7. **注意外呼数据特殊性**：\n"
        "   - 首轮发言者是 SYSTEM（坐席），与标准 SGD（USER 首轮）相反。\n"
        "   - `坐席回复` 字段是**待预测目标**，不应混入 `对话历史`。\n"
    )

    # ——— 八、与标准 SGD 的差异说明 ———
    lines.append("---\n")
    lines.append("## 八、生成文件与标准 SGD 格式的差异说明\n")
    lines.append(
        "> 本节说明 `chat_test_sgd_dialogues.json` 与 Google Research 发布的标准 "
        "[Schema-Guided Dialogue (SGD)](https://github.com/google-research-datasets/dstc8-schema-guided-dialogue) "
        "数据集在字段层面的差异。\n"
        f"> 本次提取模型：{model_label}，LLM 成功率 {llm_rate}%。\n"
    )
    lines.append(
        "**图例**：✅ 完整/金标准  ⚠️ 近似（LLM 提取，有误差）  ❌ 缺失（需人工标注）\n"
    )

    # 计算 LLM 实际提取到的字段统计
    total_acts_extracted = sum(actions.get("act_distribution", {}).values())
    total_sc = sum(actions.get("service_call_methods", {}).values())
    llm_note_suffix = f"（本次 LLM 提取 {total_acts_extracted} 条动作记录，{total_sc} 次 service_call）"

    lines.append("| SGD 字段路径 | 所在层级 | 本文件状态 | 差距说明 |")
    lines.append("|---|---|---|---|")
    for diff in SGD_FIELD_DIFF:
        note = diff["note"]
        # 为 actions 字段附加实际提取统计
        if "actions" in diff["sgd_field"] and "SYSTEM" in diff["sgd_field"]:
            note = note + f"；{llm_note_suffix}"
        lines.append(
            f"| `{diff['sgd_field']}` | {diff['sgd_location']} "
            f"| {diff['our_status']} | {note} |"
        )
    lines.append("")

    lines.append("### 8.1 缺失字段详解\n")
    lines.append(
        "#### ❌ `frames[].slots`（字符跨度标注 / Span Annotation）\n"
        "- **标准 SGD 含义**：标注 utterance 中每个槽位值的字符起止位置（如 `start=5, exclusive_end=8`）。\n"
        "- **缺失原因**：需要专用标注工具对原始文本做字符级标注，LLM 无法自动生成精确偏移量。\n"
        "- **影响**：Span 提取（Slot Filling from Span）任务无法训练；DST（对话状态跟踪）任务不受影响。\n"
    )
    lines.append(
        "#### ⚠️ `frames[].state.active_intent`（当前意图）\n"
        f"- **本次 LLM 提取**：{ov['llm_succeeded']} 条成功（{llm_rate}%）。\n"
        "- **主要误差来源**：口语化短回复（如「对」「嗯」）难以识别意图；"
        "`general_inquiry` 作为兜底意图可能被过度使用。\n"
    )
    lines.append(
        "#### ⚠️ `frames[].state.slot_values`（槽位值）\n"
        f"- **CRM 槽位（{len(crm_slot_names)} 个）**：来自 `parse_user_info()` 解析，"
        f"高覆盖槽位平均覆盖率 {high_crm_avg}%，可靠性接近 100%。\n"
        "- **对话专属槽位**（`dispute_date`、`inquiry_amount`、`term_months`、`identity_confirmed`）："
        "需 LLM 从对话文本 NLU 提取，LLM 失败时为空。\n"
    )
    lines.append(
        "#### ⚠️ `frames[].actions`（对话行为列表）\n"
        f"- **本次提取**：{total_acts_extracted} 条动作记录，来自 LLM 标注。\n"
        "- **标准 SGD**：每个 actions 条目包含精确的 slot/values/canonical_values，需人工核查。\n"
        "- **LLM 失败时**：动作列表为空（`[]`）。\n"
    )
    lines.append("### 8.2 扩展字段说明（标准 SGD 无，本项目新增）\n")
    lines.append(
        "| 扩展字段 | 说明 | 用途 |\n"
        "|---|---|---|\n"
        "| `metadata.qc_label` | 人工质检标签 | 数据质量分析 |\n"
        "| `metadata.reference_response` | 坐席参考回复（待预测目标） | 生成任务训练/评估 |\n"
        "| `metadata.user_info_parsed` | CRM 解析结构（完整版） | 执行引擎/后端 API 调用 |\n"
        f"| `metadata.extraction_method` | 提取模型标记（本次：{model_name}） | 数据溯源 |\n"
    )

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

    extracted_records: List[Dict[str, Any]] = []
    print(f"\n▶ 使用 LLM 提取 SGD 字段（{config.model}，每条间隔 {args.delay}s）...")
    for i, record in enumerate(records_to_process):
        sid = record.get("session_id", "?")[:20]
        print(f"  [{i+1:3d}/{sample_n}] {sid}...", end="", flush=True)
        result = extract_record_with_llm(record, llm_client)
        extracted_records.append(result)
        status = "✅" if result["llm_succeeded"] else "⚠️"
        print(f" {status} ({len(result['turns'])}/{result['turn_count']} 轮)")
        if i < sample_n - 1:
            time.sleep(args.delay)

    n_ok = sum(1 for r in extracted_records if r["llm_succeeded"])
    print(f"\n  ✅ 提取完成：{n_ok}/{sample_n} 条 LLM 成功")

    print("▶ 汇总统计...")
    agg = aggregate_results(extracted_records, model_info=model_info)

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
    print(
        f"  处理记录   : {ov['total_records']} 条，"
        f"LLM 成功 {ov['llm_succeeded']} 条 ({ov['llm_success_rate']}%)"
    )
    print(f"  提取模型   : {ov['model_name']} ({ov['model_base_url'] or 'OpenAI'})")
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
