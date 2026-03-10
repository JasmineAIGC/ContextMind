"""
安逸花外呼 · Schema 归纳与引导提取演示（LLM 驱动）

本演示展示两个 LLM 驱动的核心能力（对应 problem_statement 中的两个关注点）：

功能一（--mode induce）：Schema 归纳
    从原始（未标注）安逸花外呼对话中，使用 LLM 自动归纳出
    完善、丰富、准确的 Schema 数据（包含槽位描述、分类标志、
    可选值、意图描述、所需/可选槽位等元信息）。

功能二（--mode extract）：Schema 引导的细粒度信息提取
    给定一个预定义 Schema（如 resources/anyihua_sgd/schema.json），
    对新的外呼对话使用 LLM 提取精准、细粒度的结构化 JSON。

功能三（--mode full）：端到端流程
    先归纳 Schema，再用归纳出的 Schema 提取信息（一体化演示）。

用法（需要有效的 LLM API 配置）:
    cd /path/to/ContextMind

    # 在 .env 中配置 LLM_API_KEY / LLM_BASE_URL（或其他等效变量）

    # 功能一：从前 N 条对话归纳 Schema
    python examples/anyihua_schema_induction_demo.py --mode induce --limit 10

    # 功能二：用预定义 Schema 提取对话信息
    python examples/anyihua_schema_induction_demo.py --mode extract --limit 3

    # 功能三：端到端（归纳 + 提取）
    python examples/anyihua_schema_induction_demo.py --mode full --limit 5

    # 自定义数据文件
    python examples/anyihua_schema_induction_demo.py --mode induce \\
        --data /path/to/chat_test.json \\
        --schema /path/to/schema.json \\
        --batch-size 5 --limit 15
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from contextmind.infra.llm_client import LLMConfig, SimpleLLMClient
from contextmind.scenarios.anyihua.schema_extraction import (
    PartialServiceSchema,
    extract_dialogue_info,
    induce_schema_with_llm,
    schema_from_sgd_file,
)

_DEFAULT_DATA = _PROJECT_ROOT / "resources" / "data" / "chat_test_100.json"
_DEFAULT_SCHEMA = _PROJECT_ROOT / "resources" / "anyihua_sgd" / "schema.json"
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


# --------------------------------------------------------------------------- #
# 演示函数
# --------------------------------------------------------------------------- #


def demo_induce_mode(
    data_path: Path,
    service_name: str,
    batch_size: int,
    limit: int,
    save_path: Path | None = None,
) -> PartialServiceSchema:
    """
    功能一：从原始对话中使用 LLM 归纳 Schema。

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

    _hr("完整 Schema JSON")
    schema_json = schema.to_json()
    print(schema_json)

    if save_path:
        save_path.write_text(schema_json, encoding="utf-8")
        print(f"\n💾 Schema 已保存到: {save_path}")

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

    # 加载 Schema
    if not schema_path.exists():
        print(f"⚠️  Schema 文件不存在: {schema_path}")
        sys.exit(1)
    schema = schema_from_sgd_file(schema_path)
    print(f"✅ 加载预定义 Schema: {schema_path.name}（{schema.service_name}）")
    print(f"   槽位: {len(schema.slots)} 个  意图: {len(schema.intents)} 个")

    # 加载对话
    dialogues = _load_dialogues(data_path, limit)
    llm = _init_llm()

    print(f"\n🔄 正在对 {len(dialogues)} 条对话进行信息提取…")

    for idx, dialogue in enumerate(dialogues, 1):
        _hr(f"对话 #{idx}（session_id: {str(dialogue.get('session_id', ''))[:20]}）")

        # 显示对话摘要（前 3 轮）
        history = dialogue.get("对话历史", [])
        preview_turns = history[:6] if isinstance(history, list) else []
        print("  对话片段（前 6 轮）:")
        for turn in preview_turns:
            print(f"    {str(turn)[:60]}")
        if len(history) > 6:
            print(f"    … 还有 {len(history) - 6} 轮")

        # 提取信息
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

        # 若有人工标注，显示对比
        if "人工校验" in dialogue:
            print(f"\n  参考标注（人工校验）: {dialogue['人工校验']}")


def demo_full_mode(
    data_path: Path,
    service_name: str,
    batch_size: int,
    induce_limit: int,
    extract_limit: int,
) -> None:
    """
    功能三：端到端演示 — 先归纳 Schema，再用归纳出的 Schema 提取信息。
    """
    _hr("功能三：端到端（Schema 归纳 → Schema 引导提取）")

    # Step 1: 归纳 Schema
    print("\n📌 Step 1: 从前 {} 条对话归纳 Schema…".format(induce_limit))
    all_dialogues = _load_dialogues(data_path, max(induce_limit, extract_limit))
    induce_dialogues = all_dialogues[:induce_limit]
    extract_dialogues = all_dialogues[:extract_limit]

    llm = _init_llm()
    schema = induce_schema_with_llm(
        induce_dialogues,
        llm_client=llm,
        service_name=service_name,
        batch_size=batch_size,
    )

    _hr("归纳出的 Schema")
    _print_schema_summary(schema)

    # Step 2: 基于归纳的 Schema 提取信息
    _hr(f"📌 Step 2: 基于归纳 Schema 对前 {extract_limit} 条对话提取信息")

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
  python examples/anyihua_schema_induction_demo.py --mode extract --limit 3
  python examples/anyihua_schema_induction_demo.py --mode full --limit 5
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["induce", "extract", "full"],
        default="induce",
        help=(
            "演示模式（默认: induce）：\n"
            "  induce  — 从原始对话中使用 LLM 归纳 Schema\n"
            "  extract — 使用预定义 Schema 对对话进行细粒度信息提取\n"
            "  full    — 端到端（先归纳 Schema，再提取信息）"
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
        help=f"预定义 Schema 文件路径（extract 模式用，默认: {_DEFAULT_SCHEMA.name}）",
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
        "--save",
        default=None,
        help="induce 模式下将归纳出的 Schema JSON 保存到此路径",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_path = Path(args.data)
    schema_path = Path(args.schema)
    save_path = Path(args.save) if args.save else None

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
            save_path=save_path,
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
        )


if __name__ == "__main__":
    main()
