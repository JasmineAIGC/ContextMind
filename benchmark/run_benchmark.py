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
    """加载指定数据集，返回对话实例列表。

    使用各数据集适配器的原生 API（list_dialogue_ids / load_dialogue），
    统一返回携带 ``dialogue_id``、``turns`` 等属性的对话实例列表。
    """
    if dataset_name == "risawoz":
        from benchmark.datasets.risawoz import RiSAWOZAdapter
        adapter = RiSAWOZAdapter(data_root=str(data_root))
        # RiSAWOZAdapter 通过 get_dialogues_by_domain(domain=None, split) 列举 ID
        dialogue_ids: list = adapter.get_dialogues_by_domain(domain=None, split=split)
        if limit is not None:
            dialogue_ids = dialogue_ids[:limit]
        dialogues = []
        for did in dialogue_ids:
            try:
                dialogues.append(adapter.load_dialogue(did, split=split))
            except Exception as exc:
                logger.warning(f"[risawoz] 跳过对话 {did}: {exc}")
        return dialogues

    elif dataset_name == "sgd":
        from benchmark.datasets.sgd import SGDAdapter
        adapter = SGDAdapter(data_root=str(data_root))
        dialogue_ids = adapter.list_dialogue_ids(split=split)
        if limit is not None:
            dialogue_ids = dialogue_ids[:limit]
        dialogues = []
        for did in dialogue_ids:
            try:
                dialogues.append(adapter.load_dialogue(did, split=split))
            except Exception as exc:
                logger.warning(f"[sgd] 跳过对话 {did}: {exc}")
        return dialogues

    elif dataset_name == "transfertod":
        from benchmark.datasets.transfertod import TransferTODAdapter
        adapter = TransferTODAdapter(data_root=str(data_root))
        dialogue_ids = adapter.list_dialogues()
        if limit is not None:
            dialogue_ids = dialogue_ids[:limit]
        dialogues = []
        for did in dialogue_ids:
            try:
                dialogues.append(adapter.load_dialogue(did))
            except Exception as exc:
                logger.warning(f"[transfertod] 跳过对话 {did}: {exc}")
        return dialogues

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


def _add_turn_to_evaluator(
    evaluator,
    algorithm: str,
    dialogue,
    turn,
    result: dict,
) -> None:
    """将单轮评测结果记录到对应算法的评测器。"""
    scenario = getattr(dialogue, "domain", "unknown")

    if algorithm in ("dst", "fnctod"):
        predicted = result.get("state") or result.get("turn_updates") or {}
        ground_truth = getattr(turn, "expected_slots", {})
        # SGD 允许多值列表；展开为字符串以便统一比较
        gt_flat = {
            k: (v[0] if isinstance(v, list) and v else str(v))
            for k, v in ground_truth.items()
        }
        evaluator.add_prediction(
            predicted={str(k): str(v) for k, v in predicted.items()},
            ground_truth=gt_flat,
            domain=scenario,
        )

    elif algorithm == "pytod":
        exec_result = result.get("execution")
        exec_ok = bool(exec_result and getattr(exec_result, "success", False))
        evaluator.add_turn(
            program_text=result.get("program_text", ""),
            exec_success=exec_ok,
            response=result.get("response", ""),
            scenario=scenario,
        )

    elif algorithm == "evolve":
        state = result.get("state") or {}
        evaluator.add_turn(
            extracted_knowledge_count=state.get("session_history_count", 0),
            context_items_used=state.get("context_items", 0),
            response=result.get("response", ""),
            scenario=scenario,
        )


async def run(args: argparse.Namespace) -> dict:
    data_root = Path(args.data_root) if args.data_root else DATASET_DEFAULT_ROOT[args.dataset]
    logger.info(f"算法: {args.algorithm} | 数据集: {args.dataset} | 分片: {args.split} | 数据根目录: {data_root}")

    dialogues = load_dataset(args.dataset, data_root, args.split, args.limit)
    logger.info(f"加载对话数: {len(dialogues)}")

    evaluator = load_evaluator(args.algorithm)

    from contextmind.modes import build_tracker
    tracker = build_tracker(args.algorithm, model=args.model if args.model else None)

    for i, dialogue in enumerate(dialogues):
        dialogue_id = getattr(dialogue, "dialogue_id", str(i))
        logger.info(f"[{i + 1}/{len(dialogues)}] 评测对话: {dialogue_id}")
        tracker.reset()
        turns = getattr(dialogue, "turns", [])
        for turn in turns:
            user_utt = getattr(turn, "user_utterance", "")
            if not user_utt:
                continue
            try:
                result = await tracker.process_turn(user_utt)
                _add_turn_to_evaluator(evaluator, args.algorithm, dialogue, turn, result)
            except Exception as exc:
                logger.warning(f"[{dialogue_id}] 轮次评测失败: {exc}")

    metrics = evaluator.calculate_metrics()
    return metrics.to_dict()


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
