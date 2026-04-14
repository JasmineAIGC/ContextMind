#!/usr/bin/env python3
"""
DST 模式 - SGD 数据集评测脚本

使用 Google SGD (Schema-Guided Dialogue) 数据集测试 DialogueStateTracker
的槽位提取能力。

使用方式:
    python benchmark/runners/run_dst_sgd.py
    python benchmark/runners/run_dst_sgd.py --service Flights_4 --split test --limit 10
"""

import asyncio
import argparse
import datetime
import json
import logging
import sys
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

from benchmark.datasets.sgd.adapter import SGDAdapter
from benchmark.shared.intent_evaluator import IntentEvaluator
from contextmind.modes.dst import DialogueStateTracker, PromptManager
from contextmind.infra.llm_client import AdkLLMClient
from contextmind.infra.logger import get_logger, setup_logging, LogLevel

logger = get_logger(__name__)


class SGDDSTEvaluator:
    """SGD 数据集上的 DST 评测器。"""

    def __init__(self, data_root: str = "./data/SGD") -> None:
        """初始化评测器。

        Args:
            data_root: SGD 数据集根目录（包含 train/dev/test 子目录）。
        """
        self.adapter = SGDAdapter(data_root)
        self.llm_client: Optional[AdkLLMClient] = None
        self.tracker: Optional[DialogueStateTracker] = None
        self.intent_evaluator = IntentEvaluator()

    def setup_tracker(self, service_name: str, split: str = "test") -> None:
        """为指定服务初始化 LLM 客户端和 DST 追踪器。

        Args:
            service_name: SGD 服务名称（如 ``"Flights_4"``）。
            split:        数据集划分，用于加载对应的 Schema。
        """
        try:
            self.llm_client = AdkLLMClient()
            logger.info("✅ LLM 客户端初始化成功")
        except Exception as e:
            logger.error(f"❌ LLM 客户端初始化失败: {e}")
            raise

        schema = self.adapter.get_domain_schema(service_name, split=split)

        pm = PromptManager(
            domain=service_name,
            enable_dynamic_slots=True,
        )
        # 将 Schema 中定义的槽位注入 PromptManager 作为参考
        for slot_name, slot_info in schema.get("slots", {}).items():
            pm.add_slot(slot_name, slot_info.get("description", slot_name))

        self.tracker = DialogueStateTracker(
            llm_client=self.llm_client,
            prompt_manager=pm,
            max_history_turns=10,
            enable_history_summary=False,
        )
        logger.info(f"✅ DST 追踪器初始化完成 - 服务: {service_name}")

    async def evaluate_dialogue(
        self, dialogue_id: str, split: str = "test", verbose: bool = False
    ) -> Dict[str, Any]:
        """对单个对话进行 DST 评测。

        Args:
            dialogue_id: 对话 ID。
            split:       数据集划分。
            verbose:     是否输出逐轮详细信息。

        Returns:
            评测指标字典。
        """
        dialogue = self.adapter.load_dialogue(dialogue_id, split=split)

        if verbose:
            print(f"\n{'=' * 60}")
            print(f"对话: {dialogue_id}  服务: {dialogue.domain}  轮次: {len(dialogue.turns)}")
            print("=" * 60)

        self.tracker.reset()

        correct_slots = total_slots = correct_turns = 0
        cumulative_expected: Dict[str, str] = {}
        all_predicted_pairs: set = set()
        all_gt_pairs: set = set()
        all_user_utterances: List[str] = []

        for turn in dialogue.turns:
            user_utt = turn.user_utterance
            all_user_utterances.append(user_utt)
            # SGD 期望槽位展平（取多值的第一个）
            turn_expected_flat = turn.expected_slots_flat

            try:
                result = await self.tracker.process_turn(
                    user_utterance=user_utt,
                    system_utterance=turn.system_utterance,
                )
                pred_state = result.get("state", {})

                cumulative_expected.update(turn_expected_flat)
                turn_total = len(cumulative_expected)
                turn_matched = 0
                total_slots += turn_total

                for slot, gt_val in cumulative_expected.items():
                    if str(pred_state.get(slot, "")) == str(gt_val):
                        turn_matched += 1
                        correct_slots += 1

                for slot, gt_val in turn_expected_flat.items():
                    all_gt_pairs.add((slot, str(gt_val)))
                    if slot in pred_state:
                        all_predicted_pairs.add((slot, str(pred_state[slot])))
                for slot, val in pred_state.items():
                    if slot not in turn_expected_flat:
                        all_predicted_pairs.add((slot, str(val)))

                if turn_total > 0 and turn_matched == turn_total:
                    correct_turns += 1

                if verbose:
                    print(f"  T{turn.turn_id}: user={user_utt[:50]}...")
                    print(f"    pred={pred_state}  gt={turn_expected_flat}")

            except Exception as exc:
                logger.error(f"轮次 {turn.turn_id} 处理失败: {exc}")

        slot_acc = correct_slots / total_slots if total_slots else 0.0
        joint_acc = correct_turns / len(dialogue.turns) if dialogue.turns else 0.0

        tp = len(all_predicted_pairs & all_gt_pairs)
        fp = len(all_predicted_pairs - all_gt_pairs)
        fn = len(all_gt_pairs - all_predicted_pairs)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

        self.intent_evaluator.add_dialogue_evaluation(
            dialogue_id=dialogue_id,
            domain=dialogue.domain,
            predicted_intent=dialogue.domain,
            dialogue_slots=self.tracker.get_current_state(),
            user_utterances=all_user_utterances,
        )

        return {
            "dialogue_id": dialogue_id,
            "service": dialogue.domain,
            "slot_accuracy": slot_acc,
            "joint_accuracy": joint_acc,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "total_slots": total_slots,
            "correct_slots": correct_slots,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="DST on SGD 评测")
    parser.add_argument("--service", type=str, default=None, help="指定 SGD 服务名称（如 'Flights_4'）")
    parser.add_argument("--split", type=str, default="test", choices=["train", "dev", "val", "test"], help="数据集划分")
    parser.add_argument("--limit", type=int, default=None, help="限制测试对话数量")
    parser.add_argument("--data-root", type=str, default="./data/SGD", help="SGD 数据集根目录")
    parser.add_argument("--verbose", action="store_true", default=False, help="输出逐轮详细日志")
    parser.add_argument("--output", type=str, default=None, help="将结果保存到 JSON 文件")
    args = parser.parse_args()

    setup_logging(LogLevel.DEBUG if args.verbose else LogLevel.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)

    print(f"\n{'=' * 70}")
    print("=== DST on SGD 评测 ===")
    print(f"数据目录: {args.data_root}  划分: {args.split}")
    print(f"{'=' * 70}\n")

    evaluator = SGDDSTEvaluator(data_root=args.data_root)

    try:
        all_ids = evaluator.adapter.list_dialogue_ids(
            split=args.split, service=args.service
        )
    except Exception as exc:
        print(f"❌ 加载数据集失败: {exc}")
        print(f"请确保 SGD 数据集位于 {args.data_root} (含 train/dev/test 子目录)")
        return

    if not all_ids:
        print("未找到符合条件的对话数据")
        return

    if args.limit:
        all_ids = all_ids[: args.limit]

    print(f"共 {len(all_ids)} 个对话实例待评测")

    all_metrics: List[Dict] = []
    service_metrics: Dict[str, List[Dict]] = defaultdict(list)
    current_service: Optional[str] = None

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        for idx, did in enumerate(all_ids, 1):
            try:
                service = evaluator.adapter.get_domain(did, split=args.split)
                if service != current_service:
                    current_service = service
                    print(f"\n切换服务: {current_service}")
                    evaluator.setup_tracker(current_service, split=args.split)

                print(f"处理对话 {idx}/{len(all_ids)}: {did}", end=" ", flush=True)
                metrics = loop.run_until_complete(
                    evaluator.evaluate_dialogue(did, split=args.split, verbose=args.verbose)
                )
                all_metrics.append(metrics)
                service_metrics[current_service].append(metrics)
                print(f"✅ slot_acc={metrics['slot_accuracy']:.3f} f1={metrics['f1']:.3f}")
            except Exception as exc:
                print(f"❌ {exc}")
                logger.error(f"对话 {did} 评测失败: {exc}", exc_info=True)
    finally:
        loop.close()

    if not all_metrics:
        print("\n没有成功评测的对话")
        return

    def avg(key: str, records: List[Dict]) -> float:
        return sum(r[key] for r in records) / len(records) if records else 0.0

    print(f"\n{'=' * 70}")
    print(f"=== 汇总评测结果 ({len(all_metrics)} 个对话) ===")
    overall = {
        "slot_accuracy": avg("slot_accuracy", all_metrics),
        "joint_accuracy": avg("joint_accuracy", all_metrics),
        "precision":      avg("precision",     all_metrics),
        "recall":         avg("recall",        all_metrics),
        "f1":             avg("f1",            all_metrics),
    }
    for k, v in overall.items():
        print(f"  {k}: {v * 100:.2f}%")

    print(f"\n按服务汇总:")
    for svc, recs in sorted(service_metrics.items()):
        print(f"  {svc}: {len(recs)} 对话  slot_acc={avg('slot_accuracy', recs) * 100:.2f}%  f1={avg('f1', recs) * 100:.2f}%")

    if args.output:
        output_data = {
            "timestamp": datetime.datetime.now().isoformat(),
            "dataset": "SGD",
            "algorithm": "DST",
            "split": args.split,
            "total_dialogues": len(all_metrics),
            "overall": overall,
            "service_breakdown": {
                s: {
                    "count": len(recs),
                    "slot_accuracy":  avg("slot_accuracy",  recs),
                    "joint_accuracy": avg("joint_accuracy", recs),
                    "precision":      avg("precision",      recs),
                    "recall":         avg("recall",         recs),
                    "f1":             avg("f1",             recs),
                }
                for s, recs in service_metrics.items()
            },
            "per_dialogue": all_metrics,
        }
        Path(args.output).write_text(
            json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n📄 结果已保存至: {args.output}")


if __name__ == "__main__":
    main()
