"""
安逸花外呼 · Schema 归纳与引导提取演示（LLM 驱动）

本演示展示两个 LLM 驱动的核心能力以及归纳结果的持久化与格式对比：

功能一（--mode induce）：Schema 归纳
    从原始（未标注）安逸花外呼对话中，使用 LLM 自动归纳出
    完善、丰富、准确的 Schema 数据（包含槽位描述、分类标志、
    可选值、意图描述、所需/可选槽位等元信息）。
    归纳结果自动保存为 SGD JSON 数组格式文件（--output 指定路径），
    并可选择与参考 SGD Schema 做字段对齐分析（--compare）。

功能二（--mode extract）：Schema 引导的细粒度信息提取
    给定一个预定义 Schema（如 resources/anyihua_sgd/schema.json），
    对新的外呼对话使用 LLM 提取精准、细粒度的结构化 JSON。

功能三（--mode full）：端到端流程
    先归纳 Schema（并保存文件），再用归纳出的 Schema 提取信息，
    最后显示与参考 SGD Schema 的对齐结果和 langextract 格式对比。

功能四（--mode compare）：格式对比（离线，无需 LLM）
    从现有 SGD schema.json 直接生成三方格式对比报告，
    对比 PartialServiceSchema / SGD / langextract 三种格式的异同。

用法（需要有效的 LLM API 配置）:
    cd /path/to/ContextMind

    # 在 .env 中配置 LLM_API_KEY / LLM_BASE_URL（或其他等效变量）

    # 功能一：归纳 Schema 并保存（默认保存到 resources/anyihua_sgd/induced_schema.json）
    python examples/anyihua_schema_induction_demo.py --mode induce --limit 10

    # 功能一：归纳后与参考 SGD Schema 做字段对齐分析
    python examples/anyihua_schema_induction_demo.py --mode induce --limit 10 --compare

    # 功能一：指定输出路径
    python examples/anyihua_schema_induction_demo.py --mode induce --limit 10 \\
        --output /tmp/my_schema.json

    # 功能二：用预定义 Schema 提取对话信息
    python examples/anyihua_schema_induction_demo.py --mode extract --limit 3

    # 功能三：端到端（归纳 + 保存 + 提取 + 对比）
    python examples/anyihua_schema_induction_demo.py --mode full --limit 5

    # 功能四：格式对比（离线，无需 LLM）
    python examples/anyihua_schema_induction_demo.py --mode compare
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from contextmind.infra.llm_client import LLMConfig, SimpleLLMClient
from contextmind.scenarios.anyihua.schema_extraction import (
    PartialServiceSchema,
    align_schema_with_sgd,
    extract_dialogue_info,
    format_comparison_report,
    induce_schema_with_llm,
    save_schema_as_sgd,
    schema_from_sgd_file,
)

_DEFAULT_DATA = _PROJECT_ROOT / "resources" / "data" / "chat_test_100.json"
_DEFAULT_SCHEMA = _PROJECT_ROOT / "resources" / "anyihua_sgd" / "schema.json"
_DEFAULT_OUTPUT = _PROJECT_ROOT / "resources" / "anyihua_sgd" / "induced_schema.json"
_DEFAULT_SERVICE_NAME = "AnYiHua_1"


# --------------------------------------------------------------------------- #
# 辅助函数
# --------------------------------------------------------------------------- #


def _hr(title: str = "") -> None:
    """打印带标题的分隔线。"""
    width = 72
    if title:
        pad = (width - len(title) - 2) // 2
        print(f"\n{'─' * pad} {title} {'─' * pad}")
    else:
        print("\n" + "─" * width)


def _load_dialogues(data_path: Path, limit: int) -> List[Dict[str, Any]]:
    """从 chat_test JSON 文件加载对话数据。"""
    if not data_path.exists():
        print(f"⚠️  数据文件不存在: {data_path}")
        sys.exit(1)
    data: List[Dict[str, Any]] = json.loads(data_path.read_text(encoding="utf-8"))
    selected = data[:limit]
    print(f"✅ 加载对话数据: {data_path.name}（共 {len(data)} 条，使用前 {len(selected)} 条）")
    return selected


def _init_llm() -> SimpleLLMClient:
    """初始化 LLM 客户端（从环境变量加载配置）。"""
    try:
        config = LLMConfig.from_env()
        client = SimpleLLMClient(config)
        print(f"✅ LLM 客户端初始化成功（model: {config.model}）")
        return client
    except Exception as e:
        print(f"❌ LLM 初始化失败: {e}")
        print("请在 .env 文件中设置 LLM_API_KEY / LLM_BASE_URL 等配置。")
        sys.exit(1)


def _print_schema_summary(schema: PartialServiceSchema) -> None:
    """打印 Schema 摘要。"""
    print(f"\n  服务名:   {schema.service_name}")
    if schema.description:
        print(f"  描述:     {schema.description}")
    print(f"  槽位数:   {len(schema.slots)}")
    print(f"  意图数:   {len(schema.intents)}")

    if schema.slots:
        print(f"\n  槽位列表:")
        for slot in schema.slots:
            cat_flag = "（分类）" if slot.is_categorical else ""
            desc = f" — {slot.description}" if slot.description else ""
            vals = f" 可选值: {slot.possible_values}" if slot.possible_values else ""
            print(f"    · {slot.name}{cat_flag}{desc}{vals}")

    if schema.intents:
        print(f"\n  意图列表:")
        for intent in schema.intents:
            desc = f" — {intent.description}" if intent.description else ""
            req = f" 必需槽位: {intent.required_slots}" if intent.required_slots else ""
            print(f"    · {intent.name}{desc}{req}")


def _save_and_report(
    schema: PartialServiceSchema,
    output_path: Path,
    reference_schema_path: Optional[Path],
    do_compare: bool,
) -> None:
    """
    将归纳出的 Schema 保存为 SGD JSON 文件，并可选显示格式对比。

    参数:
        schema:                归纳出的 Schema
        output_path:           保存路径（SGD JSON 数组格式）
        reference_schema_path: 参考 SGD schema.json 路径（用于对齐分析）
        do_compare:            是否显示三方格式对比报告
    """
    # 保存
    save_schema_as_sgd(schema, output_path)
    print(f"\n💾 归纳 Schema 已保存（SGD JSON 格式）: {output_path}")

    # 读取参考 Schema（用于对齐）
    ref_schema: Optional[PartialServiceSchema] = None
    if reference_schema_path and reference_schema_path.exists():
        ref_schema = schema_from_sgd_file(reference_schema_path)

    # 字段对齐分析
    if ref_schema is not None:
        _hr("字段对齐分析（归纳 Schema vs 参考 SGD Schema）")
        alignment = align_schema_with_sgd(schema, ref_schema)
        print(alignment["summary"])
        cov = alignment["coverage_pct"]
        print(f"\n  槽位覆盖率: {cov['slot_coverage']:.0%}  "
              f"意图覆盖率: {cov['intent_coverage']:.0%}")

        # 显示有字段差异的匹配槽位
        diffed = [m for m in alignment["slot_alignment"]["matched"] if m["field_diffs"]]
        if diffed:
            print(f"\n  有字段差异的匹配槽位（前 5 个）:")
            for m in diffed[:5]:
                print(f"    · {m['name']}: {json.dumps(m['field_diffs'], ensure_ascii=False)[:120]}")

    # 三方格式对比报告
    if do_compare:
        _hr("三方格式对比报告（PartialServiceSchema / SGD / langextract）")
        report = format_comparison_report(schema, ref_schema)

        _hr("本项目格式 vs SGD 格式")
        vs_sgd = report["our_vs_sgd"]
        print("\n  📗 相同点:")
        for item in vs_sgd.get("相同点", []):
            print(f"    ✓ {item}")
        print("\n  📙 差异点:")
        for diff in vs_sgd.get("差异点", []):
            print(f"    △ 字段: {diff.get('字段')}")
            print(f"      本项目: {diff.get('本项目格式')}")
            print(f"      SGD:   {diff.get('SGD 格式')}")
            print(f"      影响:  {diff.get('影响')}")
        print(f"\n  💡 兼容性: {vs_sgd.get('兼容性结论')}")

        _hr("本项目格式 vs langextract 格式")
        vs_lx = report["our_vs_langextract"]
        print("\n  📘 用途差异:")
        for k, v in vs_lx.get("用途差异", {}).items():
            print(f"    · {k}: {v}")
        print("\n  📘 字段对应关系（前 5 条）:")
        for mapping in vs_lx.get("字段对应关系", [])[:5]:
            print(f"    · {mapping['本项目字段']}  ↔  {mapping['langextract 字段']}")
        print("\n  📘 关键差异:")
        for diff in vs_lx.get("关键差异", []):
            print(f"    △ {diff[:100]}")
        print(f"\n  💡 互操作: {vs_lx.get('互操作方式', '')[:200]}")

        _hr("langextract ExampleData 预览（由归纳 Schema 生成）")
        preview = report["langextract_example_preview"]
        print(f"  text 长度: {preview['text_length']} 字符")
        print(f"  extractions 数量: {preview['extractions_count']}")
        print("  前 3 条 extraction:")
        for ex in preview["extractions_preview"]:
            attrs_str = ""
            if ex.get("attributes"):
                attrs_preview = {k: str(v)[:20] for k, v in list(ex["attributes"].items())[:2]}
                attrs_str = f"  attrs={json.dumps(attrs_preview, ensure_ascii=False)}"
            print(f"    [{ex.get('extraction_class'):10s}] {ex.get('extraction_text', '')[:30]}{attrs_str}")


# --------------------------------------------------------------------------- #
# 演示函数
# --------------------------------------------------------------------------- #


def demo_induce_mode(
    data_path: Path,
    service_name: str,
    batch_size: int,
    limit: int,
    output_path: Path,
    reference_schema_path: Path,
    do_compare: bool,
) -> PartialServiceSchema:
    """
    功能一：从原始对话中使用 LLM 归纳 Schema。

    归纳结果自动保存为 SGD JSON 数组格式文件。
    若传入参考 SGD Schema 且 do_compare=True，还会显示三方格式对比报告。

    返回归纳出的 PartialServiceSchema（供 full 模式复用）。
    """
    _hr("功能一：LLM Schema 归纳（induce_schema_with_llm）")

    dialogues = _load_dialogues(data_path, limit)
    llm = _init_llm()

    print(f"\n🔄 正在归纳 Schema（batch_size={batch_size}，共 {len(dialogues)} 条对话）…")
    print("   这可能需要 30~120 秒，请耐心等待。")

    schema = induce_schema_with_llm(
        dialogues,
        llm_client=llm,
        service_name=service_name,
        batch_size=batch_size,
    )

    _hr("归纳结果")
    _print_schema_summary(schema)

    _save_and_report(schema, output_path, reference_schema_path, do_compare)

    return schema


def demo_extract_mode(
    data_path: Path,
    schema_path: Path,
    limit: int,
) -> None:
    """
    功能二：使用预定义 Schema 对对话进行细粒度信息提取。
    """
    _hr("功能二：Schema 引导的细粒度信息提取（extract_dialogue_info）")

    if not schema_path.exists():
        print(f"⚠️  Schema 文件不存在: {schema_path}")
        sys.exit(1)
    schema = schema_from_sgd_file(schema_path)
    print(f"✅ 加载预定义 Schema: {schema_path.name}（{schema.service_name}）")
    print(f"   槽位: {len(schema.slots)} 个  意图: {len(schema.intents)} 个")

    dialogues = _load_dialogues(data_path, limit)
    llm = _init_llm()

    print(f"\n🔄 正在对 {len(dialogues)} 条对话进行信息提取…")

    for idx, dialogue in enumerate(dialogues, 1):
        _hr(f"对话 #{idx}（session_id: {str(dialogue.get('session_id', ''))[:20]}）")

        history = dialogue.get("对话历史", [])
        preview_turns = history[:6] if isinstance(history, list) else []
        print("  对话片段（前 6 轮）:")
        for turn in preview_turns:
            print(f"    {str(turn)[:60]}")
        if len(history) > 6:
            print(f"    … 还有 {len(history) - 6} 轮")

        print("\n  🔍 提取结果:")
        result = extract_dialogue_info(dialogue, schema, llm)

        if result.get("parse_error"):
            print(f"  ⚠️  解析失败: {result['parse_error'][:100]}")
        else:
            intents = result.get("active_intents", [])
            slots = result.get("slot_values", {})
            print(f"  active_intents ({len(intents)}): {intents}")
            print(f"  slot_values ({len(slots)} 个槽位):")
            for slot_name, slot_val in slots.items():
                print(f"    · {slot_name}: {slot_val}")

        if "人工校验" in dialogue:
            print(f"\n  参考标注（人工校验）: {dialogue['人工校验']}")


def demo_full_mode(
    data_path: Path,
    service_name: str,
    batch_size: int,
    induce_limit: int,
    extract_limit: int,
    output_path: Path,
    reference_schema_path: Path,
) -> None:
    """
    功能三：端到端演示 — 先归纳 Schema（保存文件），再提取信息，最后对比格式。
    """
    _hr("功能三：端到端（Schema 归纳 → 保存 → Schema 引导提取 → 格式对比）")

    all_dialogues = _load_dialogues(data_path, max(induce_limit, extract_limit))
    induce_dialogues = all_dialogues[:induce_limit]
    extract_dialogues = all_dialogues[:extract_limit]

    llm = _init_llm()

    # Step 1: 归纳 Schema
    _hr(f"Step 1: 从前 {induce_limit} 条对话归纳 Schema")
    schema = induce_schema_with_llm(
        induce_dialogues,
        llm_client=llm,
        service_name=service_name,
        batch_size=batch_size,
    )

    _hr("归纳出的 Schema")
    _print_schema_summary(schema)

    # Step 2: 保存并对比格式
    _hr("Step 2: 保存 Schema 并进行格式对比")
    _save_and_report(schema, output_path, reference_schema_path, do_compare=True)

    # Step 3: 基于归纳的 Schema 提取信息
    _hr(f"Step 3: 基于归纳 Schema 对前 {extract_limit} 条对话提取信息")

    for idx, dialogue in enumerate(extract_dialogues, 1):
        _hr(f"对话 #{idx}")
        result = extract_dialogue_info(dialogue, schema, llm)
        if result.get("parse_error"):
            print(f"  ⚠️  解析失败: {result['parse_error'][:100]}")
        else:
            print(f"  active_intents: {result.get('active_intents', [])}")
            print(f"  slot_values ({len(result.get('slot_values', {}))} 个):")
            for k, v in result.get("slot_values", {}).items():
                print(f"    · {k}: {v}")


def demo_compare_mode(
    schema_path: Path,
) -> None:
    """
    功能四：格式对比（离线，无需 LLM）。

    直接从现有 SGD schema.json 生成三方格式对比报告，
    对比 PartialServiceSchema / SGD / langextract 三种格式的字段结构与用途差异。
    """
    _hr("功能四：三方格式对比（PartialServiceSchema / SGD / langextract）")

    if not schema_path.exists():
        print(f"⚠️  Schema 文件不存在: {schema_path}")
        sys.exit(1)
    ref_schema = schema_from_sgd_file(schema_path)
    print(f"✅ 加载参考 Schema: {schema_path.name}（{ref_schema.service_name}）")
    print(f"   槽位: {len(ref_schema.slots)} 个  意图: {len(ref_schema.intents)} 个")

    report = format_comparison_report(ref_schema, ref_schema)

    _hr("A. 本项目 PartialServiceSchema 格式")
    fmt = report["our_schema_format"]
    print(f"  容器类型: {fmt['container']}")
    print(f"  序列化: {fmt['serialization']}")
    print(f"  文件格式: {fmt['file_format']}")
    print(f"\n  顶层字段: {json.dumps(fmt['top_level_fields'], ensure_ascii=False)}")
    print(f"  Slot 字段: {json.dumps(fmt['slot_fields'], ensure_ascii=False)}")
    print(f"  Intent 字段: {json.dumps(fmt['intent_fields'], ensure_ascii=False)}")

    _hr("B. SGD 数据集格式")
    sgd = report["sgd_format"]
    print(f"  来源: {sgd['source']}")
    print(f"  URL: {sgd['url']}")
    print(f"  容器: {sgd['container']}")
    print(f"\n  关键约束:")
    for c in sgd.get("key_constraints", []):
        print(f"    · {c}")

    _hr("C. langextract 格式")
    lx = report["langextract_format"]
    print(f"  来源: {lx['source']}")
    print(f"  URL: {lx['url']}")
    print(f"  用途: {lx['purpose']}")
    print(f"\n  ExampleData 字段: {json.dumps(lx['ExampleData_fields'], ensure_ascii=False)}")
    print(f"  Extraction 字段: {json.dumps(lx['Extraction_fields'], ensure_ascii=False)}")
    print(f"\n  关键约束:")
    for c in lx.get("key_constraints", []):
        print(f"    · {c}")

    _hr("格式对比：本项目 vs SGD")
    vs_sgd = report["our_vs_sgd"]
    print("\n  相同点:")
    for item in vs_sgd.get("相同点", []):
        print(f"    ✓ {item}")
    print("\n  差异点:")
    for diff in vs_sgd.get("差异点", []):
        print(f"    △ 字段: {diff.get('字段')}  影响: {diff.get('影响')}")
    print(f"\n  兼容性结论: {vs_sgd.get('兼容性结论')}")

    _hr("格式对比：本项目 vs langextract")
    vs_lx = report["our_vs_langextract"]
    print("\n  用途差异:")
    for k, v in vs_lx.get("用途差异", {}).items():
        print(f"    · {k}: {v}")
    print("\n  关键差异:")
    for diff in vs_lx.get("关键差异", []):
        print(f"    △ {diff[:120]}")
    print(f"\n  互操作方式: {vs_lx.get('互操作方式', '')[:250]}")


# --------------------------------------------------------------------------- #
# 命令行入口
# --------------------------------------------------------------------------- #


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="安逸花外呼 · Schema 归纳与引导提取演示（LLM 驱动）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
用法示例:
  python examples/anyihua_schema_induction_demo.py --mode induce --limit 10
  python examples/anyihua_schema_induction_demo.py --mode induce --limit 10 --compare
  python examples/anyihua_schema_induction_demo.py --mode extract --limit 3
  python examples/anyihua_schema_induction_demo.py --mode full --limit 5
  python examples/anyihua_schema_induction_demo.py --mode compare
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["induce", "extract", "full", "compare"],
        default="induce",
        help=(
            "演示模式（默认: induce）：\n"
            "  induce  — 从原始对话中使用 LLM 归纳 Schema，自动保存文件\n"
            "  extract — 使用预定义 Schema 对对话进行细粒度信息提取\n"
            "  full    — 端到端（归纳 + 保存 + 提取 + 格式对比）\n"
            "  compare — 三方格式对比（无需 LLM）"
        ),
    )
    parser.add_argument(
        "--data",
        default=str(_DEFAULT_DATA),
        help=f"原始对话数据文件路径（chat_test 格式，默认: {_DEFAULT_DATA.name}）",
    )
    parser.add_argument(
        "--schema",
        default=str(_DEFAULT_SCHEMA),
        help=f"预定义/参考 Schema 文件路径（默认: {_DEFAULT_SCHEMA.name}）",
    )
    parser.add_argument(
        "--output",
        default=str(_DEFAULT_OUTPUT),
        help=(
            f"induce/full 模式下归纳 Schema 的保存路径（SGD JSON 格式）"
            f"（默认: {_DEFAULT_OUTPUT.name}）"
        ),
    )
    parser.add_argument(
        "--service-name",
        default=_DEFAULT_SERVICE_NAME,
        help=f"服务名称（induce 模式用，默认: {_DEFAULT_SERVICE_NAME}）",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="induce 模式每批处理的对话数量（默认: 5）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="使用的对话数量上限（默认: 10）",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        default=False,
        help="induce 模式下同时显示三方格式对比报告（PartialServiceSchema / SGD / langextract）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_path = Path(args.data)
    schema_path = Path(args.schema)
    output_path = Path(args.output)

    print("=" * 72)
    print("  安逸花外呼 · Schema 归纳与引导提取演示（LLM 驱动）")
    print(f"  模式: {args.mode}  对话数: {args.limit}  batch_size: {args.batch_size}")
    print("=" * 72)

    if args.mode == "induce":
        demo_induce_mode(
            data_path=data_path,
            service_name=args.service_name,
            batch_size=args.batch_size,
            limit=args.limit,
            output_path=output_path,
            reference_schema_path=schema_path,
            do_compare=args.compare,
        )
    elif args.mode == "extract":
        demo_extract_mode(
            data_path=data_path,
            schema_path=schema_path,
            limit=args.limit,
        )
    elif args.mode == "full":
        demo_full_mode(
            data_path=data_path,
            service_name=args.service_name,
            batch_size=args.batch_size,
            induce_limit=args.limit,
            extract_limit=min(3, args.limit),
            output_path=output_path,
            reference_schema_path=schema_path,
        )
    elif args.mode == "compare":
        demo_compare_mode(schema_path=schema_path)


if __name__ == "__main__":
    main()

