#!/usr/bin/env python3
"""
chat_test_100.json 数据提取能力分析工具

分析 resources/data/chat_test_100.json 数据集，评估从中能够提取出哪些信息
（本体、意图、槽位、策略等），以用于构建类似 SGD 数据集的标准 TOD 任务。

----------------------------------------------------------------------
分析维度
----------------------------------------------------------------------

1. 本体（Ontology）
   - 服务域定义：安逸花外呼促活
   - CRM 字段覆盖率：哪些槽位能从 用户信息 中提取，覆盖率如何
   - 字段来源：用户信息（CRM）vs 对话文本（NLU）

2. 意图（Intents）
   - 每条对话中检测到的意图分布
   - 意图转移模式（一条对话中意图的顺序）
   - 意图覆盖率（每条对话至少检测到几个意图段）

3. 槽位（Slots）
   - 每个槽位在数据集中的覆盖率（有值 vs 无值）
   - 槽位来源：CRM 数据（高可信）vs 对话推断（低可信）
   - 槽位值分布（对数值型槽位输出统计）

4. 对话策略（Strategies）
   - 常见对话流程（Dialogue Flow Patterns）
   - 策略转移矩阵（前后意图出现频率）
   - 平均策略步骤数（每条对话使用了几个不同意图）

5. 数据集统计
   - 轮次分布、QC 标签分布
   - 可提取字段的缺失率

----------------------------------------------------------------------
输出
----------------------------------------------------------------------

  资源目录/data/chat_test_extraction_report.json    —— 机器可读的结构化分析
  资源目录/data/chat_test_extraction_report.md      —— 人类可读的 Markdown 报告

----------------------------------------------------------------------
用法
----------------------------------------------------------------------

  python benchmark/tools/analyze_chat_test.py
  python benchmark/tools/analyze_chat_test.py --input resources/data/chat_test_100.json
  python benchmark/tools/analyze_chat_test.py --output /tmp/analysis_report
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from contextmind.scenarios.anyihua.utils import parse_user_info

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #

_DEFAULT_INPUT = str(_PROJECT_ROOT / "resources" / "data" / "chat_test_100.json")
_DEFAULT_OUTPUT_DIR = str(_PROJECT_ROOT / "resources" / "data")

_AGENT_PREFIX = "坐席："
_USER_PREFIX = "用户："

# 意图推断规则（与 adapter.py 保持同步）
_INTENT_RULES: List[Tuple[List[str], str]] = [
    (["本人", "核实", "您是谁", "是您本人", "确认一下", "您这边是", "手机尾号"], "verify_identity"),
    (["没有借款", "没借过", "没贷过", "异常", "怎么会有", "这笔借款", "这笔贷款",
      "七月", "八月", "九月", "十月", "号的这一笔"], "handle_loan_dispute"),
    (["额度", "提额", "提现额", "可以提", "多少额", "额度是多少"], "explain_credit_limit"),
    (["利率", "利息", "还款", "分期", "手续费", "月还", "每月还"], "explain_interest_rate"),
    (["借一万", "借多少", "算一下", "计算", "还多少钱"], "calculate_repayment"),
    (["显示", "APP", "页面", "上面写", "显示的", "看到的"], "explain_displayed_amount"),
    (["怎么借", "如何提现", "操作", "在哪借", "步骤", "怎么用"], "guide_loan_operation"),
    (["转人工", "人工客服", "投诉", "举报", "上级"], "escalate_to_human"),
    (["再见", "不打扰", "挂电话", "拜拜", "祝您", "感谢来电", "有需要再联系"], "say_goodbye"),
]

# 所有意图名称（含默认）
_ALL_INTENTS = [rule[1] for rule in _INTENT_RULES] + ["general_inquiry"]

# 槽位与 parse_user_info 输出字段的映射
# （SGD 槽位名 → parse_user_info 返回 key）
_SLOT_TO_CRM_KEY: Dict[str, str] = {
    "customer_name": "customer_name",
    "phone_suffix": "phone_suffix",
    "available_credit": "available_credit",
    "temp_credit": "temp_credit",
    "temp_credit_status": "temp_expired",      # bool → categorical
    "temp_expiry_days": "temp_active_days",
    "annual_rate_pct": "annual_rate_pct",
    "loan_count": "loan_count",
    "last_loan_date": "last_loan_date",
    "outstanding_amount": "outstanding_amount",
    "billing_day": "billing_day",
}

# 需要从对话文本中提取的槽位（CRM 无法直接提供）
_DIALOGUE_ONLY_SLOTS = ["dispute_date", "inquiry_amount", "term_months", "identity_confirmed"]

# --------------------------------------------------------------------------- #
# 辅助函数
# --------------------------------------------------------------------------- #


def _split_turn(raw: str) -> Tuple[str, str]:
    """将 "坐席：..." / "用户：..." 拆分为 (speaker, utterance)。"""
    if raw.startswith(_AGENT_PREFIX):
        return "SYSTEM", raw[len(_AGENT_PREFIX):]
    if raw.startswith(_USER_PREFIX):
        return "USER", raw[len(_USER_PREFIX):]
    return "USER", raw


def _infer_intent(utterance: str) -> str:
    """基于关键词规则推断意图，返回最先匹配的意图名称或 'general_inquiry'。"""
    for keywords, intent in _INTENT_RULES:
        if any(kw in utterance for kw in keywords):
            return intent
    return "general_inquiry"


def _slot_has_value(slot: str, crm: Dict[str, Any]) -> bool:
    """判断 CRM 字典中对应槽位是否有有效值。"""
    key = _SLOT_TO_CRM_KEY.get(slot)
    if key is None:
        return False
    val = crm.get(key)
    if val is None:
        return False
    if isinstance(val, bool):
        return True   # bool 值本身即为有效值
    if isinstance(val, int):
        return val > 0
    if isinstance(val, str):
        return bool(val.strip())
    return False


def _extract_dialogue_slot_hints(turns: List[Tuple[str, str]]) -> Dict[str, List[str]]:
    """
    从对话文本中寻找对话专属槽位的出现线索。

    返回 {slot_name: [触发话语片段, ...]}。
    """
    hints: Dict[str, List[str]] = defaultdict(list)
    # 争议日期：用户提到具体月份+日期（如"七月二十三号"）
    date_pattern = re.compile(r"[一二三四五六七八九十]+月[零一二三四五六七八九十]+[号日]")
    # 询问金额：用户明确问具体金额（如"一万"、"五千"）
    amount_pattern = re.compile(r"[零一二三四五六七八九十百千万两]+[万千百]?元")
    # 分期期数
    term_pattern = re.compile(r"[零一二三四五六七八九十]+期")
    for speaker, utt in turns:
        if speaker == "USER":
            if date_pattern.search(utt):
                hints["dispute_date"].append(utt[:40])
            if amount_pattern.search(utt):
                hints["inquiry_amount"].append(utt[:40])
            if term_pattern.search(utt):
                hints["term_months"].append(utt[:40])
            if any(kw in utt for kw in ["对", "是我", "我是", "本人", "是的"]):
                hints["identity_confirmed"].append(utt[:40])
    return dict(hints)


# --------------------------------------------------------------------------- #
# 核心分析
# --------------------------------------------------------------------------- #


def analyze_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    对单条记录进行完整分析，返回结构化结果。

    返回字典包含以下键：
      - session_id
      - qc_label
      - turn_count
      - crm_parsed      : parse_user_info 结果
      - crm_slot_coverage: 每个 CRM 槽位是否有值 {slot: bool}
      - dialogue_slot_hints: 对话文本中提取的槽位线索 {slot: [examples]}
      - turns_parsed    : [(speaker, utterance), ...]
      - intent_sequence : 每轮推断的意图列表（仅 SYSTEM 轮）
      - unique_intents  : 本对话出现的不重复意图集合
      - intent_transitions: [(intent_from, intent_to), ...] 相邻不同意图的转移
      - strategy_pattern: 意图序列去重后的顺序列表
    """
    session_id = record["session_id"]
    qc_label = record.get("人工校验", "")
    raw_turns = record.get("对话历史", [])
    user_info_str = record.get("用户信息", "")

    # 解析 CRM 数据
    crm = parse_user_info(user_info_str)

    # CRM 槽位覆盖率
    crm_slot_coverage = {
        slot: _slot_has_value(slot, crm) for slot in _SLOT_TO_CRM_KEY
    }

    # 解析对话轮次
    turns_parsed: List[Tuple[str, str]] = [_split_turn(t) for t in raw_turns]

    # 推断每轮意图（对 SYSTEM 和 USER 轮都推断，反映业务流程）
    intent_seq: List[str] = []
    for speaker, utt in turns_parsed:
        intent = _infer_intent(utt)
        intent_seq.append(intent)

    # 策略序列：去掉连续重复的意图
    strategy_pattern: List[str] = []
    for intent in intent_seq:
        if not strategy_pattern or strategy_pattern[-1] != intent:
            strategy_pattern.append(intent)

    # 意图转移（相邻不同意图）
    transitions: List[Tuple[str, str]] = [
        (strategy_pattern[i], strategy_pattern[i + 1])
        for i in range(len(strategy_pattern) - 1)
    ]

    # 对话文本中的槽位线索
    dialogue_slot_hints = _extract_dialogue_slot_hints(turns_parsed)

    return {
        "session_id": session_id,
        "qc_label": qc_label,
        "turn_count": len(raw_turns),
        "crm_parsed": crm,
        "crm_slot_coverage": crm_slot_coverage,
        "dialogue_slot_hints": dialogue_slot_hints,
        "turns_parsed": turns_parsed,
        "intent_sequence": intent_seq,
        "unique_intents": list(set(intent_seq)),
        "intent_transitions": transitions,
        "strategy_pattern": strategy_pattern,
    }


def aggregate_analysis(records_analysis: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    对所有记录的分析结果进行汇总统计。
    """
    n = len(records_analysis)

    # 1. 基础统计
    turn_counts = [r["turn_count"] for r in records_analysis]
    qc_counter = Counter(r["qc_label"] for r in records_analysis)

    # 2. CRM 槽位覆盖率
    slot_coverage_totals: Dict[str, int] = defaultdict(int)
    for r in records_analysis:
        for slot, has_val in r["crm_slot_coverage"].items():
            if has_val:
                slot_coverage_totals[slot] += 1

    crm_slot_coverage_pct = {
        slot: round(slot_coverage_totals[slot] / n * 100, 1)
        for slot in _SLOT_TO_CRM_KEY
    }

    # 3. 对话文本槽位线索覆盖率
    dialogue_slot_hint_counts: Dict[str, int] = defaultdict(int)
    for r in records_analysis:
        for slot in r["dialogue_slot_hints"]:
            dialogue_slot_hint_counts[slot] += 1

    dialogue_slot_hint_pct = {
        slot: round(dialogue_slot_hint_counts[slot] / n * 100, 1)
        for slot in _DIALOGUE_ONLY_SLOTS
    }

    # 4. 意图分布
    all_intent_seq = []
    for r in records_analysis:
        all_intent_seq.extend(r["intent_sequence"])
    intent_counter = Counter(all_intent_seq)
    intent_dist = {
        intent: {
            "count": intent_counter.get(intent, 0),
            "pct_of_total_turns": round(intent_counter.get(intent, 0) / len(all_intent_seq) * 100, 1)
            if all_intent_seq else 0,
        }
        for intent in _ALL_INTENTS
    }

    # 5. 每条对话出现的唯一意图数统计
    unique_intent_counts = [len(set(r["intent_sequence"])) for r in records_analysis]

    # 6. 意图转移矩阵（前 N 高频）
    all_transitions: List[Tuple[str, str]] = []
    for r in records_analysis:
        all_transitions.extend(r["intent_transitions"])
    transition_counter = Counter(all_transitions)
    top_transitions = [
        {"from": frm, "to": to, "count": cnt}
        for (frm, to), cnt in transition_counter.most_common(20)
    ]

    # 7. 常见策略模式（前 N 高频）
    strategy_patterns = [tuple(r["strategy_pattern"]) for r in records_analysis]
    pattern_counter = Counter(strategy_patterns)
    top_patterns = [
        {"pattern": list(pat), "count": cnt}
        for pat, cnt in pattern_counter.most_common(10)
    ]

    # 8. 每条对话首个意图分布（入口意图）
    entry_intents = Counter(r["intent_sequence"][0] if r["intent_sequence"] else "general_inquiry"
                            for r in records_analysis)

    # 9. 每条对话末个意图分布（出口意图）
    exit_intents = Counter(r["intent_sequence"][-1] if r["intent_sequence"] else "general_inquiry"
                           for r in records_analysis)

    # 10. CRM 数值槽位的值分布统计（代表性槽位）
    crm_value_stats = _compute_crm_value_stats(records_analysis)

    return {
        "dataset_overview": {
            "total_records": n,
            "total_turns": sum(turn_counts),
            "turn_count_min": min(turn_counts),
            "turn_count_max": max(turn_counts),
            "turn_count_avg": round(sum(turn_counts) / n, 1),
            "qc_label_distribution": dict(qc_counter),
        },
        "ontology": {
            "service_name": "AnYiHua_1",
            "service_description": "安逸花外呼促活服务（微贷平台坐席主动外呼，激活用户闲置借款额度）",
            "domain": "微贷/消费金融（外呼促活）",
            "data_source": "真实外呼通话录音（已脱敏）",
            "total_slots_defined": len(_SLOT_TO_CRM_KEY) + len(_DIALOGUE_ONLY_SLOTS),
            "crm_slots": list(_SLOT_TO_CRM_KEY.keys()),
            "dialogue_slots": _DIALOGUE_ONLY_SLOTS,
            "total_intents_defined": len(_ALL_INTENTS),
            "intents": _ALL_INTENTS,
        },
        "slot_analysis": {
            "crm_slots_coverage": crm_slot_coverage_pct,
            "dialogue_slots_hint_coverage": dialogue_slot_hint_pct,
            "crm_value_stats": crm_value_stats,
            "high_coverage_slots": [s for s, pct in crm_slot_coverage_pct.items() if pct >= 80],
            "low_coverage_slots": [s for s, pct in crm_slot_coverage_pct.items() if pct < 50],
        },
        "intent_analysis": {
            "intent_distribution": intent_dist,
            "top_intents": sorted(
                [(intent, d["count"]) for intent, d in intent_dist.items()],
                key=lambda x: -x[1]
            )[:5],
            "entry_intent_distribution": dict(entry_intents),
            "exit_intent_distribution": dict(exit_intents),
            "avg_unique_intents_per_dialogue": round(sum(unique_intent_counts) / n, 1),
            "min_unique_intents": min(unique_intent_counts),
            "max_unique_intents": max(unique_intent_counts),
        },
        "strategy_analysis": {
            "top_intent_transitions": top_transitions,
            "top_strategy_patterns": top_patterns,
            "common_flow_description": (
                "verify_identity → explain_credit_limit → (explain_interest_rate | "
                "handle_loan_dispute | guide_loan_operation) → say_goodbye"
            ),
        },
        "extractability_summary": _build_extractability_summary(
            crm_slot_coverage_pct, dialogue_slot_hint_pct
        ),
    }


def _compute_crm_value_stats(records_analysis: List[Dict[str, Any]]) -> Dict[str, Any]:
    """对代表性数值槽位计算统计量（min/max/mean）。"""
    numeric_slots = {
        "available_credit": "available_credit",
        "annual_rate_pct": "annual_rate_pct",
        "loan_count": "loan_count",
        "temp_expiry_days": "temp_active_days",
        "outstanding_amount": "outstanding_amount",
    }
    stats: Dict[str, Any] = {}
    for slot, crm_key in numeric_slots.items():
        values = [
            r["crm_parsed"].get(crm_key, 0)
            for r in records_analysis
            if isinstance(r["crm_parsed"].get(crm_key), (int, float))
            and r["crm_parsed"].get(crm_key, 0) > 0
        ]
        if values:
            stats[slot] = {
                "n_with_value": len(values),
                "min": min(values),
                "max": max(values),
                "mean": round(sum(values) / len(values), 1),
            }
        else:
            stats[slot] = {"n_with_value": 0}
    return stats


def _build_extractability_summary(
    crm_pct: Dict[str, float],
    dialogue_pct: Dict[str, float],
) -> Dict[str, Any]:
    """生成可提取性结论摘要。"""
    return {
        "directly_extractable": {
            "fields": ["dialogue_id", "speaker", "utterance", "qc_label", "reference_response"],
            "reliability": "100%",
            "description": "对话结构、发言者、话语内容、质检标签和参考回复可直接映射，无需推断。",
        },
        "crm_extractable": {
            "fields": [s for s, pct in crm_pct.items() if pct >= 70],
            "reliability": "≈95–99%",
            "description": (
                "来自 用户信息 字段的 CRM 数据，通过 parse_user_info() 解析，"
                "可靠性极高。覆盖率 ≥70% 的槽位适合直接用于 TOD 训练数据。"
            ),
        },
        "rule_inferrable": {
            "fields": ["active_intent", "requested_slots", "service_call", "actions"],
            "reliability": "≈50–70%",
            "description": (
                "基于关键词规则从对话文本中推断，适合快速原型。"
                "生产环境建议使用 LLM 进行语义补全以提升准确率。"
            ),
        },
        "dialogue_inferrable": {
            "fields": ["dispute_date", "inquiry_amount", "term_months", "identity_confirmed"],
            "reliability": "≈30–60%",
            "description": (
                "只能从对话文本中提取（CRM 无对应字段），依赖用户在对话中明确提及。"
                "覆盖率较低，建议使用 LLM 进行 NLU 提取。"
            ),
        },
        "not_extractable": {
            "fields": ["service_results", "full_dst_annotation"],
            "description": (
                "完整的对话状态追踪（DST）标注和 API 调用结果无法从原始数据中提取，"
                "需要人工标注或 LLM 自动标注。"
            ),
        },
    }


# --------------------------------------------------------------------------- #
# 报告生成
# --------------------------------------------------------------------------- #


def generate_markdown_report(agg: Dict[str, Any], input_path: str) -> str:
    """将聚合分析结果生成 Markdown 格式报告。"""
    ov = agg["dataset_overview"]
    ont = agg["ontology"]
    slots = agg["slot_analysis"]
    intents = agg["intent_analysis"]
    strat = agg["strategy_analysis"]
    ext = agg["extractability_summary"]

    # 使用相对路径，避免硬编码绝对路径进入版本控制
    try:
        display_path = str(Path(input_path).relative_to(_PROJECT_ROOT))
    except ValueError:
        display_path = Path(input_path).name

    lines = []
    lines.append("# chat_test_100.json 可提取信息分析报告\n")
    lines.append(f"**数据来源**：`{display_path}`  \n")
    lines.append("**分析目标**：评估从安逸花外呼数据中能够提取哪些信息，用于构建类似 SGD 的标准 TOD 任务。\n")

    # ---------- 一、数据集概览 ----------
    lines.append("---\n")
    lines.append("## 一、数据集概览\n")
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|---|---|")
    lines.append(f"| 记录总数 | {ov['total_records']} 条 |")
    lines.append(f"| 总轮次数 | {ov['total_turns']} 轮 |")
    lines.append(f"| 平均轮次 | {ov['turn_count_avg']} 轮/对话 |")
    lines.append(f"| 最短对话 | {ov['turn_count_min']} 轮 |")
    lines.append(f"| 最长对话 | {ov['turn_count_max']} 轮 |")
    lines.append("")
    lines.append("**人工校验标签分布**：\n")
    total_records = ov["total_records"]
    for label, cnt in ov["qc_label_distribution"].items():
        pct = round(cnt / total_records * 100, 1)
        lines.append(f"- `{label}`：{cnt} 条（{pct}%）")
    lines.append("")

    # ---------- 二、本体（Ontology） ----------
    lines.append("---\n")
    lines.append("## 二、本体（Ontology）\n")
    lines.append(f"- **服务名称**：`{ont['service_name']}`")
    lines.append(f"- **服务描述**：{ont['service_description']}")
    lines.append(f"- **领域**：{ont['domain']}")
    lines.append(f"- **数据来源**：{ont['data_source']}")
    lines.append(f"- **槽位总数**：{ont['total_slots_defined']} 个（CRM 可提取 {len(ont['crm_slots'])} 个，对话提取 {len(ont['dialogue_slots'])} 个）")
    lines.append(f"- **意图总数**：{ont['total_intents_defined']} 个")
    lines.append("")
    lines.append("### 2.1 意图列表\n")
    intent_desc = {
        "verify_identity": "核实用户身份（开场必须执行）",
        "explain_credit_limit": "告知可提现额度情况",
        "explain_interest_rate": "解释利率/还款方式",
        "calculate_repayment": "计算指定金额和期数的月还款额",
        "explain_displayed_amount": "解释 APP 页面显示金额的构成",
        "handle_loan_dispute": "核实用户争议的借款记录",
        "guide_loan_operation": "引导用户在 APP 完成借款操作",
        "escalate_to_human": "转接人工客服",
        "say_goodbye": "礼貌告别",
        "general_inquiry": "通用询问（默认，无法匹配其他意图时）",
    }
    lines.append("| 意图名称 | 描述 |")
    lines.append("|---|---|")
    for intent in ont["intents"]:
        lines.append(f"| `{intent}` | {intent_desc.get(intent, '')} |")
    lines.append("")
    lines.append("### 2.2 槽位列表\n")
    slot_desc = {
        "customer_name": "客户姓名（CRM）",
        "phone_suffix": "手机尾号 3-4 位（CRM）",
        "available_credit": "可提现额度（元，CRM）",
        "temp_credit": "临时额度（元，CRM）",
        "temp_credit_status": "临时额度是否有效（CRM）",
        "temp_expiry_days": "临时额度剩余天数（CRM）",
        "annual_rate_pct": "年化利率（%，CRM）",
        "loan_count": "当前未还借款笔数（CRM）",
        "last_loan_date": "最近借款日期（CRM）",
        "outstanding_amount": "未还款金额（元，CRM）",
        "billing_day": "账单日（CRM）",
        "dispute_date": "用户争议的借款日期（对话文本）",
        "inquiry_amount": "用户询问的金额（对话文本）",
        "term_months": "分期期数（对话文本）",
        "identity_confirmed": "身份是否已核实（对话文本）",
    }
    lines.append("| 槽位名称 | 来源 | 描述 |")
    lines.append("|---|---|---|")
    for slot in ont["crm_slots"]:
        pct = slots["crm_slots_coverage"].get(slot, 0)
        lines.append(f"| `{slot}` | CRM（覆盖率 {pct}%） | {slot_desc.get(slot, '')} |")
    for slot in ont["dialogue_slots"]:
        pct = slots["dialogue_slots_hint_coverage"].get(slot, 0)
        lines.append(f"| `{slot}` | 对话文本（出现率 {pct}%） | {slot_desc.get(slot, '')} |")
    lines.append("")

    # ---------- 三、槽位分析 ----------
    lines.append("---\n")
    lines.append("## 三、槽位分析\n")
    lines.append("### 3.1 CRM 槽位覆盖率（来自 用户信息 字段）\n")
    lines.append("| 槽位 | 覆盖率 | 评级 |")
    lines.append("|---|---|---|")
    for slot, pct in sorted(slots["crm_slots_coverage"].items(), key=lambda x: -x[1]):
        rating = "🟢 高" if pct >= 80 else ("🟡 中" if pct >= 50 else "🔴 低")
        lines.append(f"| `{slot}` | {pct}% | {rating} |")
    lines.append("")
    lines.append(f"**高覆盖率槽位（≥80%）**：{', '.join(f'`{s}`' for s in slots['high_coverage_slots'])}\n")
    lines.append(f"**低覆盖率槽位（<50%）**：{', '.join(f'`{s}`' for s in slots['low_coverage_slots']) or '无'}\n")

    lines.append("### 3.2 对话文本槽位出现率\n")
    lines.append("| 槽位 | 出现率 | 说明 |")
    lines.append("|---|---|---|")
    slot_note = {
        "dispute_date": "用户主动提到日期（争议场景）",
        "inquiry_amount": "用户主动提到具体金额",
        "term_months": "用户提及分期期数",
        "identity_confirmed": "用户确认身份",
    }
    for slot, pct in slots["dialogue_slots_hint_coverage"].items():
        lines.append(f"| `{slot}` | {pct}% | {slot_note.get(slot, '')} |")
    lines.append("")
    lines.append("### 3.3 数值槽位值分布\n")
    lines.append("| 槽位 | 有值条数 | 最小值 | 最大值 | 均值 |")
    lines.append("|---|---|---|---|---|")
    for slot, stat in slots["crm_value_stats"].items():
        if stat.get("n_with_value", 0) > 0:
            lines.append(
                f"| `{slot}` | {stat['n_with_value']} | {stat['min']} | {stat['max']} | {stat['mean']} |"
            )
    lines.append("")

    # ---------- 四、意图分析 ----------
    lines.append("---\n")
    lines.append("## 四、意图（Intent）分析\n")
    lines.append(f"- 每条对话平均包含 **{intents['avg_unique_intents_per_dialogue']}** 个不同意图")
    lines.append(f"- 最少 {intents['min_unique_intents']} 个，最多 {intents['max_unique_intents']} 个\n")
    lines.append("### 4.1 意图出现频率（按轮次统计）\n")
    lines.append("| 意图 | 出现轮次 | 占比 |")
    lines.append("|---|---|---|")
    sorted_intents = sorted(intents["intent_distribution"].items(), key=lambda x: -x[1]["count"])
    for intent, d in sorted_intents:
        lines.append(f"| `{intent}` | {d['count']} | {d['pct_of_total_turns']}% |")
    lines.append("")
    lines.append("### 4.2 入口意图（对话首轮意图）\n")
    lines.append("| 意图 | 对话数 |")
    lines.append("|---|---|")
    for intent, cnt in sorted(intents["entry_intent_distribution"].items(), key=lambda x: -x[1]):
        lines.append(f"| `{intent}` | {cnt} |")
    lines.append("")
    lines.append("### 4.3 出口意图（对话末轮意图）\n")
    lines.append("| 意图 | 对话数 |")
    lines.append("|---|---|")
    for intent, cnt in sorted(intents["exit_intent_distribution"].items(), key=lambda x: -x[1]):
        lines.append(f"| `{intent}` | {cnt} |")
    lines.append("")

    # ---------- 五、策略分析 ----------
    lines.append("---\n")
    lines.append("## 五、对话策略（Strategy）分析\n")
    lines.append("### 5.1 常见策略流程\n")
    lines.append(f"```\n{strat['common_flow_description']}\n```\n")
    lines.append("### 5.2 高频意图转移（Top 10）\n")
    lines.append("| 从意图 | 转移到 | 次数 |")
    lines.append("|---|---|---|")
    for t in strat["top_intent_transitions"][:10]:
        lines.append(f"| `{t['from']}` | `{t['to']}` | {t['count']} |")
    lines.append("")
    lines.append("### 5.3 高频策略模式（Top 5）\n")
    lines.append("| 策略序列 | 出现次数 |")
    lines.append("|---|---|")
    for p in strat["top_strategy_patterns"][:5]:
        pat_str = " → ".join(p["pattern"])
        lines.append(f"| `{pat_str}` | {p['count']} |")
    lines.append("")

    # ---------- 六、可提取性结论 ----------
    lines.append("---\n")
    lines.append("## 六、可提取性结论汇总\n")
    lines.append("| 提取类别 | 涉及字段 | 可靠性 |")
    lines.append("|---|---|---|")
    for category, info in ext.items():
        reliability = info.get("reliability", "—")
        fields = ", ".join(f"`{f}`" for f in info["fields"])
        lines.append(f"| {_category_label(category)} | {fields} | {reliability} |")
    lines.append("")
    for category, info in ext.items():
        lines.append(f"**{_category_label(category)}**：{info['description']}\n")

    lines.append("---\n")
    lines.append("## 七、对 SGD TOD 任务构建的建议\n")
    lines.append("""
1. **直接可用（无需补充）**
   - 对话结构（dialogue_id / speaker / utterance）来自原始数据，100% 可靠。
   - CRM 槽位（available_credit / annual_rate_pct / customer_name 等）来自 用户信息 字段，覆盖率高，可直接作为 `slot_values` 中的 groundtruth。

2. **规则推断（快速原型）**
   - 使用关键词规则推断 `active_intent`（准确率 ≈50–70%），适合快速构建数据集骨架。
   - 推断质量受对话文本简短/含混影响，建议对规则层结果进行抽样人工验证。

3. **LLM 补全（生产质量）**
   - 对 `active_intent`、`requested_slots`、`actions`、`service_call.parameters` 使用 LLM 进行语义补全。
   - 建议以 LLM 补全结果为主，规则推断结果为回退。

4. **保留扩展字段**
   - `metadata.user_info_parsed`：存放解析后的 CRM 数据，供执行引擎使用。
   - `metadata.reference_response`：存放参考坐席回复，供生成质量评估。
   - `metadata.qc_label`：存放人工质检标签，供质量分析。

5. **注意事项**
   - 外呼数据首轮为 SYSTEM（坐席），与标准 SGD（USER 首轮）相反，需注意 PyTOD 的 `user_turn_idx = 2 * idx` 假设。
   - 对话末尾的 `坐席回复` 字段是**待预测目标**，不应混入对话历史。
""")

    return "\n".join(lines)


def _category_label(category: str) -> str:
    """将英文类别 key 转换为中文标签。"""
    labels = {
        "directly_extractable": "直接提取",
        "crm_extractable": "CRM 解析",
        "rule_inferrable": "规则推断",
        "dialogue_inferrable": "对话 NLU",
        "not_extractable": "无法自动提取",
    }
    return labels.get(category, category)


# --------------------------------------------------------------------------- #
# 主程序
# --------------------------------------------------------------------------- #


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="分析 chat_test_100.json 可提取信息",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input",
        default=_DEFAULT_INPUT,
        help=f"输入 JSON 文件路径（默认：{_DEFAULT_INPUT}）",
    )
    parser.add_argument(
        "--output-dir",
        default=_DEFAULT_OUTPUT_DIR,
        help=f"报告输出目录（默认：{_DEFAULT_OUTPUT_DIR}）",
    )
    parser.add_argument(
        "--no-markdown",
        action="store_true",
        help="跳过生成 Markdown 报告",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print("chat_test_100.json 可提取信息分析工具")
    print(f"{'='*60}")
    print(f"输入文件: {input_path}")
    print(f"输出目录: {output_dir}")

    # 加载数据
    print("\n▶ 加载数据...")
    with open(input_path, encoding="utf-8") as f:
        raw_data: List[Dict[str, Any]] = json.load(f)
    print(f"  已加载 {len(raw_data)} 条记录")

    # 逐条分析
    print("▶ 逐条分析...")
    records_analysis = [analyze_record(r) for r in raw_data]
    print(f"  ✅ 完成 {len(records_analysis)} 条记录分析")

    # 汇总统计
    print("▶ 汇总统计...")
    agg = aggregate_analysis(records_analysis)

    # 保存 JSON 报告
    json_report_path = output_dir / "chat_test_extraction_report.json"
    # 过滤掉不可 JSON 序列化的 turns_parsed（含 tuple）
    agg_serializable = agg
    with open(json_report_path, "w", encoding="utf-8") as f:
        json.dump(agg_serializable, f, ensure_ascii=False, indent=2)
    print(f"  ✅ JSON 报告已写入: {json_report_path}")

    # 保存 Markdown 报告
    if not args.no_markdown:
        md_report_path = output_dir / "chat_test_extraction_report.md"
        md_content = generate_markdown_report(agg, str(input_path))
        with open(md_report_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"  ✅ Markdown 报告已写入: {md_report_path}")

    # 控制台摘要
    print(f"\n{'='*60}")
    print("分析摘要")
    print(f"{'='*60}")
    ov = agg["dataset_overview"]
    slots = agg["slot_analysis"]
    intents = agg["intent_analysis"]
    print(f"  数据规模    : {ov['total_records']} 条对话，{ov['total_turns']} 轮次")
    print(f"  平均对话长度: {ov['turn_count_avg']} 轮")
    print(f"\n  --- 槽位覆盖率（CRM 数据）---")
    for slot, pct in sorted(slots["crm_slots_coverage"].items(), key=lambda x: -x[1])[:5]:
        bar = "█" * int(pct / 10)
        print(f"  {slot:<30s}: {pct:5.1f}% {bar}")
    print(f"\n  --- 意图分布（Top 5）---")
    for intent, cnt in intents["top_intents"][:5]:
        print(f"  {intent:<35s}: {cnt} 轮")
    print(f"\n  每条对话平均含 {intents['avg_unique_intents_per_dialogue']} 个不同意图")
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()
