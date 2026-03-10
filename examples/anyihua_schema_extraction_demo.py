"""
安逸花外呼 · 任务三：Schema 提取演示（Schema Extraction Demo）

演示如何从安逸花外呼对话数据中提取部分字段 SGD Schema，
以及如何将标注对话转换为 langextract ExampleData-兼容格式。

功能一（--mode schema）：
    从 SGD schema.json 加载 PartialServiceSchema 并序列化，
    展示"允许部分字段缺失"的输出格式（跳过值为 None 的字段）。

功能二（--mode extract）：
    将 resources/anyihua_sgd/dialogues_001.json 中的标注对话
    转换为 langextract ExampleData-兼容字典列表，打印前 N 条样本。

功能三（--mode partial）：
    从单条原始对话中自动归纳 PartialServiceSchema（无元信息，
    仅保留对话中出现过的槽位和意图名称）。

用法（无需 LLM，完全离线）:
    cd /path/to/ContextMind

    # 展示 PartialServiceSchema 序列化（允许部分字段缺失）
    python examples/anyihua_schema_extraction_demo.py --mode schema

    # 将标注对话转换为 langextract 样本
    python examples/anyihua_schema_extraction_demo.py --mode extract

    # 从原始对话归纳 PartialServiceSchema
    python examples/anyihua_schema_extraction_demo.py --mode partial

    # 指定自定义数据文件
    python examples/anyihua_schema_extraction_demo.py --mode extract \\
        --dialogues /path/to/dialogues.json \\
        --schema /path/to/schema.json \\
        --limit 5
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

from contextmind.scenarios.anyihua.schema_extraction import (
    PartialIntent,
    PartialServiceSchema,
    PartialSlot,
    dialogue_to_langextract_example,
    dialogues_to_langextract_examples,
    extract_partial_schema_from_dialogue,
    schema_from_sgd_file,
)

_DEFAULT_DIALOGUES = _PROJECT_ROOT / "resources" / "anyihua_sgd" / "dialogues_001.json"
_DEFAULT_SCHEMA = _PROJECT_ROOT / "resources" / "anyihua_sgd" / "schema.json"


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


# --------------------------------------------------------------------------- #
# 演示函数
# --------------------------------------------------------------------------- #


def demo_schema_mode(schema_path: Path) -> None:
    """
    功能一：展示 PartialServiceSchema 序列化（允许部分字段缺失）。

    首先演示手动构建含缺失字段的 Schema，再从文件加载完整 Schema，
    对比两者的序列化输出差异。
    """
    _hr("功能一：PartialServiceSchema — 允许部分字段缺失")

    # 1. 手动构建含缺失字段的最小 Schema
    minimal_schema = PartialServiceSchema(
        service_name="AnYiHua_Minimal",
        # description 缺失（None）
        slots=[
            PartialSlot(
                name="customer_name",
                description="客户姓名",
                # is_categorical 和 possible_values 缺失
            ),
            PartialSlot(
                name="available_credit",
                # description / is_categorical / possible_values 均缺失
            ),
            PartialSlot(
                name="identity_confirmed",
                is_categorical=True,
                possible_values=["true", "false"],
                # description 缺失
            ),
        ],
        intents=[
            PartialIntent(
                name="verify_identity",
                description="开场身份核实",
                # 其余字段缺失
            ),
            PartialIntent(
                name="say_goodbye",
                # 所有可选字段均缺失
            ),
        ],
    )

    print("\n📋 最小 Schema（手动构建，含缺失字段）→ to_sgd_dict()（跳过 None 字段）:")
    print(json.dumps(minimal_schema.to_sgd_dict(), ensure_ascii=False, indent=2))

    # 2. langextract 兼容格式
    print("\n🔗 to_langextract_schema_dict()（供 langextract ExampleData 使用）:")
    lx_dict = minimal_schema.to_langextract_schema_dict()
    print(f"  text 长度: {len(lx_dict['text'])} 字符")
    print(f"  extractions 数量: {len(lx_dict['extractions'])}")
    for ex in lx_dict["extractions"]:
        print(
            f"    [{ex['extraction_class']}] {ex['extraction_text']}"
            + (f"  attrs={ex['attributes']}" if ex.get("attributes") else "")
        )

    # 3. 从文件加载完整 Schema
    if schema_path.exists():
        _hr("从 SGD schema.json 加载完整 PartialServiceSchema")
        full_schema = schema_from_sgd_file(schema_path)
        print(f"  服务名: {full_schema.service_name}")
        print(f"  描述: {full_schema.description}")
        print(f"  槽位数: {len(full_schema.slots)}")
        print(f"  意图数: {len(full_schema.intents)}")

        # 展示部分槽位（有 possible_values 的分类槽）
        cat_slots = [s for s in full_schema.slots if s.is_categorical]
        if cat_slots:
            print(f"\n  分类槽位（共 {len(cat_slots)} 个）:")
            for s in cat_slots:
                print(f"    · {s.name}: {s.possible_values}")

        print(f"\n  完整序列化（前 400 字符）:")
        full_json = full_schema.to_json()
        print("  " + full_json[:400].replace("\n", "\n  "))
    else:
        print(f"\n⚠️  schema.json 不存在，跳过文件加载演示: {schema_path}")


def demo_extract_mode(
    dialogues_path: Path,
    schema_path: Path,
    limit: int = 3,
) -> None:
    """
    功能二：将标注 SGD 对话转换为 langextract ExampleData-兼容字典。
    """
    _hr("功能二：标注对话 → langextract ExampleData-兼容字典")

    if not dialogues_path.exists():
        print(f"⚠️  对话文件不存在: {dialogues_path}")
        return

    dialogues: List[Dict[str, Any]] = json.loads(
        dialogues_path.read_text(encoding="utf-8")
    )
    print(f"✅ 加载对话数据: {dialogues_path}（共 {len(dialogues)} 条）")

    schema: PartialServiceSchema | None = None
    if schema_path.exists():
        schema = schema_from_sgd_file(schema_path)
        print(f"✅ 加载 Schema: {schema_path}（{schema.service_name}）")
    else:
        print(f"⚠️  schema.json 不存在，不附加元信息: {schema_path}")

    examples = dialogues_to_langextract_examples(dialogues, schema)
    print(f"\n📦 转换结果: {len(examples)} 条 ExampleData 样本")

    for i, example in enumerate(examples[:limit]):
        _hr(f"样本 #{i + 1}")
        # 截断文本显示
        text_preview = example["text"][:200].replace("\n", " | ")
        print(f"  text 预览: {text_preview}…")
        print(f"  extractions 数量: {len(example['extractions'])}")
        for ex in example["extractions"][:6]:
            attrs_str = ""
            if ex.get("attributes"):
                attrs_str = (
                    "  "
                    + ", ".join(
                        f"{k}={v[:20]}" for k, v in ex["attributes"].items()
                    )
                )
            print(
                f"    [{ex['extraction_class']:14s}] {ex['extraction_text'][:30]}"
                + attrs_str
            )
        if len(example["extractions"]) > 6:
            print(f"    … 还有 {len(example['extractions']) - 6} 条 extraction")

    print(
        f"\n💡 使用提示（安装 langextract 后）:\n"
        f"   import langextract as lx\n"
        f"   lx_examples = [\n"
        f"       lx.data.ExampleData(\n"
        f"           text=ex['text'],\n"
        f"           extractions=[\n"
        f"               lx.data.Extraction(\n"
        f"                   extraction_class=e['extraction_class'],\n"
        f"                   extraction_text=e['extraction_text'],\n"
        f"                   attributes=e.get('attributes'),\n"
        f"               )\n"
        f"               for e in ex['extractions']\n"
        f"           ],\n"
        f"       )\n"
        f"       for ex in examples\n"
        f"   ]\n"
        f"   result = lx.extract(\n"
        f"       text_or_documents='<新对话文本>',\n"
        f"       prompt_description='从安逸花外呼对话中提取槽位值和意图',\n"
        f"       examples=lx_examples,\n"
        f"       model_id='gemini-2.5-flash',\n"
        f"   )"
    )


def demo_partial_mode(dialogues_path: Path) -> None:
    """
    功能三：从单条原始对话自动归纳 PartialServiceSchema（部分字段缺失）。
    """
    _hr("功能三：从对话自动归纳 PartialServiceSchema（无元信息）")

    if not dialogues_path.exists():
        print(f"⚠️  对话文件不存在: {dialogues_path}")
        return

    dialogues: List[Dict[str, Any]] = json.loads(
        dialogues_path.read_text(encoding="utf-8")
    )
    if not dialogues:
        print("⚠️  对话数据为空")
        return

    # 取前 3 条对话合并归纳
    for idx in range(min(3, len(dialogues))):
        dialogue = dialogues[idx]
        partial = extract_partial_schema_from_dialogue(dialogue)
        _hr(f"对话 #{idx + 1}：{dialogue.get('dialogue_id', '')[:16]}…")
        print(f"  归纳槽位: {[s.name for s in partial.slots]}")
        print(f"  归纳意图: {[i.name for i in partial.intents]}")
        print(f"  to_sgd_dict（跳过 None 字段）:")
        print(
            "  " + partial.to_json().replace("\n", "\n  ")[:300]
        )


# --------------------------------------------------------------------------- #
# 命令行入口
# --------------------------------------------------------------------------- #


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="安逸花外呼 · Schema 提取演示（任务三）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
用法示例:
  python examples/anyihua_schema_extraction_demo.py --mode schema
  python examples/anyihua_schema_extraction_demo.py --mode extract --limit 5
  python examples/anyihua_schema_extraction_demo.py --mode partial
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["schema", "extract", "partial"],
        default="extract",
        help=(
            "演示模式（默认: extract）：\n"
            "  schema  — 展示 PartialServiceSchema 序列化（允许部分字段缺失）\n"
            "  extract — 将标注对话转换为 langextract ExampleData-兼容字典\n"
            "  partial — 从原始对话自动归纳 PartialServiceSchema"
        ),
    )
    parser.add_argument(
        "--dialogues",
        default=str(_DEFAULT_DIALOGUES),
        help=f"SGD 对话文件路径（默认: {_DEFAULT_DIALOGUES}）",
    )
    parser.add_argument(
        "--schema",
        default=str(_DEFAULT_SCHEMA),
        help=f"SGD schema.json 文件路径（默认: {_DEFAULT_SCHEMA}）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="extract 模式下最多显示的样本数（默认: 3）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dialogues_path = Path(args.dialogues)
    schema_path = Path(args.schema)

    if args.mode == "schema":
        demo_schema_mode(schema_path)
    elif args.mode == "extract":
        demo_extract_mode(dialogues_path, schema_path, limit=args.limit)
    elif args.mode == "partial":
        demo_partial_mode(dialogues_path)


if __name__ == "__main__":
    main()
