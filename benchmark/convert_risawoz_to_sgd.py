#!/usr/bin/env python3
"""
RiSAWOZ → SGD 格式转换脚本

将 RiSAWOZ 数据集（中文多领域任务型对话）转换为
Google SGD（Schema-Guided Dialogue）格式，
以便使用 pyTOD 算法进行训练和测试。

----------------------------------------------------------------------
使用哪个 RiSAWOZ 数据目录？
----------------------------------------------------------------------

RiSAWOZ 解压后的实际目录结构如下（--data-root 应指向子目录）：

  RiSAWOZ-data/
    source-data/                 ← --data-root 指向这里（推荐）
      all_train10000.json
      all_dev600.json
      all_test600_new.json
      multi_test230_new.json
      single_test370_new.json
      all_(11200)_new.json
    task2-data-DST/              ← --data-root 指向这里（DST）
      dst_all_train10000.json
      dst_all_dev600.json
      dst_all_test600_new.json
      dst_multi_test230_new.json
      dst_single_test370_new.json
    task3-data-E2E-Context-to-text/  ← train.json / val.json / test.json
    task5-data-Unified-generative-ellipsis-and-coreference-resolution/
      all_train10000.json  all_dev600.json  all_test600_new.json  ...
    task1-data-NLU/              ← ❌ 不支持转换（IOB 格式）
    task4-data-Coreference resolution/  ← ❌ 不支持转换（CoNLL 格式）

----------------------------------------------------------------------
各数据目录兼容性
----------------------------------------------------------------------

  ✅ source-data/（推荐）
     完整的原始对话标注，dialogue_act + belief_state，信息最丰富
     --source-format source-data
     文件映射: train→all_train10000.json, val→all_dev600.json,
               test→all_test600_new.json

  ✅ task2-data-DST/（也支持）
     DST 专用格式，user_utterance + system_utterance + user_acts
     --source-format task2-dst
     文件映射: train→dst_all_train10000.json, val→dst_all_dev600.json,
               test→dst_all_test600_new.json

  ✅ task5-data-Unified.../（也支持）
     与 source-data 格式相同（文件名相同）
     --source-format task5-unified
     文件映射: train→all_train10000.json, val→all_dev600.json,
               test→all_test600_new.json

  ⚠️  task3-data-E2E-Context-to-text/（部分支持）
     标准文件名（train.json / val.json / test.json），但缺少 belief_state
     --source-format task3-e2e

  ❌ task1-data-NLU/    — IOB 格式文本文件，不可转换
  ❌ task4-data-Coreference resolution/  — CoNLL 格式，不可转换

----------------------------------------------------------------------
使用方法
----------------------------------------------------------------------

    # 使用 source-data/（推荐）
    python benchmark/convert_risawoz_to_sgd.py \\
        --data-root ./data/RiSAWOZ-data/source-data \\
        --source-format source-data \\
        --output-dir ./data/RiSAWOZ_SGD

    # 使用 task2-data-DST/
    python benchmark/convert_risawoz_to_sgd.py \\
        --data-root ./data/RiSAWOZ-data/task2-data-DST \\
        --source-format task2-dst

    # 只转换验证集
    python benchmark/convert_risawoz_to_sgd.py \\
        --data-root ./data/RiSAWOZ-data/source-data \\
        --source-format source-data --splits val

    # 手动指定文件名映射（自定义测试文件）
    python benchmark/convert_risawoz_to_sgd.py \\
        --data-root ./data/RiSAWOZ-data/source-data \\
        --source-format source-data \\
        --file-mapping test=multi_test230_new.json

输出目录结构（与 SGD 相同）:
    <output-dir>/
        train/
            schema.json           # 所有服务的 Schema 定义
            dialogues_001.json    # 对话文件（每个最多 1000 条）
            ...
        val/
            schema.json
            dialogues_001.json
        test/
            schema.json
            dialogues_001.json
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
        default="./data/RiSAWOZ-data/source-data",
        help=(
            "RiSAWOZ 数据子目录路径（指向含 JSON 文件的目录）。\n"
            "  source-data 格式: ./data/RiSAWOZ-data/source-data\n"
            "  task2-dst 格式:   ./data/RiSAWOZ-data/task2-data-DST\n"
            "（默认: ./data/RiSAWOZ-data/source-data）"
        ),
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
    parser.add_argument(
        "--inspect",
        action="store_true",
        help=(
            "检查模式：打印第一条对话的原始结构（对话ID、keys、前几个 turn 的 role/keys），"
            "不执行转换。用于排查数据格式问题。"
        ),
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
    # Show the effective file mapping (user-supplied overrides auto-mapping)
    from benchmark.datasets.risawoz.adapter import RISAWOZ_FILE_MAPPINGS as _FM
    if file_mapping:
        print(f"文件名映射   : {file_mapping}（用户自定义）")
    elif args.source_format in _FM:
        print(f"文件名映射   : {_FM[args.source_format]}（{args.source_format} 默认）")
    print(f"{'='*60}\n")

    converter = RiSAWOZToSGDConverter(
        data_root=str(data_root),
        file_mapping=file_mapping,
        source_format=args.source_format,
    )

    # ── Inspect mode: dump first dialogue structure and exit ──────────
    if args.inspect:
        split = args.splits[0]
        print(f"\n🔍 检查模式: 读取 '{split}' 划分的第一条对话结构")
        try:
            raw_data = converter.adapter._load_data_file(split)
            dialogues = raw_data if isinstance(raw_data, list) else list(raw_data.values())
            first = next((d for d in dialogues if isinstance(d, dict)), None)
            if first is None:
                print("  ❌ 未找到任何对话 dict")
                sys.exit(1)
            print(f"\n  对话级别 keys: {list(first.keys())}")
            turns = first.get("dialogue", [])
            print(f"  'dialogue' 下共 {len(turns)} 个 turn")
            for i, t in enumerate(turns[:6]):
                if isinstance(t, dict):
                    role_val = repr(t.get("role", "<missing>"))
                    turn_keys = list(t.keys())
                    bs_sample = t.get("belief_state", "—")
                    da_sample = t.get("dialogue_act", "—")
                    if isinstance(da_sample, list):
                        da_sample = da_sample[:2]
                    if isinstance(bs_sample, list):
                        bs_sample = bs_sample[:2]
                    print(
                        f"  turn[{i}]: role={role_val}  keys={turn_keys}\n"
                        f"           belief_state (首2): {bs_sample}\n"
                        f"           dialogue_act  (首2): {da_sample}"
                    )
                else:
                    print(f"  turn[{i}]: {type(t).__name__}: {t!r}")
        except Exception as exc:
            print(f"  ❌ 读取失败: {exc}")
            sys.exit(1)
        return

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
