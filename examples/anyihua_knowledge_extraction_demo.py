"""
安逸花外呼知识提取演示（单轮对话 + langextract 溯源版）

演示如何使用 AnyihuaKnowledgeExtractor 从安逸花外呼多轮对话中提取带轮次归属
和字符级溯源的结构化知识，并可选择将结果转换为 SGD 数据集格式。

完整处理流程（4 步）：
  步骤 1：加载测试对话数据
    · 支持 chat_test_100.json（标准格式，含 session_id / 用户信息 / 对话历史）
    · 支持 chat_test_500.json（嵌套格式，含 label / query{用户信息/对话历史/坐席回复}）
    · 两种格式自动检测并归一化为统一结构

  步骤 2：基于 langextract 提取结构化知识（含溯源）
    · 逐轮解析对话，每轮作为独立文本单元，解决多轮对话对齐问题
    · LLM 输出 turn_idx（来自哪一轮）和 provenance_text（该轮话语的逐字片段）
    · WordAligner 仅对对应轮次的短文本做字符对齐，精度高
    · 提取结果（含溯源）保存为 JSON 文件

  步骤 3：将提取结果转换为 SGD 数据集格式
    · 每条对话生成带 frames / state / service_call 的标准 SGD 结构
    · 累积槽位状态（slot_values 跨轮合并）
    · 自动生成 schema.json（服务定义 + 槽位 + 意图）
    · 结果保存到指定输出目录

  步骤 4：统计 schema.json 与知识提取结果的匹配程度
    · 计算槽位覆盖率：提取出现的槽位有多少在 schema 中已预定义
    · 计算意图覆盖率：提取出现的意图有多少在 schema 中已预定义
    · 列出未覆盖的槽位和意图（可用于完善 schema 或启用开放模式）

核心特点：
  · 支持动态 Schema：槽位、意图均可自定义，不局限于预定义列表
  · 统计指标带中文说明

LLM 通过 contextmind/infra/llm_client.py 统一初始化，配置从 .env 文件自动加载。

运行示例::

    # 使用默认参数（读取前 2 条对话，同时输出 SGD 格式）
    python examples/anyihua_knowledge_extraction_demo.py

    # 批量处理前 10 条，指定输出路径，并导出 SGD 格式
    python examples/anyihua_knowledge_extraction_demo.py \\
        --num 10 \\
        --output data/my_results.json \\
        --sgd-dir data/my_sgd/

    # 同时处理两个文件（chat_test_100.json 前 2 条 + chat_test_500.json 前 5 条）
    python examples/anyihua_knowledge_extraction_demo.py \\
        --num 2 --num2 5

    # 使用开放 Schema（允许 LLM 自由命名槽位/意图，适合探索新业务）
    python examples/anyihua_knowledge_extraction_demo.py \\
        --scene-name 银行贷款外呼 \\
        --slot-open-ended \\
        --intent-open-ended

    # 不输出 SGD 格式（仅保存原始提取结果）
    python examples/anyihua_knowledge_extraction_demo.py --no-sgd

参数说明（见 --help）：
    --data              原始对话 JSON 文件路径（默认：chat_test_100.json）
    --data2             第二个对话 JSON 文件路径（默认：chat_test_500.json）
    --num               从 --data 文件处理的对话数量（默认：2；-1 表示全部）
    --num2              从 --data2 文件处理的对话数量（默认：0，即不处理）
    --output            提取结果 JSON 保存路径
    --sgd-dir           SGD 格式输出目录（默认：data/anyihua_sgd/）
    --no-sgd            禁用 SGD 格式输出
    --scene-name        业务场景名称（影响 LLM 提示词）
    --slot-open-ended   允许 LLM 在预定义槽位之外自由提取新槽位
    --intent-open-ended 允许 LLM 在预定义意图之外自由提取新意图
    --show-turns        打印每条对话的前几轮内容

环境要求：
    在 .env 文件中配置 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 等参数。
    （参考 .env.example）
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import List, Optional

# 确保项目根目录在 sys.path 中
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from contextmind.scenarios.anyihua.knowledge_extraction import (
    AnyihuaKnowledgeExtractor,
    DEFAULT_SCHEMA,
    ExtractionSchema,
    IntentDefinition,
    SlotDefinition,
    save_as_sgd,
    save_results,
)

# 默认路径
_DEFAULT_DATA_PATH = _ROOT / "resources" / "data" / "chat_test_100.json"
_DEFAULT_DATA2_PATH = _ROOT / "resources" / "data" / "chat_test_500.json"
_DEFAULT_SAVE_PATH = _ROOT / "data" / "anyihua_knowledge_extraction_results.json"
_DEFAULT_SGD_DIR = _ROOT / "data" / "anyihua_sgd"


# --------------------------------------------------------------------------- #
# 数据格式归一化
# --------------------------------------------------------------------------- #


def _normalize_record(record: dict, source_file: Optional[str] = None) -> dict:
    """
    将不同来源的对话记录归一化为统一的标准格式。

    支持两种格式：

    **格式 A — chat_test_100.json 标准格式**（直接透传）::

        {
          "session_id": "...",
          "用户信息": "...",
          "对话历史": [...],
          "坐席回复": "...",
          "人工校验": "..."
        }

    **格式 B — chat_test_500.json 嵌套格式**（展平后透传）::

        {
          "label": "无标签命中",
          "query": {
            "用户信息": "...",
            "对话历史": [...],
            "坐席回复": "..."
          }
        }

    参数:
        record:      原始对话记录字典
        source_file: 来源文件名（用于生成 session_id，可选）

    返回:
        归一化后的对话记录字典（标准格式）
    """
    # 格式 A：已含 对话历史 字段，直接返回
    if "对话历史" in record:
        return record

    # 格式 B：含 query 嵌套结构，展平
    if "query" in record and isinstance(record["query"], dict):
        query = record["query"]
        normalized: dict = dict(query)  # 复制 用户信息 / 对话历史 / 坐席回复
        # 将 label 映射到 人工校验
        if "label" in record:
            normalized.setdefault("人工校验", record["label"])
        # 生成唯一 session_id（格式 B 无此字段）
        if "session_id" not in normalized:
            import hashlib
            raw = json.dumps(record, ensure_ascii=False, sort_keys=True)
            h = hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]
            prefix = Path(source_file).stem if source_file else "dlg"
            normalized["session_id"] = f"{prefix}_{h}"
        return normalized

    # 未知格式：原样返回，让提取器自行处理（或记录警告）
    return record


def _load_and_normalize(
    file_path: Path,
    num: int,
) -> List[dict]:
    """
    加载并归一化指定 JSON 文件中的对话记录。

    参数:
        file_path: JSON 文件路径
        num:       最多加载的记录数（-1 表示全部）

    返回:
        归一化后的对话记录列表
    """
    if not file_path.exists():
        print(f"[警告] 数据文件不存在，跳过: {file_path}")
        return []

    raw: List[dict] = json.loads(file_path.read_text(encoding="utf-8"))
    total = len(raw)
    take = total if num == -1 else min(num, total)
    records = [_normalize_record(r, source_file=str(file_path)) for r in raw[:take]]
    print(f"  · {file_path.name}: 共 {total} 条，本次加载前 {take} 条")
    return records


# --------------------------------------------------------------------------- #
# 打印辅助函数
# --------------------------------------------------------------------------- #


def _print_result(result, show_turns: bool = True, show_stats_desc: bool = True) -> None:
    """
    格式化打印单条提取结果。

    参数:
        result:           ExtractionResult 对象
        show_turns:       是否打印对话轮次预览
        show_stats_desc:  是否在统计字段旁显示中文说明
    """
    print(f"\n{'=' * 72}")
    print(f"对话 ID : {result.dialogue_id}")
    n_agent = sum(1 for _, sp, _ in result.turns if sp == "坐席")
    n_user = sum(1 for _, sp, _ in result.turns if sp == "用户")
    print(f"对话轮次: 共 {len(result.turns)} 轮（坐席 {n_agent} 轮 / 用户 {n_user} 轮）")

    if show_turns and result.turns:
        print("\n── 对话内容（前 6 轮）──")
        for idx, sp, utt in result.turns[:6]:
            print(f"  [第{idx+1}轮({sp})] {utt[:60]}{'…' if len(utt) > 60 else ''}")
        if len(result.turns) > 6:
            print(f"  … 还有 {len(result.turns) - 6} 轮")

    print(
        f"\n── 提取结果 {len(result.knowledge_items)} 条 "
        f"（溯源率 {result.stats.get('alignment_rate', 0):.1%}） ──"
    )

    # 按类别分组显示
    for cls_label, cls_key in [
        ("槽位值 slot_value", "slot_value"),
        ("用户意图 intent", "intent"),
        ("关键事实 fact", "fact"),
    ]:
        items = [it for it in result.knowledge_items if it.extraction_class == cls_key]
        if not items:
            continue
        print(f"\n  【{cls_label}】")
        for item in items:
            print(f"    · {item.label}: {item.value}")
            print(f"      溯源: {item.provenance}")

    # 统计字段（带说明）
    print(f"\n── 统计 ──")
    if show_stats_desc:
        for key, info in result.stats_explained.items():
            desc = info["description"]
            val = info["value"]
            # 截短说明避免过宽
            desc_short = desc[:60] + "…" if len(desc) > 60 else desc
            print(f"  {key:<22}: {str(val):<8}  # {desc_short}")
    else:
        for k, v in result.stats.items():
            print(f"  {k}: {v}")


def _parse_slot_additions(specs: Optional[List[str]]) -> List[SlotDefinition]:
    """
    将命令行 --add-slot 参数解析为 SlotDefinition 列表。

    格式：``name:description``（冒号分隔）
    示例：``loan_purpose:用户借款目的（如装修、教育）``

    参数:
        specs: 原始字符串列表，每项格式为 ``name:description``

    返回:
        SlotDefinition 列表；格式错误的项将被跳过并打印警告。
    """
    if not specs:
        return []
    result: List[SlotDefinition] = []
    for spec in specs:
        if ":" not in spec:
            print(f"[警告] --add-slot 格式错误（应为 name:description）：{spec!r}，已跳过")
            continue
        name, _, desc = spec.partition(":")
        name = name.strip()
        desc = desc.strip()
        if not name:
            print(f"[警告] --add-slot 槽位名为空：{spec!r}，已跳过")
            continue
        result.append(SlotDefinition(name, desc or f"动态新增槽位：{name}"))
    return result


def _parse_intent_additions(specs: Optional[List[str]]) -> List[IntentDefinition]:
    """
    将命令行 --add-intent 参数解析为 IntentDefinition 列表。

    格式：``name:description``（冒号分隔）
    示例：``complain_service:用户对服务质量表达不满``

    参数:
        specs: 原始字符串列表，每项格式为 ``name:description``

    返回:
        IntentDefinition 列表；格式错误的项将被跳过并打印警告。
    """
    if not specs:
        return []
    result: List[IntentDefinition] = []
    for spec in specs:
        if ":" not in spec:
            print(f"[警告] --add-intent 格式错误（应为 name:description）：{spec!r}，已跳过")
            continue
        name, _, desc = spec.partition(":")
        name = name.strip()
        desc = desc.strip()
        if not name:
            print(f"[警告] --add-intent 意图名为空：{spec!r}，已跳过")
            continue
        result.append(IntentDefinition(name, desc or f"动态新增意图：{name}"))
    return result


def _print_schema_coverage_report(coverage: dict) -> None:
    """
    格式化打印 schema.json 与知识提取结果的匹配程度报告。

    参数:
        coverage: save_as_sgd() 返回的 summary["schema_coverage"] 字典，包含：
            extracted_slots    - 提取结果中出现的所有槽位名
            extracted_intents  - 提取结果中出现的所有意图名
            schema_slots       - schema.json 中预定义的所有槽位名
            schema_intents     - schema.json 中预定义的所有意图名
            uncovered_slots    - 提取出现但 schema 未预定义的槽位（未覆盖）
            uncovered_intents  - 提取出现但 schema 未预定义的意图（未覆盖）
            slot_coverage_pct  - 槽位覆盖率（%）
            intent_coverage_pct- 意图覆盖率（%）
            note               - 覆盖情况文字说明
    """
    print(f"\n{'=' * 72}")
    print("【步骤 4：schema.json 与知识提取结果匹配度统计】")
    print(f"{'=' * 72}")

    slot_cov = coverage.get("slot_coverage_pct", 0.0)
    intent_cov = coverage.get("intent_coverage_pct", 0.0)
    extracted_slots = coverage.get("extracted_slots", [])
    extracted_intents = coverage.get("extracted_intents", [])
    schema_slots = coverage.get("schema_slots", [])
    schema_intents = coverage.get("schema_intents", [])
    uncovered_slots = coverage.get("uncovered_slots", [])
    uncovered_intents = coverage.get("uncovered_intents", [])

    covered_slots = sorted(set(extracted_slots) & set(schema_slots))
    covered_intents = sorted(set(extracted_intents) & set(schema_intents))

    print(f"\n  ── 槽位（Slot）匹配 ──")
    print(f"  schema.json 预定义槽位数 : {len(schema_slots)}")
    print(f"  提取结果中出现的槽位数   : {len(extracted_slots)}")
    print(f"  已覆盖（交集）           : {len(covered_slots)} 个  {covered_slots}")
    if uncovered_slots:
        print(f"  未覆盖（仅在提取中出现） : {len(uncovered_slots)} 个  {uncovered_slots}")
    print(f"  槽位覆盖率               : {slot_cov:.1f}%")

    print(f"\n  ── 意图（Intent）匹配 ──")
    print(f"  schema.json 预定义意图数 : {len(schema_intents)}")
    print(f"  提取结果中出现的意图数   : {len(extracted_intents)}")
    print(f"  已覆盖（交集）           : {len(covered_intents)} 个  {covered_intents}")
    if uncovered_intents:
        print(f"  未覆盖（仅在提取中出现） : {len(uncovered_intents)} 个  {uncovered_intents}")
    print(f"  意图覆盖率               : {intent_cov:.1f}%")

    print(f"\n  备注: {coverage.get('note', '')}")

    # 总结行
    overall = (slot_cov + intent_cov) / 2
    print(f"\n  综合覆盖率（槽位+意图均值）: {overall:.1f}%")
    if uncovered_slots or uncovered_intents:
        print(
            "  💡 建议：将上述未覆盖项加入 schema 或使用 --slot-open-ended / "
            "--intent-open-ended 启用开放模式自动发现。"
        )
    else:
        print("  ✅ 所有提取项均已在 schema.json 中预定义，覆盖完整。")
    print(f"{'=' * 72}")


def _build_schema(args: argparse.Namespace) -> ExtractionSchema:
    """
    根据命令行参数构造 ExtractionSchema。

    · 若无任何修改标志，使用 DEFAULT_SCHEMA（全套预定义）。
    · 若指定了 --add-slot / --add-intent，在 DEFAULT_SCHEMA 基础上新增对应项。
    · 若指定了 --scene-name 不同的名称或开放模式，同时应用对应修改。

    动态新增规则：
        - 新增槽位/意图会追加到预定义列表末尾（`general_inquiry` 意图始终保持最后）
        - 与预定义列表中已有名称相同的项将被跳过，并打印提示信息
    """
    extra_slots = _parse_slot_additions(getattr(args, "add_slot", None))
    extra_intents = _parse_intent_additions(getattr(args, "add_intent", None))

    has_modifications = (
        args.scene_name != DEFAULT_SCHEMA.scene_name
        or args.slot_open_ended
        or args.intent_open_ended
        or extra_slots
        or extra_intents
    )

    if not has_modifications:
        return DEFAULT_SCHEMA

    # 构建最终槽位列表：预定义 + 去重后的新增项
    existing_slot_names = {s.name for s in DEFAULT_SCHEMA.slots}
    new_slots: List[SlotDefinition] = []
    for slot in extra_slots:
        if slot.name in existing_slot_names:
            print(f"[提示] 槽位 '{slot.name}' 已在预定义 Schema 中存在，跳过新增")
        else:
            new_slots.append(slot)
            existing_slot_names.add(slot.name)

    # 构建最终意图列表：预定义（含 general_inquiry 兜底）+ 去重后的新增项
    existing_intent_names = {i.name for i in DEFAULT_SCHEMA.intents}
    # 将 general_inquiry（兜底意图）移到末尾
    base_intents_without_fallback = [
        i for i in DEFAULT_SCHEMA.intents if i.name != "general_inquiry"
    ]
    fallback_intent = [i for i in DEFAULT_SCHEMA.intents if i.name == "general_inquiry"]

    new_intents: List[IntentDefinition] = []
    for intent in extra_intents:
        if intent.name in existing_intent_names:
            print(f"[提示] 意图 '{intent.name}' 已在预定义 Schema 中存在，跳过新增")
        else:
            new_intents.append(intent)
            existing_intent_names.add(intent.name)

    final_intents = base_intents_without_fallback + new_intents + fallback_intent

    schema = dataclasses.replace(
        DEFAULT_SCHEMA,
        scene_name=args.scene_name,
        slots=DEFAULT_SCHEMA.slots + new_slots,
        intents=final_intents,
        slot_open_ended=args.slot_open_ended,
        intent_open_ended=args.intent_open_ended,
    )

    # 打印变更摘要
    if new_slots or new_intents:
        print(f"\n[Schema 扩展] 在预定义 Schema 基础上新增：")
        if new_slots:
            print(f"  新增槽位 ({len(new_slots)} 个)：{[s.name for s in new_slots]}")
        if new_intents:
            print(f"  新增意图 ({len(new_intents)} 个)：{[i.name for i in new_intents]}")

    return schema


# --------------------------------------------------------------------------- #
# 参数解析
# --------------------------------------------------------------------------- #


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="安逸花外呼对话知识提取演示（支持 SGD 格式输出 + 动态 Schema）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例：
  # 默认（前 2 条对话，输出 SGD 格式）
  python examples/anyihua_knowledge_extraction_demo.py

  # 批量处理前 10 条（含 schema 覆盖率报告）
  python examples/anyihua_knowledge_extraction_demo.py --num 10

  # 同时处理两个文件（chat_test_100.json 前 2 条 + chat_test_500.json 前 5 条）
  python examples/anyihua_knowledge_extraction_demo.py --num 2 --num2 5

  # 使用开放 Schema（LLM 可自由命名槽位和意图）
  python examples/anyihua_knowledge_extraction_demo.py --slot-open-ended --intent-open-ended

  # 动态新增槽位（格式：name:description）
  python examples/anyihua_knowledge_extraction_demo.py \\
      --add-slot "loan_purpose:用户借款目的（如装修、教育）" \\
      --add-slot "preferred_term:用户偏好的还款期数"

  # 动态新增意图
  python examples/anyihua_knowledge_extraction_demo.py \\
      --add-intent "complain_service:用户对服务质量或态度表达不满"

  # 不输出 SGD 格式
  python examples/anyihua_knowledge_extraction_demo.py --no-sgd
""",
    )

    # ── 数据 & 输出路径 ──
    parser.add_argument(
        "--data",
        type=Path,
        default=_DEFAULT_DATA_PATH,
        metavar="PATH",
        help=f"第一个对话 JSON 文件路径（默认：{_DEFAULT_DATA_PATH.relative_to(_ROOT)}）",
    )
    parser.add_argument(
        "--data2",
        type=Path,
        default=_DEFAULT_DATA2_PATH,
        metavar="PATH",
        help=(
            f"第二个对话 JSON 文件路径，支持 chat_test_500.json 的嵌套格式"
            f"（默认：{_DEFAULT_DATA2_PATH.relative_to(_ROOT)}）"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_DEFAULT_SAVE_PATH,
        metavar="PATH",
        help=f"提取结果 JSON 保存路径（默认：{_DEFAULT_SAVE_PATH.relative_to(_ROOT)}）",
    )
    parser.add_argument(
        "--sgd-dir",
        type=Path,
        default=_DEFAULT_SGD_DIR,
        metavar="DIR",
        help=f"SGD 格式输出目录（默认：{_DEFAULT_SGD_DIR.relative_to(_ROOT)}）",
    )
    parser.add_argument(
        "--no-sgd",
        action="store_true",
        default=False,
        help="禁用 SGD 格式输出（仅保存原始提取结果 JSON）",
    )

    # ── 处理数量 ──
    parser.add_argument(
        "--num",
        type=int,
        default=2,
        metavar="N",
        help="从 --data 文件处理的对话数量（默认：2；-1 表示全部）",
    )
    parser.add_argument(
        "--num2",
        type=int,
        default=0,
        metavar="N",
        help=(
            "从 --data2 文件（chat_test_500.json）额外加载的对话数量"
            "（默认：0，即不加载；-1 表示全部）"
        ),
    )

    # ── Schema 设置 ──
    schema_group = parser.add_argument_group("Schema 设置（动态提取 Schema）")
    schema_group.add_argument(
        "--scene-name",
        type=str,
        default=DEFAULT_SCHEMA.scene_name,
        metavar="NAME",
        help=f"业务场景名称，用于 LLM 提示词（默认：{DEFAULT_SCHEMA.scene_name}）",
    )
    schema_group.add_argument(
        "--slot-open-ended",
        action="store_true",
        default=False,
        help="允许 LLM 在预定义槽位之外自由提取新槽位（开放槽位模式）",
    )
    schema_group.add_argument(
        "--intent-open-ended",
        action="store_true",
        default=False,
        help="允许 LLM 在预定义意图之外自由提取新意图（开放意图模式）",
    )
    schema_group.add_argument(
        "--add-slot",
        action="append",
        dest="add_slot",
        metavar="name:description",
        default=None,
        help=(
            "动态新增槽位（格式：name:description，可重复使用）。"
            "新槽位追加到预定义槽位之后，与已有槽位同名时跳过。"
            "示例：--add-slot \"loan_purpose:用户借款目的\""
        ),
    )
    schema_group.add_argument(
        "--add-intent",
        action="append",
        dest="add_intent",
        metavar="name:description",
        default=None,
        help=(
            "动态新增意图（格式：name:description，可重复使用）。"
            "新意图追加到 general_inquiry 兜底意图之前，与已有意图同名时跳过。"
            "示例：--add-intent \"complain_service:用户对服务质量表达不满\""
        ),
    )

    # ── 显示设置 ──
    display_group = parser.add_argument_group("显示设置")
    display_group.add_argument(
        "--show-turns",
        action="store_true",
        default=False,
        help="打印每条对话的前 6 轮内容（批量模式默认关闭）",
    )
    display_group.add_argument(
        "--no-stats-desc",
        action="store_true",
        default=False,
        help="不在统计字段旁显示中文说明",
    )

    return parser.parse_args()


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #


def main() -> None:
    args = _parse_args()

    # ════════════════════════════════════════════════════════════════════════ #
    # 步骤 1：加载测试对话数据
    # ════════════════════════════════════════════════════════════════════════ #
    print(f"{'=' * 72}")
    print("【步骤 1：加载测试对话数据】")
    print(f"{'=' * 72}")

    # 从 --data（默认 chat_test_100.json）加载
    selected: List[dict] = _load_and_normalize(args.data, args.num)

    # 从 --data2（默认 chat_test_500.json）额外加载（num2 > 0 时）
    if args.num2 != 0:
        extra = _load_and_normalize(args.data2, args.num2)
        selected.extend(extra)
        print(f"  合并后共 {len(selected)} 条对话待处理")
    elif args.data2.exists():
        print(f"  提示：可通过 --num2 N 同时加载 {args.data2.name}（当前跳过）")

    if not selected:
        print("[错误] 未加载到任何对话数据，请检查 --data / --num 参数")
        sys.exit(1)

    num = len(selected)
    print(f"\n  本次共处理 {num} 条对话")
    print(f"  提取结果将保存至: {args.output}")
    if not args.no_sgd:
        print(f"  SGD 格式将保存至: {args.sgd_dir}/")

    # ── 构建 Schema ──
    schema = _build_schema(args)
    if schema is not DEFAULT_SCHEMA:
        print(
            f"\nSchema 设置: 场景={schema.scene_name}, "
            f"槽位开放={schema.slot_open_ended}, "
            f"意图开放={schema.intent_open_ended}"
        )
    print()

    # ── 初始化提取器 ──
    extractor = AnyihuaKnowledgeExtractor(schema=schema)

    # ════════════════════════════════════════════════════════════════════════ #
    # 步骤 2：基于 langextract 提取结构化知识（含溯源），保存为 JSON
    # ════════════════════════════════════════════════════════════════════════ #
    print(f"{'=' * 72}")
    print("【步骤 2：基于 langextract 提取结构化知识（含知识溯源）】")
    print(f"{'=' * 72}")

    # ── 单条提取演示（仅在 num >= 1 时执行）──
    if num >= 1:
        print("\n── 演示：单条提取（含轮次归属与字符级溯源）──")
        result = extractor.extract(selected[0])
        _print_result(
            result,
            show_turns=True,
            show_stats_desc=not args.no_stats_desc,
        )

    # ── 批量提取（结果自动保存为 JSON 文件）──
    if num > 1:
        print(f"\n── 批量提取（共 {num} 条）— 结果自动保存为 JSON 文件 ──")
        results = extractor.extract_batch(
            selected,
            save_path=args.output,
        )
        for r in results[1:]:  # 第 0 条已在演示中打印
            _print_result(
                r,
                show_turns=args.show_turns,
                show_stats_desc=not args.no_stats_desc,
            )
        print(f"\n✅ 步骤 2 完成：提取结果（含溯源）已保存至: {args.output}")
    else:
        # 仅 1 条时也保存
        results = [result]
        save_results(results, args.output)
        print(f"\n✅ 步骤 2 完成：提取结果（含溯源）已保存至: {args.output}")

    # ════════════════════════════════════════════════════════════════════════ #
    # 步骤 3 & 4：转换为 SGD 格式 + schema 覆盖率统计
    # ════════════════════════════════════════════════════════════════════════ #
    if not args.no_sgd:
        print(f"\n{'=' * 72}")
        print("【步骤 3：将原始对话数据转换为 SGD 数据集格式】")
        print(f"{'=' * 72}")
        summary = save_as_sgd(
            results=results,
            raw_dialogues=selected[:len(results)],
            output_dir=args.sgd_dir,
            extraction_schema=schema,
        )
        print(f"  对话数  : {summary['dialogues']}")
        print(f"  总轮次  : {summary['turns']}")
        if summary.get("discovered_schema_items"):
            print(f"  Schema 新增: {summary['discovered_schema_items']} 项（开放模式发现）")
        print(f"  输出目录: {summary['output_dir']}")
        print(f"  生成文件: schema.json, dialogues_*.json, conversion_summary.json")
        print(f"\n✅ 步骤 3 完成：SGD 格式已保存至: {args.sgd_dir}/")

        # 步骤 4：打印覆盖率报告
        if "schema_coverage" in summary:
            _print_schema_coverage_report(summary["schema_coverage"])
            print(f"✅ 步骤 4 完成：schema 覆盖率报告已打印（完整数据见 conversion_summary.json）")




if __name__ == "__main__":
    main()
