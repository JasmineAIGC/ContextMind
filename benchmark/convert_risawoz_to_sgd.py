#!/usr/bin/env python3
"""
RiSAWOZ → SGD 格式转换脚本

将 RiSAWOZ 数据集（中文多领域任务型对话）转换为
Google SGD（Schema-Guided Dialogue）格式，
以便使用 pyTOD 算法进行训练和测试。

----------------------------------------------------------------------
使用哪个 RiSAWOZ ZIP 包？
----------------------------------------------------------------------

RiSAWOZ 数据集包含多个 ZIP 包，对应不同的任务。
转换为 SGD 格式时，只有以下两个包是有效的数据源：

  ✅ source-data.zip（推荐）
     - 完整的原始对话标注，包含 dialogue_act、belief_state 等所有字段
     - 每轮用独立的 role="usr"/"sys" dict 表示
     - 信息最丰富，能生成最完整的 SGD schema 和 actions
     - 使用 --source-format source-data

  ✅ task2-data-DST.zip（也支持）
     - 专为 DST 任务提取的数据，每轮含 user_utterance + system_utterance
     - 包含 belief_state 和 user_acts，SGD 转换完整
     - 使用 --source-format task2-dst

  ❌ task1-data-NLU.zip（不支持）
     - IOB 格式文本文件（seq.in / seq.out / label），无对话结构
     - 单句标注，不是完整对话，无法转换为 SGD 格式

  ⚠️  task3 / task4 / task5 ZIP（部分支持）
     - 格式变体，base 对话结构与 task2-dst 相似，可尝试自动模式
     - 但可能缺少 belief_state 或 user_acts 字段，转换质量较低
     - 如需使用，建议先检查数据格式

----------------------------------------------------------------------
使用方法
----------------------------------------------------------------------

    # 使用 source-data.zip 中的完整数据（推荐）
    python benchmark/convert_risawoz_to_sgd.py \\
        --data-root ./data/RiSAWOZ \\
        --source-format source-data

    # 使用 task2-data-DST.zip 中的 DST 数据
    python benchmark/convert_risawoz_to_sgd.py \\
        --data-root ./data/RiSAWOZ_DST \\
        --source-format task2-dst

    # 只转换验证集
    python benchmark/convert_risawoz_to_sgd.py --splits val

    # 自定义文件名映射（非标准文件名时）
    python benchmark/convert_risawoz_to_sgd.py \\
        --file-mapping train=train_data.json val=val_data.json test=test_data.json

输出目录结构（与 SGD 相同）:
    <output-dir>/
        train/
            schema.json           # 所有服务的 Schema 定义
            dialogues_001.json    # 对话文件（每个最多 1000 条）
            ...
        val/
            schema.json
            dialogues_001.json
            ...
        test/
            schema.json
            dialogues_001.json
            ...
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# 将项目根目录加入 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.datasets.risawoz.sgd_converter import RiSAWOZToSGDConverter, SOURCE_FORMATS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将 RiSAWOZ 数据集转换为 SGD 格式",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--data-root",
        default="./data/RiSAWOZ",
        help="RiSAWOZ 数据集根目录（默认: ./data/RiSAWOZ）",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "输出目录（默认: <data-root>/../RiSAWOZ_SGD）。"
            "每个 split 会在此目录下创建子目录。"
        ),
    )
    parser.add_argument(
        "--splits",
        nargs="+",
        default=["train", "val", "test"],
        choices=["train", "val", "test"],
        help="要转换的数据集划分（默认: train val test）",
    )
    parser.add_argument(
        "--file-mapping",
        nargs="+",
        default=None,
        metavar="SPLIT=FILENAME",
        help=(
            "自定义文件名映射，格式为 split=filename，例如 "
            "train=train_data.json val=val_data.json"
        ),
    )
    parser.add_argument(
        "--source-format",
        default="auto",
        choices=list(SOURCE_FORMATS),
        help=(
            "源数据格式（默认: auto 自动检测）。"
            "source-data: 对应 source-data.zip（推荐，最完整）；"
            "task2-dst: 对应 task2-data-DST.zip。"
        ),
    )
    parser.add_argument(
        "--dialogues-per-file",
        type=int,
        default=1000,
        help="每个对话文件最多包含的对话数（默认: 1000）",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别（默认: INFO）",
    )
    return parser.parse_args()


def _parse_file_mapping(raw: list) -> dict:
    """Parse ['train=train.json', 'val=val.json'] into {'train': 'train.json', ...}."""
    mapping = {}
    for item in raw:
        if "=" not in item:
            logging.warning(f"忽略无效的 file-mapping 条目: {item!r}（应为 split=filename）")
            continue
        split, filename = item.split("=", 1)
        mapping[split.strip()] = filename.strip()
    return mapping


def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="[%(asctime)s] %(levelname)s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger(__name__)

    # Resolve output root
    data_root = Path(args.data_root)
    if args.output_dir:
        output_root = Path(args.output_dir)
    else:
        output_root = data_root.parent / f"{data_root.name}_SGD"

    # Parse file mapping
    file_mapping = None
    if args.file_mapping:
        file_mapping = _parse_file_mapping(args.file_mapping)

    print(f"\n{'='*60}")
    print("RiSAWOZ → SGD 格式转换器")
    print(f"{'='*60}")
    print(f"数据集根目录 : {data_root}")
    print(f"输出根目录   : {output_root}")
    print(f"要转换的划分 : {', '.join(args.splits)}")
    print(f"源数据格式   : {args.source_format}")
    if file_mapping:
        print(f"文件名映射   : {file_mapping}")
    print(f"{'='*60}\n")

    converter = RiSAWOZToSGDConverter(
        data_root=str(data_root),
        file_mapping=file_mapping,
        source_format=args.source_format,
    )

    all_summaries = {}
    errors = []

    for split in args.splits:
        split_output = str(output_root / split)
        print(f"▶ 正在转换 {split} 集 → {split_output}")
        try:
            summary = converter.convert(
                split=split,
                output_dir=split_output,
                dialogues_per_file=args.dialogues_per_file,
            )
            all_summaries[split] = summary
            print(
                f"  ✅ 完成: {summary['dialogues']} 对话, "
                f"{summary['turns']} 轮次, "
                f"{summary['services']} 服务, "
                f"{summary['dialogue_files']} 个文件"
            )
        except FileNotFoundError as exc:
            msg = f"  ❌ 数据文件不存在: {exc}"
            print(msg)
            logger.error(msg)
            errors.append((split, str(exc)))
        except Exception as exc:
            msg = f"  ❌ 转换失败: {exc}"
            print(msg)
            logger.exception(f"转换 {split} 失败")
            errors.append((split, str(exc)))

    # Final summary
    print(f"\n{'='*60}")
    print("转换完成汇总")
    print(f"{'='*60}")
    for split, s in all_summaries.items():
        print(
            f"  {split:8s}: {s['dialogues']:5d} 对话  "
            f"{s['turns']:6d} 轮次  {s['services']:2d} 服务"
        )
    if errors:
        print(f"\n⚠️  以下划分转换失败:")
        for split, msg in errors:
            print(f"  {split}: {msg}")

    # Write a combined summary JSON next to the output directories (only if we succeeded)
    if all_summaries:
        summary_path = output_root / "conversion_summary.json"
        output_root.mkdir(parents=True, exist_ok=True)
    else:
        summary_path = Path(args.data_root).parent / "conversion_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "source": str(data_root),
                "splits": all_summaries,
                "errors": [{"split": s, "error": m} for s, m in errors],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n📄 汇总报告已写入: {summary_path}")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
