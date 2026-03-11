"""
安逸花外呼 · SGD 格式转换器

将 AnyihuaKnowledgeExtractor 的提取结果与原始对话数据合并，
转换为类似 Google SGD 数据集格式的结构化对话数据。

SGD 格式结构::

    schema.json  —— 服务定义（slots / intents）
    dialogues_001.json  —— 对话列表，每条对话格式如下：

    {
      "dialogue_id": "session_id",
      "services": ["AnYiHua_1"],
      "metadata": {
        "qc_label":           "人工校验标签",
        "reference_response": "坐席参考回复",
        "user_info_raw":      "原始用户信息字符串",
        "user_info_parsed":   {...CRM 解析结果...}
      },
      "turns": [
        {
          "speaker":  "SYSTEM" | "USER",
          "utterance": "话语原文",
          "frames": [
            {
              "service": "AnYiHua_1",

              // USER turn 专有字段：
              "state": {
                "active_intent":    "意图名",
                "requested_slots":  [...],
                "slot_values":      {"slot": ["value"]}
              },

              // SYSTEM turn 专有字段：
              "service_call":    {"method": "api_name", "parameters": {...}} | null,
              "service_results": [{"slot": "value", ...}],

              // 两种 speaker 都有：
              "actions": [{"act": "...", "slot": "...", "values": [], "canonical_values": []}]
            }
          ]
        }
      ]
    }

设计说明：
  · 提取结果（ExtractionResult）提供 slot_value / intent / fact 知识项，
    每项含 turn_idx（来自哪一轮）和 speaker（说话人）。
  · SGD state.slot_values 是累积状态：在每个 USER 轮聚合该轮及之前所有已出现的槽位值。
  · 若某轮有 intent 提取项，取第一条作为 active_intent；否则默认 general_inquiry。
  · SYSTEM 轮的 service_call 由当前 active_intent → CRM API 名称映射自动填充。
  · service_results 优先使用 CRM 解析数据（parse_user_info），无 CRM 数据时留空。

典型使用::

    from contextmind.scenarios.anyihua.knowledge_extraction import (
        AnyihuaKnowledgeExtractor,
        to_sgd_dialogue,
        save_as_sgd,
    )
    import json
    from pathlib import Path

    dialogues = json.loads(Path("resources/data/chat_test_100.json").read_text())
    extractor = AnyihuaKnowledgeExtractor()

    results = extractor.extract_batch(dialogues[:10])
    save_as_sgd(results, dialogues[:10], output_dir=Path("data/anyihua_sgd"))
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from contextmind.infra.logger import get_logger
from contextmind.scenarios.anyihua.utils import parse_user_info

from .extractor import ExtractionResult, KnowledgeItem

logger = get_logger(__name__)

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #

SERVICE_NAME = "AnYiHua_1"

# 意图 → CRM API 名称映射（与 analyze_chat_test.py 一致）
_INTENT_TO_API: Dict[str, str] = {
    "verify_identity":          "verify_customer",
    "explain_credit_limit":     "query_account",
    "explain_interest_rate":    "calculate_repayment",
    "calculate_repayment":      "calculate_repayment",
    "explain_displayed_amount": "query_account",
    "handle_loan_dispute":      "query_loan_records",
    "guide_loan_operation":     "query_account",
    "escalate_to_human":        "",
    "say_goodbye":              "query_unresolved_issues",
    "general_inquiry":          "",
}

# 已知槽位集合（来自 schema.json）
_SCHEMA_SLOTS = {
    "customer_name", "phone_suffix", "dispute_date", "inquiry_amount",
    "term_months", "identity_confirmed", "available_credit", "temp_credit",
    "temp_credit_status", "temp_expiry_days", "annual_rate_pct", "loan_count",
    "last_loan_date", "outstanding_amount", "billing_day",
}

_AGENT_PREFIX = "坐席："
_USER_PREFIX = "用户："


# --------------------------------------------------------------------------- #
# 内部辅助
# --------------------------------------------------------------------------- #


def _build_service_results(crm: Dict[str, Any], intent: str) -> List[Dict[str, str]]:
    """
    根据 active_intent 和 CRM 数据构建 service_results。

    只在有 CRM API 调用的意图下返回非空结果。
    """
    api = _INTENT_TO_API.get(intent, "")
    if not api:
        return []

    base: Dict[str, str] = {}
    if crm.get("customer_name"):
        base["customer_name"] = str(crm["customer_name"])
    if crm.get("phone_suffix"):
        base["phone_suffix"] = str(crm["phone_suffix"])

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
            base["last_loan_date"] = str(crm["last_loan_date"])
        if crm.get("outstanding_amount"):
            base["outstanding_amount"] = str(crm["outstanding_amount"])

    elif api == "calculate_repayment":
        if crm.get("annual_rate_pct"):
            base["annual_rate_pct"] = str(crm["annual_rate_pct"])

    return [base] if base else []


def _is_user_turn(raw_line: str) -> bool:
    return raw_line.startswith(_USER_PREFIX)


# --------------------------------------------------------------------------- #
# 核心转换：ExtractionResult + 原始对话 → SGD 对话字典
# --------------------------------------------------------------------------- #


def to_sgd_dialogue(
    result: ExtractionResult,
    raw_dialogue: Dict[str, Any],
) -> Dict[str, Any]:
    """
    将单条 ExtractionResult 与原始对话数据合并，转换为 SGD 对话格式字典。

    参数:
        result:       AnyihuaKnowledgeExtractor.extract() 的返回值
        raw_dialogue: chat_test_100.json 中对应的原始对话条目

    返回:
        SGD 格式的对话字典（可直接序列化为 JSON）
    """
    session_id = raw_dialogue.get("session_id", result.dialogue_id)
    crm = parse_user_info(raw_dialogue.get("用户信息", ""))

    # ---- 按轮次分组知识项 ----
    # 槽位值：{turn_idx → {label → value}}
    slot_by_turn: Dict[int, Dict[str, str]] = {}
    # 意图：{turn_idx → [label]}
    intent_by_turn: Dict[int, List[str]] = {}

    for item in result.knowledge_items:
        if item.turn_idx < 0:
            continue
        if item.extraction_class == "slot_value":
            slot_by_turn.setdefault(item.turn_idx, {})[item.label] = item.value
        elif item.extraction_class == "intent":
            intent_by_turn.setdefault(item.turn_idx, []).append(item.label)

    # ---- 构建轮次 turns ----
    turns: List[Dict[str, Any]] = []
    # 累积 slot_values（USER 轮维护累积对话状态）
    cumulative_slots: Dict[str, List[str]] = {}
    last_active_intent = "general_inquiry"

    for turn_idx, speaker, utterance in result.turns:
        if speaker == "坐席":
            sgd_speaker = "SYSTEM"
        else:
            sgd_speaker = "USER"

        # ---- 本轮槽位更新 ----
        for label, value in slot_by_turn.get(turn_idx, {}).items():
            cumulative_slots[label] = [value]

        # ---- 本轮意图 ----
        intents_this_turn = intent_by_turn.get(turn_idx, [])
        if intents_this_turn:
            active_intent = intents_this_turn[0]
            last_active_intent = active_intent
        else:
            active_intent = last_active_intent

        frame: Dict[str, Any] = {"service": SERVICE_NAME}

        if sgd_speaker == "USER":
            frame["state"] = {
                "active_intent":   active_intent,
                "requested_slots": [],
                "slot_values":     dict(cumulative_slots),
            }
            # 简单 actions：为本轮新出现的槽位生成 INFORM 动作
            actions = []
            for label, value in slot_by_turn.get(turn_idx, {}).items():
                actions.append({
                    "act":              "INFORM",
                    "slot":             label,
                    "values":           [value],
                    "canonical_values": [],
                })
            if intents_this_turn:
                actions.append({
                    "act":              "INFORM_INTENT",
                    "slot":             "",
                    "values":           [active_intent],
                    "canonical_values": [],
                })
            frame["actions"] = actions

        else:  # SYSTEM
            # service_call：根据当前 active_intent 映射
            api_name = _INTENT_TO_API.get(last_active_intent, "")
            frame["service_call"] = (
                {"method": api_name, "parameters": {"customer_name": crm.get("customer_name", "")}}
                if api_name else None
            )
            frame["service_results"] = _build_service_results(crm, last_active_intent)
            # 简单 actions：为本轮出现的槽位生成 INFORM 动作
            actions = []
            for label, value in slot_by_turn.get(turn_idx, {}).items():
                actions.append({
                    "act":              "INFORM",
                    "slot":             label,
                    "values":           [value],
                    "canonical_values": [],
                })
            frame["actions"] = actions

        turns.append({
            "speaker":   sgd_speaker,
            "utterance": utterance,
            "frames":    [frame],
        })

    # ---- 元数据 ----
    metadata: Dict[str, Any] = {
        "qc_label":           raw_dialogue.get("人工校验", ""),
        "reference_response": raw_dialogue.get("坐席回复", ""),
        "user_info_raw":      raw_dialogue.get("用户信息", ""),
        "user_info_parsed":   crm,
        "extraction_stats":   result.stats,
        "extracted_at":       result.extracted_at,
    }

    sgd_dialogue = {
        "dialogue_id": session_id,
        "services":    [SERVICE_NAME],
        "metadata":    metadata,
        "turns":       turns,
    }

    logger.debug(
        f"[SGDConverter] 对话 {session_id}: {len(turns)} 轮 → SGD 格式 "
        f"（USER 轮 {sum(1 for t in turns if t['speaker']=='USER')} 个，"
        f"SYSTEM 轮 {sum(1 for t in turns if t['speaker']=='SYSTEM')} 个）"
    )
    return sgd_dialogue


# --------------------------------------------------------------------------- #
# 批量转换 + 文件保存
# --------------------------------------------------------------------------- #


def save_as_sgd(
    results: List[ExtractionResult],
    raw_dialogues: List[Dict[str, Any]],
    output_dir: Path,
    schema_source: Optional[Path] = None,
    dialogues_per_file: int = 1000,
) -> Dict[str, Any]:
    """
    将批量提取结果与原始对话数据合并，保存为 SGD-like 格式文件集合。

    输出结构::

        <output_dir>/
            schema.json              # 服务 Schema（复制自 schema_source 或内置默认）
            dialogues_001.json       # 对话数据（每 dialogues_per_file 条一个文件）
            conversion_summary.json  # 转换统计信息

    参数:
        results:           ExtractionResult 列表（与 raw_dialogues 一一对应）
        raw_dialogues:     原始对话条目列表（chat_test_100.json 内容）
        output_dir:        输出目录（自动创建）
        schema_source:     schema.json 来源路径；None 时使用内置默认
                           （默认为 resources/anyihua_sgd/schema.json）
        dialogues_per_file: 每个 dialogues_*.json 文件包含的对话数量

    返回:
        转换统计字典（dialogues / turns / dialogue_files / output_dir 等）
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 确定 schema_source 默认路径
    # File layout: contextmind/scenarios/anyihua/knowledge_extraction/sgd_converter.py
    # Project root is 4 levels up: sgd_converter.py → knowledge_extraction → anyihua → scenarios → contextmind → root
    if schema_source is None:
        _pkg_root = Path(__file__).resolve().parents[4]  # project root
        schema_source = _pkg_root / "resources" / "anyihua_sgd" / "schema.json"

    # ---- 写入 schema.json ----
    if schema_source.exists():
        schema_data = json.loads(schema_source.read_text(encoding="utf-8"))
        logger.info(f"[SGDConverter] 使用 Schema 来源: {schema_source}")
    else:
        schema_data = _default_schema()
        logger.warning(
            f"[SGDConverter] schema.json 未找到 ({schema_source})，使用内置默认 Schema"
        )
    (output_dir / "schema.json").write_text(
        json.dumps(schema_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(f"[SGDConverter] schema.json 已写入: {output_dir}/schema.json")

    # ---- 转换每条对话 ----
    n = min(len(results), len(raw_dialogues))
    logger.info(f"[SGDConverter] ═══ 开始 SGD 转换，共 {n} 条对话 ═══")

    sgd_dialogues: List[Dict[str, Any]] = []
    total_turns = 0
    failed = 0

    for i in range(n):
        try:
            sgd = to_sgd_dialogue(results[i], raw_dialogues[i])
            sgd_dialogues.append(sgd)
            total_turns += len(sgd["turns"])
        except Exception as exc:
            failed += 1
            logger.error(
                f"[SGDConverter] ✗ 对话 {i} 转换失败 "
                f"({results[i].dialogue_id}): {exc}"
            )

    # ---- 分文件写入 dialogues_*.json ----
    dialogue_files = 0
    for chunk_start in range(0, len(sgd_dialogues), dialogues_per_file):
        chunk = sgd_dialogues[chunk_start: chunk_start + dialogues_per_file]
        dialogue_files += 1
        out_path = output_dir / f"dialogues_{dialogue_files:03d}.json"
        out_path.write_text(
            json.dumps(chunk, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(
            f"[SGDConverter] {out_path.name} 已写入 "
            f"({len(chunk)} 条对话，{sum(len(d['turns']) for d in chunk)} 轮)"
        )

    # ---- 写入 conversion_summary.json ----
    summary: Dict[str, Any] = {
        "dialogues":      len(sgd_dialogues),
        "turns":          total_turns,
        "failed":         failed,
        "dialogue_files": dialogue_files,
        "services":       [SERVICE_NAME],
        "output_dir":     str(output_dir),
        "converted_at":   datetime.now().isoformat(),
    }
    (output_dir / "conversion_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    logger.info(
        f"[SGDConverter] ═══ SGD 转换完成 ═══ "
        f"对话 {len(sgd_dialogues)} 条 / 轮次 {total_turns} 个 / 文件 {dialogue_files} 个"
    )
    return summary


# --------------------------------------------------------------------------- #
# 内置默认 Schema（schema.json 缺失时的兜底）
# --------------------------------------------------------------------------- #


def _default_schema() -> List[Dict[str, Any]]:
    """内置最小 Schema，与 resources/anyihua_sgd/schema.json 字段一致。"""
    return [
        {
            "service_name": SERVICE_NAME,
            "description": "安逸花外呼促活服务。坐席代表安逸花/马上消费金融主动致电老用户，目标是激活用户闲置的借款额度。",
            "slots": [
                {"name": "customer_name",     "description": "客户姓名",           "is_categorical": False, "possible_values": []},
                {"name": "phone_suffix",      "description": "手机尾号",           "is_categorical": False, "possible_values": []},
                {"name": "dispute_date",      "description": "用户质疑的借款日期", "is_categorical": False, "possible_values": []},
                {"name": "inquiry_amount",    "description": "用户询问的金额",     "is_categorical": False, "possible_values": []},
                {"name": "term_months",       "description": "分期期数",           "is_categorical": False, "possible_values": []},
                {"name": "identity_confirmed","description": "身份是否已核实",     "is_categorical": True,  "possible_values": ["true", "false"]},
                {"name": "available_credit",  "description": "可提现额度",         "is_categorical": False, "possible_values": []},
                {"name": "temp_credit",       "description": "临时额度上限",       "is_categorical": False, "possible_values": []},
                {"name": "temp_credit_status","description": "临时额度有效性",     "is_categorical": True,  "possible_values": ["有效", "已过期", "无临时额度"]},
                {"name": "temp_expiry_days",  "description": "临时额度剩余天数",   "is_categorical": False, "possible_values": []},
                {"name": "annual_rate_pct",   "description": "年化利率（%）",      "is_categorical": False, "possible_values": []},
                {"name": "loan_count",        "description": "未还清借款笔数",     "is_categorical": False, "possible_values": []},
                {"name": "last_loan_date",    "description": "最近借款日期",       "is_categorical": False, "possible_values": []},
                {"name": "outstanding_amount","description": "未还款金额（元）",   "is_categorical": False, "possible_values": []},
                {"name": "billing_day",       "description": "账单日",             "is_categorical": False, "possible_values": []},
            ],
            "intents": [
                {
                    "name": "verify_identity",
                    "description": "开场身份核实",
                    "required_slots": ["customer_name"],
                    "optional_slots": {"phone_suffix": ""},
                    "result_slots": ["identity_confirmed"],
                },
                {
                    "name": "explain_credit_limit",
                    "description": "告知额度情况",
                    "required_slots": ["customer_name", "available_credit"],
                    "optional_slots": {"temp_credit": "", "temp_credit_status": "", "temp_expiry_days": ""},
                    "result_slots": ["available_credit", "temp_credit", "temp_credit_status"],
                },
                {
                    "name": "explain_interest_rate",
                    "description": "解释利率和还款方式",
                    "required_slots": ["customer_name", "annual_rate_pct"],
                    "optional_slots": {"term_months": ""},
                    "result_slots": ["annual_rate_pct"],
                },
                {
                    "name": "calculate_repayment",
                    "description": "计算月还款额",
                    "required_slots": ["customer_name"],
                    "optional_slots": {"inquiry_amount": "", "term_months": ""},
                    "result_slots": [],
                },
                {
                    "name": "explain_displayed_amount",
                    "description": "解释 APP 显示金额",
                    "required_slots": ["customer_name", "inquiry_amount"],
                    "optional_slots": {"available_credit": "", "temp_credit": "", "temp_credit_status": ""},
                    "result_slots": ["available_credit", "temp_credit"],
                },
                {
                    "name": "handle_loan_dispute",
                    "description": "核实争议借款记录",
                    "required_slots": ["customer_name", "dispute_date"],
                    "optional_slots": {"last_loan_date": "", "loan_count": "", "outstanding_amount": ""},
                    "result_slots": ["last_loan_date", "loan_count", "outstanding_amount"],
                },
                {
                    "name": "guide_loan_operation",
                    "description": "引导 APP 借款操作",
                    "required_slots": ["customer_name"],
                    "optional_slots": {"available_credit": ""},
                    "result_slots": [],
                },
                {
                    "name": "escalate_to_human",
                    "description": "转接人工客服",
                    "required_slots": ["customer_name"],
                    "optional_slots": {"dispute_date": "", "inquiry_amount": ""},
                    "result_slots": [],
                },
                {
                    "name": "say_goodbye",
                    "description": "礼貌告别",
                    "required_slots": ["customer_name"],
                    "optional_slots": {},
                    "result_slots": [],
                },
                {
                    "name": "general_inquiry",
                    "description": "通用询问（默认）",
                    "required_slots": [],
                    "optional_slots": {},
                    "result_slots": [],
                },
            ],
        }
    ]
