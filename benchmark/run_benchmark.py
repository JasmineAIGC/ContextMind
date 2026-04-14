#!/usr/bin/env python3
"""
统一评测入口

将原来 12 个独立 runner 脚本（4算法 × 3数据集）合并为一个入口，
通过 --algorithm 和 --dataset 参数驱动。

用法示例：
    python benchmark/run_benchmark.py --algorithm dst --dataset risawoz --split val
    python benchmark/run_benchmark.py --algorithm pytod --dataset sgd --limit 20
    python benchmark/run_benchmark.py --algorithm evolve --dataset transfertod --split test
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# 将项目根目录加入 Python 路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

ALGORITHMS = ["dst", "fnctod", "pytod", "evolve"]
DATASETS = ["risawoz", "sgd", "transfertod"]

DATASET_DEFAULT_ROOT = {
    "risawoz": PROJECT_ROOT / "resources" / "dataset" / "RiSAWOZ",
    "sgd": PROJECT_ROOT / "resources" / "dataset" / "SGD",
    "transfertod": PROJECT_ROOT / "resources" / "dataset" / "TransferTOD",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ContextMind 对话系统统一评测入口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--algorithm", "-a",
        required=True,
        choices=ALGORITHMS,
        help="评测算法: dst | fnctod | pytod | evolve",
    )
    parser.add_argument(
        "--dataset", "-d",
        required=True,
        choices=DATASETS,
        help="数据集: risawoz | sgd | transfertod",
    )
    parser.add_argument(
        "--split",
        default="val",
        choices=["train", "val", "test"],
        help="数据集分片（默认: val）",
    )
    parser.add_argument(
        "--data-root",
        default=None,
        help="数据集根目录（默认: resources/dataset/<DatasetName>）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="最多评测对话数量（用于快速调试）",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="结果输出 JSON 文件路径（不指定则只打印到控制台）",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="LLM 模型名称（覆盖配置文件默认值）",
    )
    return parser


def load_dataset(dataset_name: str, data_root: Path, split: str, limit: int | None):
    """加载指定数据集，返回对话列表。"""
    if dataset_name == "risawoz":
        from benchmark.datasets.risawoz import RiSAWOZAdapter
        adapter = RiSAWOZAdapter(data_root=data_root)
        return adapter.load(split=split, limit=limit)
    elif dataset_name == "sgd":
        from benchmark.datasets.sgd import SGDAdapter
        adapter = SGDAdapter(data_root=data_root)
        return adapter.load(split=split, limit=limit)
    elif dataset_name == "transfertod":
        from benchmark.datasets.transfertod import TransferTODAdapter
        adapter = TransferTODAdapter(data_root=data_root)
        return adapter.load(split=split, limit=limit)
    else:
        raise ValueError(f"未知数据集: {dataset_name}")


def load_evaluator(algorithm: str):
    """加载指定算法的评测器。"""
    if algorithm == "dst":
        from benchmark.evaluators.dst import DSTEvaluator
        return DSTEvaluator()
    elif algorithm == "fnctod":
        from benchmark.evaluators.fnctod import FnCTODEvaluator
        return FnCTODEvaluator()
    elif algorithm == "pytod":
        from benchmark.evaluators.pytod import PyTODEvaluator
        return PyTODEvaluator()
    elif algorithm == "evolve":
        from benchmark.evaluators.evolve import EvolveEvaluator
        return EvolveEvaluator()
    else:
        raise ValueError(f"未知算法: {algorithm}")


async def run(args: argparse.Namespace) -> dict:
    data_root = Path(args.data_root) if args.data_root else DATASET_DEFAULT_ROOT[args.dataset]
    logger.info(f"算法: {args.algorithm} | 数据集: {args.dataset} | 分片: {args.split} | 数据根目录: {data_root}")

    dialogues = load_dataset(args.dataset, data_root, args.split, args.limit)
    logger.info(f"加载对话数: {len(dialogues)}")

    evaluator = load_evaluator(args.algorithm)

    from contextmind.modes import build_tracker
    tracker_kwargs = {}
    if args.model:
        tracker_kwargs["model"] = args.model

    tracker = build_tracker(args.algorithm, **tracker_kwargs)

    for i, dialogue in enumerate(dialogues):
        logger.info(f"[{i + 1}/{len(dialogues)}] 评测对话: {getattr(dialogue, 'dialogue_id', i)}")
        try:
            result = await tracker.run_dialogue(dialogue)
            evaluator.add(dialogue, result)
        except Exception as exc:
            logger.warning(f"对话评测失败: {exc}")

    metrics = evaluator.calculate_metrics()
    result_dict = evaluator.metrics_to_dict(metrics)
    return result_dict


def main():
    parser = build_parser()
    args = parser.parse_args()

    results = asyncio.run(run(args))

    print(json.dumps(results, ensure_ascii=False, indent=2))

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info(f"结果已写入: {out_path}")


if __name__ == "__main__":
    main()
