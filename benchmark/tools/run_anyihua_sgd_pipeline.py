#!/usr/bin/env python3
"""
安逸花外呼数据 → SGD 格式 3 步管道 CLI

实现 docs/analysis/dialogue-to-knowledge-pipeline.md 描述的完整转换流程：

  Step 1: LLM Schema 发现（从抽样对话归纳意图与槽位）
  Step 2: Schema 合并精化（预定义 + 发现合并）
  Step 3: LLM 全量 SGD 转换（含 langextract 对齐信息）

所有 LLM 调用均通过 .env 文件定义的 SimpleLLMClient，
不使用 langextract 库的内置 Gemini 模型。

----------------------------------------------------------------------
使用方法
----------------------------------------------------------------------

  # 完整 3 步管道（转换全部对话）
  python benchmark/tools/run_anyihua_sgd_pipeline.py

  # 仅转换前 10 条（调试用）
  python benchmark/tools/run_anyihua_sgd_pipeline.py --limit 10

  # 跳过 Step 1（使用预定义 Schema，不做 LLM 归纳）
  python benchmark/tools/run_anyihua_sgd_pipeline.py --skip-step1

  # 跳过 Step 1 和 Step 2（直接用预定义 Schema 转换）
  python benchmark/tools/run_anyihua_sgd_pipeline.py --skip-step1 --skip-step2

  # 指定输入/输出路径
  python benchmark/tools/run_anyihua_sgd_pipeline.py \\
      --input resources/data/chat_test_100.json \\
      --schema resources/anyihua_sgd/schema.json \\
      --output data/anyihua_sgd_pipeline

  # 保存中间结果（discovered_schema、merged_schema）
  python benchmark/tools/run_anyihua_sgd_pipeline.py \\
      --save-discovered data/step1_discovered_schema.json \\
      --save-merged data/step2_merged_schema.json

  # Step 1 抽样数量控制
  python benchmark/tools/run_anyihua_sgd_pipeline.py --sample-n 30

----------------------------------------------------------------------
输出目录结构
----------------------------------------------------------------------

  <output>/
      schema.json              # merged_schema（SGD 格式）
      dialogues_001.json       # 转换后的对话数据（SGD 格式）
      extraction_summary.json  # 提取统计（对齐率、槽位填充率等）

----------------------------------------------------------------------
安逸花对话的 langextract 特殊处理
----------------------------------------------------------------------

对话文本以"坐席："/"用户："为前缀，langextract 对齐时：
  - intent：extraction_text = 用户发言原话（非意图编码）
  - slot_value：extraction_text = 槽位的原始值文本（如"高先生"、"六七八"）
  - system_intent：extraction_text = 坐席发言原话（非 API 方法名）

意图编码、方法名等不出现在中文对话中的字符串，统一放入 attributes 字典，
而不作为 extraction_text，确保 langextract WordAligner 能够成功对齐。
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# 将项目根目录加入 Python 路径
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 默认路径（相对于项目根目录）
_DEFAULT_INPUT = str(_PROJECT_ROOT / "resources" / "data" / "chat_test_100.json")
_DEFAULT_SCHEMA = str(_PROJECT_ROOT / "resources" / "anyihua_sgd" / "schema.json")
_DEFAULT_OUTPUT = str(_PROJECT_ROOT / "data" / "anyihua_sgd_pipeline")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="安逸花外呼数据 → SGD 格式 3 步管道（基于 .env LLM）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python benchmark/tools/run_anyihua_sgd_pipeline.py\n"
            "  python benchmark/tools/run_anyihua_sgd_pipeline.py --limit 10\n"
            "  python benchmark/tools/run_anyihua_sgd_pipeline.py --skip-step1\n"
            "  python benchmark/tools/run_anyihua_sgd_pipeline.py --save-alignment-data\n"
        ),
    )
    parser.add_argument(
        "--input",
        default=_DEFAULT_INPUT,
        help=f"原始对话文件路径（chat_test 格式，默认: {_DEFAULT_INPUT}）",
    )
    parser.add_argument(
        "--schema",
        default=_DEFAULT_SCHEMA,
        help=f"预定义 Schema 文件路径（默认: {_DEFAULT_SCHEMA}）",
    )
    parser.add_argument(
        "--output",
        default=_DEFAULT_OUTPUT,
        help=f"SGD 输出目录路径（默认: {_DEFAULT_OUTPUT}）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="仅转换前 N 条对话（默认: 全部）",
    )
    parser.add_argument(
        "--sample-n",
        type=int,
        default=50,
        help="Step 1 LLM Schema 发现的抽样数量（默认: 50）",
    )
    parser.add_argument(
        "--skip-step1",
        action="store_true",
        help="跳过 Step 1（Schema 发现），直接使用预定义 Schema",
    )
    parser.add_argument(
        "--skip-step2",
        action="store_true",
        help="跳过 Step 2（Schema 合并），直接使用 Step 1 结果",
    )
    parser.add_argument(
        "--save-discovered",
        default=None,
        help="Step 1 发现的 Schema 保存路径（可选）",
    )
    parser.add_argument(
        "--save-merged",
        default=None,
        help="Step 2 合并后的 Schema 保存路径（可选）",
    )
    parser.add_argument(
        "--save-alignment-data",
        action="store_true",
        help=(
            "额外保存 alignment_data_*.json（含 langextract 对齐数据和 metadata，"
            "供质量审查和调试使用）"
        ),
    )
    parser.add_argument(
        "--dialogues-per-file",
        type=int,
        default=1000,
        help="每个 dialogues_*.json 最多包含的对话数（默认: 1000）",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别（默认: INFO）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="[%(asctime)s] %(levelname)s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    print(f"\n{'='*64}")
    print("安逸花外呼数据 → SGD 格式 3 步管道")
    print(f"{'='*64}")
    print(f"输入文件     : {args.input}")
    print(f"预定义 Schema: {args.schema}")
    print(f"输出目录     : {args.output}")
    print(f"对话限制     : {'全部' if not args.limit else f'前 {args.limit} 条'}")
    print(f"Step 1 抽样  : {args.sample_n} 条")
    print(f"跳过 Step 1  : {'✅' if args.skip_step1 else '❌'}")
    print(f"跳过 Step 2  : {'✅' if args.skip_step2 else '❌'}")
    print(f"{'='*64}\n")

    # ------------------------------------------------------------------
    # 初始化 LLM 客户端（从 .env 配置加载）
    # ------------------------------------------------------------------
    try:
        from contextmind.infra.llm_client import SimpleLLMClient

        llm_client = SimpleLLMClient()
        print(f"✅ LLM 客户端初始化成功（model: {llm_client.config.model}）\n")
    except Exception as exc:
        print(f"❌ LLM 客户端初始化失败: {exc}")
        print("请检查 .env 文件中的 QWEN3_API_KEY 等配置项。")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 运行管道
    # ------------------------------------------------------------------
    from contextmind.scenarios.anyihua.schema_extraction.pipeline import run_pipeline

    try:
        summary = run_pipeline(
            input_path=Path(args.input),
            predefined_schema_path=Path(args.schema),
            output_dir=Path(args.output),
            llm_client=llm_client,
            sample_n=args.sample_n,
            limit=args.limit,
            skip_step1=args.skip_step1,
            skip_step2=args.skip_step2,
            discovered_schema_save_path=(
                Path(args.save_discovered) if args.save_discovered else None
            ),
            merged_schema_save_path=(
                Path(args.save_merged) if args.save_merged else None
            ),
            dialogues_per_file=args.dialogues_per_file,
            save_alignment_data=args.save_alignment_data,
        )
    except Exception as exc:
        print(f"\n❌ 管道运行失败: {exc}")
        logging.getLogger(__name__).error("管道异常", exc_info=True)
        sys.exit(1)

    # ------------------------------------------------------------------
    # 打印汇总
    # ------------------------------------------------------------------
    schema_stats = summary.get("schema_stats", {})
    lx_stats = summary.get("langextract_stats", {})

    print(f"\n{'='*64}")
    print("管道完成汇总")
    print(f"{'='*64}")
    print(f"  对话总数     : {summary['dialogues']}")
    print(f"  总轮次数     : {summary['turns']}")
    print(f"  输出文件数   : {summary['dialogue_files']}")
    print(f"  Schema       : {schema_stats.get('intents', 0)} 意图 / {schema_stats.get('slots', 0)} 槽位")
    print(f"  langextract  :")
    print(f"    总提取数   : {lx_stats.get('total_extractions', 0)}")
    print(f"    已对齐数   : {lx_stats.get('total_aligned', 0)}")
    print(f"    对齐率     : {lx_stats.get('alignment_rate', 0.0):.1%}")
    print(f"\n  输出目录     : {summary['output_dir']}")
    print(f"    ├── schema.json")
    for i in range(1, summary["dialogue_files"] + 1):
        print(f"    ├── dialogues_{i:03d}.json")
    print(f"    └── extraction_summary.json")
    print(f"\n📄 汇总报告: {summary['output_dir']}/extraction_summary.json")
    print(f"{'='*64}\n")


if __name__ == "__main__":
    main()
