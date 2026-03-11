"""
安逸花外呼知识提取演示（单轮对话 + langextract 溯源版）

演示如何使用 AnyihuaKnowledgeExtractor 从安逸花外呼多轮对话中提取带轮次归属
和字符级溯源的结构化知识，并可选择将结果转换为 SGD 数据集格式。

核心特点：
  · 逐轮解析对话，每轮作为 langextract 的独立文本输入（解决多轮对话对齐问题）
  · LLM 输出包含 turn_idx（来自哪一轮）和 provenance_text（该轮话语的 verbatim 片段）
  · WordAligner 仅对对应轮次的短文本做字符对齐，精度高
  · 提取结果保存为 JSON 文件，可同步输出 SGD 格式
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

    # 使用开放 Schema（允许 LLM 自由命名槽位/意图，适合探索新业务）
    python examples/anyihua_knowledge_extraction_demo.py \\
        --scene-name 银行贷款外呼 \\
        --slot-open-ended \\
        --intent-open-ended

    # 不输出 SGD 格式（仅保存原始提取结果）
    python examples/anyihua_knowledge_extraction_demo.py --no-sgd

参数说明（见 --help）：
    --data              原始对话 JSON 文件路径
    --output            提取结果 JSON 保存路径
    --sgd-dir           SGD 格式输出目录（默认：data/anyihua_sgd/）
    --no-sgd            禁用 SGD 格式输出
    --num               处理对话数量（默认：2）
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

# 确保项目根目录在 sys.path 中
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from contextmind.scenarios.anyihua.knowledge_extraction import (
    AnyihuaKnowledgeExtractor,
    DEFAULT_SCHEMA,
    ExtractionSchema,
    save_as_sgd,
    save_results,
)

# 默认路径
_DEFAULT_DATA_PATH = _ROOT / "resources" / "data" / "chat_test_100.json"
_DEFAULT_SAVE_PATH = _ROOT / "data" / "anyihua_knowledge_extraction_results.json"
_DEFAULT_SGD_DIR = _ROOT / "data" / "anyihua_sgd"


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


def _build_schema(args: argparse.Namespace) -> ExtractionSchema:
    """
    根据命令行参数构造 ExtractionSchema。

    · 若 --scene-name 与默认值相同且无开放模式标志，使用 DEFAULT_SCHEMA（全套预定义）。
    · 若指定了 --scene-name 不同的名称或开放模式，克隆 DEFAULT_SCHEMA 并应用修改。
    """
    if (
        args.scene_name == DEFAULT_SCHEMA.scene_name
        and not args.slot_open_ended
        and not args.intent_open_ended
    ):
        return DEFAULT_SCHEMA

    # 克隆默认 schema，仅修改指定字段
    schema = dataclasses.replace(
        DEFAULT_SCHEMA,
        scene_name=args.scene_name,
        slot_open_ended=args.slot_open_ended,
        intent_open_ended=args.intent_open_ended,
    )
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

  # 批量处理前 10 条
  python examples/anyihua_knowledge_extraction_demo.py --num 10

  # 使用开放 Schema（LLM 可自由命名槽位和意图）
  python examples/anyihua_knowledge_extraction_demo.py --slot-open-ended --intent-open-ended

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
        help=f"原始对话 JSON 文件路径（默认：{_DEFAULT_DATA_PATH.relative_to(_ROOT)}）",
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
        help="处理对话数量（默认：2；-1 表示全部）",
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

    # ── 加载数据 ──
    data_path: Path = args.data
    if not data_path.exists():
        print(f"[错误] 数据文件不存在: {data_path}")
        sys.exit(1)

    dialogues = json.loads(data_path.read_text(encoding="utf-8"))
    num = len(dialogues) if args.num == -1 else min(args.num, len(dialogues))
    selected = dialogues[:num]
    print(f"已加载 {len(dialogues)} 条对话，本次处理前 {num} 条")
    print(f"提取结果将保存至: {args.output}")
    if not args.no_sgd:
        print(f"SGD 格式将保存至: {args.sgd_dir}/")

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

    # ── 单条提取演示（仅在 num >= 1 时执行）──
    if num >= 1:
        print("【演示一：单条提取（含轮次归属与字符级溯源）】")
        result = extractor.extract(selected[0])
        _print_result(
            result,
            show_turns=True,
            show_stats_desc=not args.no_stats_desc,
        )

    # ── 批量提取（结果自动保存为 JSON 文件）──
    if num > 1:
        print(f"\n\n【演示二：批量提取（共 {num} 条）— 结果自动保存为 JSON 文件】")
        results = extractor.extract_batch(
            selected,
            save_path=args.output,
        )
        for r in results[1:]:  # 第 0 条已在演示一中打印
            _print_result(
                r,
                show_turns=args.show_turns,
                show_stats_desc=not args.no_stats_desc,
            )
        print(f"\n✅ 提取结果已保存至: {args.output}")
    else:
        # 仅 1 条时也保存
        results = [result]
        save_results(results, args.output)
        print(f"\n✅ 提取结果已保存至: {args.output}")

    # ── SGD 格式转换 ──
    if not args.no_sgd:
        print(f"\n\n【SGD 格式转换：将提取结果转换为 SGD 数据集格式】")
        summary = save_as_sgd(
            results=results,
            raw_dialogues=selected[:len(results)],
            output_dir=args.sgd_dir,
        )
        print(f"  对话数:   {summary['dialogues']}")
        print(f"  总轮次:   {summary['turns']}")
        print(f"  输出目录: {summary['output_dir']}")
        print(f"✅ SGD 格式已保存至: {args.sgd_dir}/")


if __name__ == "__main__":
    main()
