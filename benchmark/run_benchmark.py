#!/usr/bin/env python3
"""
统一评测入口

将原来 12 个独立 runner 脚本（4算法 × 3数据集）合并为一个入口，
通过 --algorithm 和 --dataset 参数驱动。

支持的数据集:
    risawoz    - 中文 RiSAWOZ 数据集 (内置: resources/data/risawoz_test.json)
    sgd        - Google Schema-Guided Dialogue (需手动下载，见 benchmark/prepare_datasets.py)
    transfertod - TransferTOD 中文数据集 (需手动下载，见 benchmark/prepare_datasets.py)

用法示例:
    # RiSAWOZ 测试集 (开箱即用)
    python benchmark/run_benchmark.py --algorithm dst --dataset risawoz
    python benchmark/run_benchmark.py --algorithm fnctod --dataset risawoz --limit 50
    python benchmark/run_benchmark.py --algorithm dst --dataset risawoz --output results/dst_risawoz.json

    # SGD (需先下载数据集)
    python benchmark/run_benchmark.py --algorithm dst --dataset sgd --split test
    python benchmark/run_benchmark.py --algorithm pytod --dataset sgd --split test --limit 20

    # TransferTOD (需先下载数据集)
    python benchmark/run_benchmark.py --algorithm evolve --dataset transfertod

数据集下载:
    运行 python benchmark/prepare_datasets.py --help 查看各数据集的下载说明。
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

# RiSAWOZ 内置数据：单一 test 文件，直接放在 resources/data/ 下
# SGD / TransferTOD 需要用户自行下载并解压到对应目录
DATASET_DEFAULT_ROOT = {
    "risawoz": PROJECT_ROOT / "resources" / "data",
    "sgd": PROJECT_ROOT / "resources" / "dataset" / "SGD",
    "transfertod": PROJECT_ROOT / "resources" / "dataset" / "TransferTOD",
}

# RiSAWOZ 内置文件的 split → 文件名映射
# test 分片内置于 resources/data/risawoz_test.json
# train/val 需通过 prepare_datasets.py --parse 生成
RISAWOZ_FILE_MAPPING = {
    "train": "risawoz_train.json",
    "val":   "risawoz_val.json",
    "test":  "risawoz_test.json",
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
        default=None,
        choices=["train", "val", "test"],
        help=(
            "数据集分片 (risawoz 内置仅有 test；sgd/transfertod 默认 test)。"
            "不指定时按各数据集默认值自动选择。"
        ),
    )
    parser.add_argument(
        "--data-root",
        default=None,
        help=(
            "数据集根目录（不指定则使用默认路径）。"
            "risawoz 默认: resources/data/，"
            "sgd/transfertod 默认: resources/dataset/<DatasetName>/。"
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="最多评测对话数量（用于快速调试，如 --limit 20）",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="结果输出 JSON 文件路径（不指定则只打印到控制台）",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="LLM 模型名称（覆盖 .env 配置默认值）",
    )
    return parser


def _resolve_split(dataset_name: str, split: str | None) -> str:
    """解析数据集分片名称，为未指定分片时选择合理默认值。

    - risawoz 内置文件仅有 "test"，缺省用 "test"
    - sgd / transfertod 缺省用 "test"
    """
    if split is not None:
        return split
    return "test"


def _check_data_root(dataset_name: str, data_root: Path) -> None:
    """检查数据集根目录是否存在，不存在时给出友好提示并退出。"""
    if not data_root.exists():
        if dataset_name == "risawoz":
            logger.error(
                f"RiSAWOZ 数据目录不存在: {data_root}\n"
                f"内置测试文件应位于: resources/data/risawoz_test.json\n"
                f"请检查文件是否已存在，或通过 --data-root 指定正确路径。"
            )
        else:
            logger.error(
                f"{dataset_name.upper()} 数据目录不存在: {data_root}\n"
                f"请先下载数据集：python benchmark/prepare_datasets.py --dataset {dataset_name}"
            )
        sys.exit(1)


def load_dataset(dataset_name: str, data_root: Path, split: str, limit: int | None):
    """加载指定数据集，返回对话实例列表。

    使用各数据集适配器的原生 API（list_dialogue_ids / load_dialogue），
    统一返回携带 ``dialogue_id``、``turns`` 等属性的对话实例列表。

    RiSAWOZ 数据格式 (resources/data/risawoz_test.json):
        [{
            "dialogue_idx": "attraction_goal_1-13_v2###8382",
            "domains": ["旅游景点"],
            "dialogue": [
                {
                    "turn_idx": 0,
                    "transcript": "用户话语...",
                    "system_transcript": "系统话语...",
                    "belief_state": [{"slots": [["旅游景点-区域", "昆山"]], "act": "inform"}],
                    "turn_label": [["旅游景点-区域", "昆山"]]
                },
                ...
            ]
        }]

    SGD 数据格式 (resources/dataset/SGD/{split}/dialogues_*.json):
        标准 Google SGD 格式，包含 schema.json + dialogues_XXX.json。

    TransferTOD 数据格式 (resources/dataset/TransferTOD/data/raw_data/{clean|noise}/):
        [{
            "id": 1, "task": "酒店", "extract_slot": 4,
            "content": [{"Turn": 0, "origin_slots": {...}, "new_slots": {...},
                         "conversations": [{"from": "user", "value": "..."}, ...]}]
        }]
    """
    _check_data_root(dataset_name, data_root)

    if dataset_name == "risawoz":
        from benchmark.datasets.risawoz import RiSAWOZAdapter
        # 内置测试文件仅包含 test 分片；若用户下载了完整数据集，
        # 可通过 --data-root 指定 source-data/ 等子目录，并配合 --split 使用。
        adapter = RiSAWOZAdapter(data_root=str(data_root), file_mapping=RISAWOZ_FILE_MAPPING)
        dialogue_ids: list = adapter.get_dialogues_by_domain(domain=None, split=split)
        if not dialogue_ids:
            logger.error(
                f"RiSAWOZ split='{split}' 未找到任何对话。\n"
                f"  - 内置数据仅包含 split='test'（对应 risawoz_test.json）。\n"
                f"  - 如需 train/val，请先运行:\n"
                f"      python benchmark/prepare_datasets.py --dataset risawoz \\\n"
                f"          --source /path/to/RiSAWOZ --parse"
            )
            return []
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
        # TransferTOD 没有 train/val/test 分片概念；data_type="clean" 表示干净数据
        dialogue_ids = adapter.list_dialogues(data_type="clean")
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
    result,
) -> None:
    """将单轮评测结果记录到对应算法的评测器。

    各追踪器的 process_turn 返回值格式:
        dst:     Dict[str, str]           — 直接是累积对话状态字典
        fnctod:  {"state": {...}, "response": str, "updates": {...}}
        pytod:   {"response": str, "program_text": str, "state": dict, "execution": ...}
        evolve:  str                      — EvolveApplication 返回自然语言回复文本
    """
    scenario = getattr(dialogue, "domain", "unknown")

    if algorithm == "dst":
        # DST 追踪器直接返回累积状态字典 Dict[str, str]
        predicted = result if isinstance(result, dict) else {}
        ground_truth = getattr(turn, "expected_slots", {})
        gt_flat = {
            k: (v[0] if isinstance(v, list) and v else str(v))
            for k, v in ground_truth.items()
        }
        evaluator.add_prediction(
            predicted={str(k): str(v) for k, v in predicted.items()},
            ground_truth=gt_flat,
            domain=scenario,
        )

    elif algorithm == "fnctod":
        # FnCTOD 追踪器返回 {"state": {...}, "response": str, "updates": {...}}
        predicted = result.get("state") or result.get("updates") or {}
        ground_truth = getattr(turn, "expected_slots", {})
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
        # PyTOD 追踪器返回 {"response": str, "program_text": str, "state": dict, "execution": ...}
        exec_result = result.get("execution")
        exec_ok = bool(exec_result and getattr(exec_result, "success", False))
        evaluator.add_turn(
            program_text=result.get("program_text", ""),
            exec_success=exec_ok,
            response=result.get("response", ""),
            scenario=scenario,
        )

    elif algorithm == "evolve":
        # EvolveApplication.process_turn 返回 str（自然语言回复）
        response_text = result if isinstance(result, str) else str(result)
        evaluator.add_turn(
            extracted_knowledge_count=0,
            context_items_used=0,
            response=response_text,
            scenario=scenario,
        )


async def run(args: argparse.Namespace) -> dict:
    split = _resolve_split(args.dataset, args.split)
    data_root = Path(args.data_root) if args.data_root else DATASET_DEFAULT_ROOT[args.dataset]
    logger.info(f"算法: {args.algorithm} | 数据集: {args.dataset} | 分片: {split} | 数据根目录: {data_root}")

    dialogues = load_dataset(args.dataset, data_root, split, args.limit)
    logger.info(f"加载对话数: {len(dialogues)}")

    evaluator = load_evaluator(args.algorithm)

    from contextmind.modes import build_tracker
    tracker = build_tracker(args.algorithm, model=args.model if args.model else None)

    for i, dialogue in enumerate(dialogues):
        dialogue_id = getattr(dialogue, "dialogue_id", str(i))
        logger.info(f"[{i + 1}/{len(dialogues)}] 评测对话: {dialogue_id}")
        # 支持同步和异步 reset（DST/FnCTOD/PyTOD 为同步，EvolveApplication 为异步）
        reset_result = tracker.reset()
        if asyncio.iscoroutine(reset_result):
            await reset_result
        # 为支持领域感知的追踪器（如 DST）更新当前对话的领域，
        # 确保 LLM 使用正确的槽位命名格式（如 RiSAWOZ 的 "领域-槽位名" 格式）。
        domain = getattr(dialogue, "domain", None)
        if domain and hasattr(tracker, "set_domain"):
            tracker.set_domain(domain)
        turns = getattr(dialogue, "turns", [])
        for turn in turns:
            user_utt = getattr(turn, "user_utterance", "")
            if not user_utt:
                continue
            system_utt = getattr(turn, "system_utterance", "")
            try:
                result = await tracker.process_turn(user_utt, system_utterance=system_utt)
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
