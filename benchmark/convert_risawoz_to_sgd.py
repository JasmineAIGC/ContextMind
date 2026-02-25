#!/usr/bin/env python3
"""
RiSAWOZ → SGD 格式转换脚本

将 RiSAWOZ 数据集（中文多领域任务型对话）转换为
Google SGD（Schema-Guided Dialogue）格式，
以便使用 pyTOD 算法进行训练和测试。

使用方法:
    # 转换所有划分（train / val / test）
    python benchmark/convert_risawoz_to_sgd.py

    # 只转换验证集
    python benchmark/convert_risawoz_to_sgd.py --splits val

    # 指定数据目录和输出目录
    python benchmark/convert_risawoz_to_sgd.py \\
        --data-root ./data/RiSAWOZ \\
        --output-dir ./data/RiSAWOZ_SGD

    # 自定义文件名映射（RiSAWOZ 非标准文件名时）
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

from benchmark.datasets.risawoz.sgd_converter import RiSAWOZToSGDConverter


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
    if file_mapping:
        print(f"文件名映射   : {file_mapping}")
    print(f"{'='*60}\n")

    converter = RiSAWOZToSGDConverter(
        data_root=str(data_root),
        file_mapping=file_mapping,
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
