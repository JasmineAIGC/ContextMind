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

from .extractor import ExtractionResult, ExtractionSchema, KnowledgeItem

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

# 开放模式 schema 推断阈值
# 新发现槽位的不同取值数量落在 [_MIN_CATEGORICAL, _MAX_CATEGORICAL] 范围内时，
# 视为枚举型（is_categorical=True）并填充 possible_values。
_MIN_CATEGORICAL_VALUES: int = 2
_MAX_CATEGORICAL_VALUES: int = 10
# 某槽位在新意图出现的对话中，共现频率 ≥ 此阈值时才纳入 required_slots。
_REQUIRED_SLOT_FREQUENCY_THRESHOLD: float = 0.5

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


def _infer_description_from_values(label: str, values: List[str]) -> str:
    """
    当 ExtractionSchema 中找不到对应描述时，根据标签名和提取值生成可读描述。

    - 将 label 中的下划线/连字符替换为空格，作为描述主体。
    - 若有提取值样本，附加最多 3 个值作为示例。
    """
    readable = label.replace("_", " ").replace("-", " ").strip()
    if values:
        samples = list(dict.fromkeys(v for v in values if v))[:3]  # 去重保序，取前3
        if samples:
            return f"{readable}（示例：{'、'.join(samples)}）"
    return readable


def _merge_schema_definitions_into_schema(
    schema_data: List[Dict[str, Any]],
    extraction_schema: ExtractionSchema,
) -> int:
    """
    将 ExtractionSchema 中明确定义的槽位和意图合并进 SGD schema 结构（就地修改）。

    与开放模式的 :func:`_merge_discovered_into_schema` 不同，本函数处理的是用户
    通过 ``--add-slot`` / ``--add-intent`` 显式新增的槽位和意图——这些项已写入
    ``ExtractionSchema``，但在基础 ``schema.json``（resources/anyihua_sgd/schema.json）
    中尚不存在。

    算法：
    1. 对 ``extraction_schema.slots``：将不在 ``schema_data`` 中的项追加到 slots 列表末尾。
    2. 对 ``extraction_schema.intents``：将不在 ``schema_data`` 中的项插入到
       ``general_inquiry`` 兜底意图之前（如果存在），否则追加到末尾。
    3. 保持幂等性：已存在同名项时跳过，不重复添加。

    返回:
        新增到 schema 中的条目总数（slots + intents）。
    """
    if not schema_data:
        return 0

    service = schema_data[0]
    added = 0

    # ── 合并槽位 ──────────────────────────────────────────────────────────────
    existing_slot_names: set = {s["name"] for s in service.get("slots", [])}
    for slot_def in extraction_schema.slots:
        if slot_def.name not in existing_slot_names:
            service.setdefault("slots", []).append({
                "name": slot_def.name,
                "description": slot_def.description,
                "is_categorical": False,
                "possible_values": [],
            })
            existing_slot_names.add(slot_def.name)
            added += 1
            logger.info(f"[SGDConverter] 新增用户定义槽位到 schema.json: {slot_def.name}")

    # ── 合并意图 ──────────────────────────────────────────────────────────────
    intents_list = service.setdefault("intents", [])
    existing_intent_names: set = {i["name"] for i in intents_list}
    new_intents = [i for i in extraction_schema.intents if i.name not in existing_intent_names]

    # 在 general_inquiry 兜底意图之前插入（保持语义顺序）
    fallback_idx = next(
        (idx for idx, it in enumerate(intents_list) if it.get("name") == "general_inquiry"),
        len(intents_list),
    )
    for offset, intent_def in enumerate(new_intents):
        intents_list.insert(fallback_idx + offset, {
            "name": intent_def.name,
            "description": intent_def.description,
            "is_transactional": False,
            "required_slots": [],
            "optional_slots": {},
            "result_slots": [],
        })
        added += 1
        logger.info(f"[SGDConverter] 新增用户定义意图到 schema.json: {intent_def.name}")

    return added


def _merge_discovered_into_schema(
    schema_data: List[Dict[str, Any]],
    results: List[ExtractionResult],
    extraction_schema: ExtractionSchema,
) -> int:
    """
    将开放模式下 LLM 新发现的槽位和意图合并进 SGD schema 结构（就地修改）。

    仅在 ``extraction_schema.slot_open_ended`` 或
    ``extraction_schema.intent_open_ended`` 为 True 时有效。

    算法：
    1. 收集所有提取结果中出现的 slot_value / intent 标签及其提取值。
    2. 与当前 schema 中已有的名称对比，找出新增项和需更新的项。
    3. 新槽位：
       · 优先使用 ExtractionSchema 中的 description；若不存在则从提取值推导。
       · 若提取出的不同值数量 ≥ 3，推断为 categorical 并填充 possible_values。
       · 追加到 slots 列表末尾。
    4. 新意图：
       · 优先使用 ExtractionSchema 中的 description；若不存在则从提取值推导。
       · 从提取结果中推断该意图出现时共现的槽位，作为 required_slots 候选。
       · 插入到 general_inquiry 兜底意图之前（如果存在），否则追加到末尾。
    5. 已存在的 is_categorical=True 槽位：将新出现的值追加到 possible_values。

    返回:
        新增到 schema 中的条目总数（slots + intents）。
    """
    if not schema_data:
        return 0

    service = schema_data[0]  # 仅处理第一个 service（AnYiHua_1）
    added = 0

    # ── 预建索引：ExtractionSchema 中的描述查找表 ────────────────────────────
    schema_slot_desc: Dict[str, str] = {
        s.name: s.description for s in extraction_schema.slots
    }
    schema_intent_desc: Dict[str, str] = {
        i.name: i.description for i in extraction_schema.intents
    }

    # ── 预建索引：从所有 results 中收集每个 label 的所有提取值 ────────────────
    # slot_values_map: {label -> [value, ...]}
    slot_values_map: Dict[str, List[str]] = {}
    # intent_slots_map: {intent_label -> set of slot labels co-occurring in same dialogue}
    intent_slots_map: Dict[str, set] = {}

    for result in results:
        # 先收集本条对话里出现的所有 slot label
        dialogue_slots = {
            item.label
            for item in result.knowledge_items
            if item.extraction_class == "slot_value"
        }
        for item in result.knowledge_items:
            if item.extraction_class == "slot_value":
                slot_values_map.setdefault(item.label, []).append(item.value)
            elif item.extraction_class == "intent":
                intent_slots_map.setdefault(item.label, set()).update(dialogue_slots)

    # ── 新槽位发现 ──────────────────────────────────────────────────────────
    if extraction_schema.slot_open_ended:
        existing_slots = service.get("slots", [])
        existing_slot_names = {s["name"] for s in existing_slots}

        # 更新已存在的 categorical 槽位的 possible_values
        for slot_entry in existing_slots:
            if slot_entry.get("is_categorical") and slot_entry["name"] in slot_values_map:
                new_vals = slot_values_map[slot_entry["name"]]
                existing_pv = set(slot_entry.get("possible_values") or [])
                for v in new_vals:
                    if v and v not in existing_pv:
                        slot_entry.setdefault("possible_values", []).append(v)
                        existing_pv.add(v)

        # 收集新发现的槽位（按首次出现顺序）
        discovered_slot_labels: List[str] = []
        seen_slot_labels: set = set()
        for result in results:
            for item in result.knowledge_items:
                if item.extraction_class == "slot_value" and item.label not in seen_slot_labels:
                    seen_slot_labels.add(item.label)
                    if item.label not in existing_slot_names:
                        discovered_slot_labels.append(item.label)

        for label in discovered_slot_labels:
            values = slot_values_map.get(label, [])
            distinct_values = list(dict.fromkeys(v for v in values if v))

            # 描述：优先从 ExtractionSchema 查找，否则从提取值推导
            description = schema_slot_desc.get(label) or _infer_description_from_values(
                label, distinct_values
            )

            # 推断是否为枚举型：不同值数 ≥ _MIN_CATEGORICAL_VALUES
            # 且 ≤ _MAX_CATEGORICAL_VALUES 时视为 categorical
            is_categorical = _MIN_CATEGORICAL_VALUES <= len(distinct_values) <= _MAX_CATEGORICAL_VALUES
            possible_values = distinct_values if is_categorical else []

            service.setdefault("slots", []).append({
                "name": label,
                "description": description,
                "is_categorical": is_categorical,
                "possible_values": possible_values,
            })
            added += 1
            logger.info(f"[SGDConverter] 新增槽位到 schema.json: {label}（categorical={is_categorical}）")

    # ── 新意图发现 ──────────────────────────────────────────────────────────
    if extraction_schema.intent_open_ended:
        existing_intent_names = {i["name"] for i in service.get("intents", [])}
        discovered_intent_labels: List[str] = []
        seen_intent_labels: set = set()
        for result in results:
            for item in result.knowledge_items:
                if item.extraction_class == "intent" and item.label not in seen_intent_labels:
                    seen_intent_labels.add(item.label)
                    if item.label not in existing_intent_names:
                        discovered_intent_labels.append(item.label)

        # 已知预定义槽位集合（用于筛选 required_slots 候选）
        all_known_slot_names = {s["name"] for s in service.get("slots", [])}

        # 预先计算每个 (intent_label, slot_label) 对在多少条对话中共现，
        # 避免对每个槽位重复扫描全量 results（O(n*m*k) → O(n*k)）。
        # intent_dialogue_count[label] = 该意图出现的对话数
        # intent_slot_cooccurrence[(intent_label, slot_label)] = 共现对话数
        intent_dialogue_count: Dict[str, int] = {}
        intent_slot_cooccurrence: Dict[tuple, int] = {}
        for result in results:
            intent_labels_in_dialogue = {
                item.label
                for item in result.knowledge_items
                if item.extraction_class == "intent"
                and item.label in set(discovered_intent_labels)
            }
            slot_labels_in_dialogue = {
                item.label
                for item in result.knowledge_items
                if item.extraction_class == "slot_value"
            }
            for ilabel in intent_labels_in_dialogue:
                intent_dialogue_count[ilabel] = intent_dialogue_count.get(ilabel, 0) + 1
                for slabel in slot_labels_in_dialogue:
                    key = (ilabel, slabel)
                    intent_slot_cooccurrence[key] = intent_slot_cooccurrence.get(key, 0) + 1

        intents_list = service.setdefault("intents", [])
        # 找到 general_inquiry 兜底意图的位置（新意图插入在它之前）
        fallback_idx = next(
            (i for i, it in enumerate(intents_list) if it.get("name") == "general_inquiry"),
            len(intents_list),
        )
        for offset, label in enumerate(discovered_intent_labels):
            # 描述：优先从 ExtractionSchema 查找，否则从提取值推导
            intent_values = list(dict.fromkeys(
                item.value
                for result in results
                for item in result.knowledge_items
                if item.extraction_class == "intent" and item.label == label
            ))
            description = schema_intent_desc.get(label) or _infer_description_from_values(
                label, intent_values
            )

            # 推断 required_slots：与该意图共现且在 schema 中存在的槽位，
            # 且共现频率 ≥ _REQUIRED_SLOT_FREQUENCY_THRESHOLD
            co_slots = intent_slots_map.get(label, set()) & all_known_slot_names
            n_intent = intent_dialogue_count.get(label, 0)
            required_slots: List[str] = []
            if n_intent > 0:
                for slot_name in sorted(co_slots):
                    n_cooccur = intent_slot_cooccurrence.get((label, slot_name), 0)
                    if n_cooccur / n_intent >= _REQUIRED_SLOT_FREQUENCY_THRESHOLD:
                        required_slots.append(slot_name)

            intents_list.insert(fallback_idx + offset, {
                "name": label,
                "description": description,
                "is_transactional": False,
                "required_slots": required_slots,
                "optional_slots": {},
                "result_slots": [],
            })
            added += 1
            logger.info(
                f"[SGDConverter] 新增意图到 schema.json: {label}，"
                f"推断 required_slots={required_slots}"
            )

    return added


def save_as_sgd(
    results: List[ExtractionResult],
    raw_dialogues: List[Dict[str, Any]],
    output_dir: Path,
    schema_source: Optional[Path] = None,
    dialogues_per_file: int = 1000,
    extraction_schema: Optional[ExtractionSchema] = None,
) -> Dict[str, Any]:
    """
    将批量提取结果与原始对话数据合并，保存为 SGD-like 格式文件集合。

    输出结构::

        <output_dir>/
            schema.json              # 服务 Schema（基于预定义，融合用户新增项和开放模式新发现项）
            dialogues_001.json       # 对话数据（每 dialogues_per_file 条一个文件）
            conversion_summary.json  # 转换统计信息

    参数:
        results:           ExtractionResult 列表（与 raw_dialogues 一一对应）
        raw_dialogues:     原始对话条目列表（chat_test_100.json 内容）
        output_dir:        输出目录（自动创建）
        schema_source:     schema.json 来源路径；None 时使用内置默认
                           （默认为 resources/anyihua_sgd/schema.json）
        dialogues_per_file: 每个 dialogues_*.json 文件包含的对话数量
        extraction_schema: 用于提取的 ExtractionSchema；
                           · 始终将 ExtractionSchema 中显式定义但基础 schema.json 中
                             尚未包含的槽位/意图（如通过 ``--add-slot`` / ``--add-intent``
                             新增的项）合并到输出 schema.json；
                           · 当 slot_open_ended 或 intent_open_ended 为 True 时，
                             还会从 results 中收集 LLM 新发现的槽位/意图标签并合并。

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

    # ---- 合并用户显式定义的槽位/意图（--add-slot / --add-intent 新增项）----
    user_defined_count = 0
    if extraction_schema is not None:
        user_defined_count = _merge_schema_definitions_into_schema(
            schema_data, extraction_schema
        )
        if user_defined_count:
            logger.info(
                f"[SGDConverter] 用户定义项：共新增 {user_defined_count} 项到 schema.json"
            )

    # ---- 开放模式：将 LLM 新发现的槽位/意图合并入 schema ----
    discovered_count = 0
    if extraction_schema is not None and (
        extraction_schema.slot_open_ended or extraction_schema.intent_open_ended
    ):
        discovered_count = _merge_discovered_into_schema(
            schema_data, results, extraction_schema
        )
        if discovered_count:
            logger.info(
                f"[SGDConverter] 开放模式：共新增 {discovered_count} 项到 schema.json"
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

    # ---- Schema 覆盖率统计 ----
    # 从所有提取结果中收集实际出现的槽位名和意图名
    extracted_slots: set = set()
    extracted_intents: set = set()
    for result in results:
        for item in result.knowledge_items:
            if item.extraction_class == "slot_value" and item.label:
                extracted_slots.add(item.label)
            elif item.extraction_class == "intent" and item.label:
                extracted_intents.add(item.label)

    # 从已写入的 schema_data 中获取预定义名称集合
    service_entry = schema_data[0] if schema_data else {}
    schema_slot_names: set = {s["name"] for s in service_entry.get("slots", [])}
    schema_intent_names: set = {i["name"] for i in service_entry.get("intents", [])}

    uncovered_slots = sorted(extracted_slots - schema_slot_names)
    uncovered_intents = sorted(extracted_intents - schema_intent_names)

    slot_cov = (
        round(len(extracted_slots & schema_slot_names) / len(extracted_slots) * 100, 1)
        if extracted_slots else 100.0
    )
    intent_cov = (
        round(len(extracted_intents & schema_intent_names) / len(extracted_intents) * 100, 1)
        if extracted_intents else 100.0
    )

    if uncovered_slots or uncovered_intents:
        note = (
            f"存在未覆盖项：槽位 {uncovered_slots}，意图 {uncovered_intents}。"
            "建议将其加入 _default_schema() 或启用开放模式。"
        )
    else:
        note = (
            "所有提取结果中出现的槽位和意图均已在 schema.json 中预定义，"
            "无需开放模式新增。"
        )

    schema_coverage: Dict[str, Any] = {
        "extracted_slots":    sorted(extracted_slots),
        "extracted_intents":  sorted(extracted_intents),
        "schema_slots":       sorted(schema_slot_names),
        "schema_intents":     sorted(schema_intent_names),
        "uncovered_slots":    uncovered_slots,
        "uncovered_intents":  uncovered_intents,
        "slot_coverage_pct":  slot_cov,
        "intent_coverage_pct": intent_cov,
        "note":               note,
    }

    logger.info(
        f"[SGDConverter] Schema 覆盖率 — "
        f"槽位 {slot_cov}%（{len(extracted_slots & schema_slot_names)}/{len(extracted_slots)}）"
        f"，意图 {intent_cov}%（{len(extracted_intents & schema_intent_names)}/{len(extracted_intents)}）"
    )
    if uncovered_slots:
        logger.warning(f"[SGDConverter] 未覆盖槽位: {uncovered_slots}")
    if uncovered_intents:
        logger.warning(f"[SGDConverter] 未覆盖意图: {uncovered_intents}")

    # ---- 写入 conversion_summary.json ----
    summary: Dict[str, Any] = {
        "dialogues":               len(sgd_dialogues),
        "turns":                   total_turns,
        "failed":                  failed,
        "dialogue_files":          dialogue_files,
        "services":                [SERVICE_NAME],
        "output_dir":              str(output_dir),
        "converted_at":            datetime.now().isoformat(),
        "user_defined_schema_items": user_defined_count,
        "discovered_schema_items": discovered_count,
        "schema_coverage":         schema_coverage,
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
    """内置默认 Schema，与 resources/anyihua_sgd/schema.json 字段完全一致。"""
    return [
        {
            "service_name": SERVICE_NAME,
            "description": (
                "安逸花外呼促活服务。坐席代表安逸花/马上消费金融主动致电老用户，"
                "目标是激活用户闲置的借款额度。"
                "标准流程：核实身份 → 告知额度 → 解答疑问 → 引导借款 → 礼貌告别。"
            ),
            "slots": [
                # ── 身份核实相关 ──
                {"name": "customer_name",          "description": '客户姓名（如"高先生"、"杨女士"）',                     "is_categorical": False, "possible_values": []},
                {"name": "phone_suffix",           "description": "手机尾号（3–4 位数字，用于身份核实）",                 "is_categorical": False, "possible_values": []},
                {"name": "identity_confirmed",     "description": "身份是否已核实（true / false）",                       "is_categorical": True,  "possible_values": ["true", "false"]},
                # ── 额度相关 ──
                {"name": "available_credit",       "description": "当前实际可提现额度（元，由 query_account API 返回）", "is_categorical": False, "possible_values": []},
                {"name": "credit_limit",           "description": "账户授信总额度（元）",                               "is_categorical": False, "possible_values": []},
                {"name": "temp_credit",            "description": "临时额度上限（元）",                                  "is_categorical": False, "possible_values": []},
                {"name": "temp_credit_status",     "description": "临时额度是否有效（有效 / 已过期 / 无临时额度）",      "is_categorical": True,  "possible_values": ["有效", "已过期", "无临时额度"]},
                {"name": "temp_credit_expiry_date","description": '临时额度到期日期（如"十月二十六号"）',                "is_categorical": False, "possible_values": []},
                {"name": "temp_expiry_days",       "description": "临时额度剩余有效天数",                               "is_categorical": False, "possible_values": []},
                # ── 利率与还款相关 ──
                {"name": "annual_rate_pct",        "description": "年化利率（%，如 24 表示 24%）",                       "is_categorical": False, "possible_values": []},
                {"name": "daily_rate_pct",         "description": "日利率（%，如 0.065 表示 0.065%）",                  "is_categorical": False, "possible_values": []},
                {"name": "monthly_payment",        "description": "用户询问或坐席告知的月还款额（元）",                  "is_categorical": False, "possible_values": []},
                {"name": "total_interest",         "description": "用户询问或坐席告知的总利息（元）",                    "is_categorical": False, "possible_values": []},
                {"name": "term_months",            "description": "用户询问的分期期数（如 12）",                         "is_categorical": False, "possible_values": []},
                {"name": "billing_day",            "description": "账单日（每月几号）",                                  "is_categorical": False, "possible_values": []},
                {"name": "repayment_date",         "description": '还款日（如"十一月一号"）',                            "is_categorical": False, "possible_values": []},
                # ── 借款记录相关 ──
                {"name": "loan_count",             "description": "当前未还清借款笔数",                                  "is_categorical": False, "possible_values": []},
                {"name": "last_loan_date",         "description": "最近一次借款日期（中文格式）",                        "is_categorical": False, "possible_values": []},
                {"name": "outstanding_amount",     "description": "当前未还款金额（元）",                                "is_categorical": False, "possible_values": []},
                {"name": "dispute_date",           "description": '用户质疑的借款日期（如"七月二十三号"）',              "is_categorical": False, "possible_values": []},
                {"name": "inquiry_amount",         "description": "用户询问或质疑的金额（元）",                          "is_categorical": False, "possible_values": []},
                {"name": "overdue_days",           "description": "逾期天数",                                            "is_categorical": False, "possible_values": []},
                # ── 用户态度与期望相关 ──
                {"name": "user_expected_interest", "description": '用户对合理利息的期望金额（元），如"一万块一年应该八九百"', "is_categorical": False, "possible_values": []},
                {"name": "user_complaint_reason",  "description": "用户抱怨或拒绝的具体原因（如还款太麻烦、利率太高等）", "is_categorical": False, "possible_values": []},
            ],
            "intents": [
                # ── 坐席主导意图 ──
                {
                    "name": "verify_identity",
                    "description": "【坐席】开场身份核实，确认来电者是账户本人",
                    "is_transactional": False,
                    "required_slots": ["customer_name"],
                    "optional_slots": {"phone_suffix": ""},
                    "result_slots": ["identity_confirmed"],
                },
                {
                    "name": "explain_credit_limit",
                    "description": "【坐席】告知用户当前可提现额度及授信额度情况",
                    "is_transactional": False,
                    "required_slots": ["customer_name", "available_credit"],
                    "optional_slots": {"credit_limit": "", "temp_credit": "", "temp_credit_status": "", "temp_expiry_days": ""},
                    "result_slots": ["available_credit", "temp_credit", "temp_credit_status"],
                },
                {
                    "name": "explain_interest_rate",
                    "description": "【坐席】解释贷款利率（年化/日利率）和还款方式",
                    "is_transactional": False,
                    "required_slots": ["customer_name", "annual_rate_pct"],
                    "optional_slots": {"daily_rate_pct": "", "term_months": ""},
                    "result_slots": ["annual_rate_pct"],
                },
                {
                    "name": "calculate_repayment",
                    "description": "【坐席】根据用户需求计算指定金额和期数的月还款额及总利息",
                    "is_transactional": False,
                    "required_slots": ["customer_name"],
                    "optional_slots": {"inquiry_amount": "", "term_months": ""},
                    "result_slots": ["monthly_payment", "total_interest"],
                },
                {
                    "name": "explain_displayed_amount",
                    "description": "【坐席】解释 APP 页面显示金额的构成或计算逻辑",
                    "is_transactional": False,
                    "required_slots": ["customer_name", "inquiry_amount"],
                    "optional_slots": {"available_credit": "", "credit_limit": "", "temp_credit": "", "temp_credit_status": ""},
                    "result_slots": ["available_credit", "temp_credit"],
                },
                {
                    "name": "handle_loan_dispute",
                    "description": "【坐席】核实并回应用户对某笔借款记录（日期/金额）的争议",
                    "is_transactional": False,
                    "required_slots": ["customer_name", "dispute_date"],
                    "optional_slots": {"last_loan_date": "", "loan_count": "", "outstanding_amount": ""},
                    "result_slots": ["last_loan_date", "loan_count", "outstanding_amount"],
                },
                {
                    "name": "guide_loan_operation",
                    "description": "【坐席】引导用户在 APP 完成借款操作步骤",
                    "is_transactional": False,
                    "required_slots": ["customer_name"],
                    "optional_slots": {"available_credit": ""},
                    "result_slots": [],
                },
                {
                    "name": "promote_loan_offer",
                    "description": "【坐席】主动推介借款优惠、介绍产品亮点或邀请用户使用额度",
                    "is_transactional": False,
                    "required_slots": ["customer_name"],
                    "optional_slots": {"available_credit": "", "credit_limit": "", "temp_credit": ""},
                    "result_slots": [],
                },
                {
                    "name": "explain_temp_credit",
                    "description": "【坐席】解释临时额度的有效期、金额及使用规则",
                    "is_transactional": False,
                    "required_slots": ["customer_name", "temp_credit"],
                    "optional_slots": {"temp_credit_status": "", "temp_expiry_days": "", "temp_credit_expiry_date": ""},
                    "result_slots": ["temp_credit_status", "temp_expiry_days"],
                },
                {
                    "name": "escalate_to_human",
                    "description": "【坐席/用户】请求或承诺转接人工客服",
                    "is_transactional": True,
                    "required_slots": ["customer_name"],
                    "optional_slots": {"dispute_date": "", "inquiry_amount": ""},
                    "result_slots": [],
                },
                {
                    "name": "say_goodbye",
                    "description": "【坐席/用户】礼貌结束对话、道别",
                    "is_transactional": False,
                    "required_slots": ["customer_name"],
                    "optional_slots": {},
                    "result_slots": [],
                },
                # ── 用户主导意图 ──
                {
                    "name": "complain_repayment",
                    "description": "【用户】抱怨月还款额太高、还款方式太麻烦或还款压力大；关键词：还款太麻烦、要还多少、还起太恼火、月供太高",
                    "is_transactional": False,
                    "required_slots": [],
                    "optional_slots": {"monthly_payment": "", "term_months": ""},
                    "result_slots": [],
                },
                {
                    "name": "complain_interest_rate",
                    "description": "【用户】质疑或抱怨利率偏高、利息太贵；关键词：利息有点高、太高了、利率高",
                    "is_transactional": False,
                    "required_slots": [],
                    "optional_slots": {"annual_rate_pct": "", "user_complaint_reason": ""},
                    "result_slots": [],
                },
                {
                    "name": "express_interest_expectation",
                    "description": "【用户】表达对合理利率/利息的期望或认知，或将当前利息与期望金额比较；关键词：一万块一年应该八九百、一千多太高了、应该只有八百多",
                    "is_transactional": False,
                    "required_slots": [],
                    "optional_slots": {"user_expected_interest": ""},
                    "result_slots": [],
                },
                {
                    "name": "confirm_information",
                    "description": "【用户】确认或认可坐席提供的信息；关键词：对、好的、明白、是的、嗯",
                    "is_transactional": False,
                    "required_slots": [],
                    "optional_slots": {},
                    "result_slots": [],
                },
                {
                    "name": "reject_offer",
                    "description": "【用户】明确拒绝当前借款方案或产品；关键词：不用了、不需要、不借了",
                    "is_transactional": False,
                    "required_slots": [],
                    "optional_slots": {"user_complaint_reason": ""},
                    "result_slots": [],
                },
                {
                    "name": "ask_for_clarification",
                    "description": "【用户】要求坐席进一步解释某项内容；关键词：为什么、怎么算的、能说清楚吗",
                    "is_transactional": False,
                    "required_slots": [],
                    "optional_slots": {},
                    "result_slots": [],
                },
                {
                    "name": "dispute_loan_record",
                    "description": "【用户】对某笔借款记录提出质疑或否认；关键词：我没有借这笔、这不是我的借款",
                    "is_transactional": False,
                    "required_slots": [],
                    "optional_slots": {"dispute_date": ""},
                    "result_slots": [],
                },
                {
                    "name": "inquire_repayment_method",
                    "description": "【用户】询问还款方式、还款渠道或操作步骤",
                    "is_transactional": False,
                    "required_slots": [],
                    "optional_slots": {},
                    "result_slots": [],
                },
                {
                    "name": "express_hesitation",
                    "description": "【用户】表示犹豫、考虑中或需要时间决定；关键词：我想想、再看看、暂时不用",
                    "is_transactional": False,
                    "required_slots": [],
                    "optional_slots": {},
                    "result_slots": [],
                },
                {
                    "name": "general_inquiry",
                    "description": "【用户·兜底】用户回复完全无法匹配以上任何具体意图时的最后兜底；仅在穷尽所有其他意图后仍无法归类时使用",
                    "is_transactional": False,
                    "required_slots": [],
                    "optional_slots": {},
                    "result_slots": [],
                },
            ],
        }
    ]
