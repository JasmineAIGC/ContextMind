#!/usr/bin/env python3
"""
FnCTOD 模式 - SGD 数据集评测脚本

使用 Google SGD (Schema-Guided Dialogue) 数据集测试 FnCTODTracker 的函数调用能力。

使用方式:
    python benchmark/runners/run_fnctod_sgd.py
    python benchmark/runners/run_fnctod_sgd.py --service Flights_4 --split test --limit 10
"""

import asyncio
import argparse
import datetime
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

from benchmark.datasets.sgd.adapter import SGDAdapter
from benchmark.shared.intent_evaluator import IntentEvaluator
from contextmind.modes.fnctod import FnCTODTracker, FunctionManager
from contextmind.modes.fnctod.function_manager import DomainSpec, FunctionParameter, ParameterType
from contextmind.infra.llm_client import AdkLLMClient
from contextmind.infra.logger import get_logger, setup_logging, LogLevel

logger = get_logger(__name__)


class SGDFnCTODEvaluator:
    """SGD 数据集上的 FnCTOD 评测器。"""

    def __init__(self, data_root: str = "./data/SGD") -> None:
        self.adapter = SGDAdapter(data_root)
        self.llm_client: Optional[AdkLLMClient] = None
        self.tracker: Optional[FnCTODTracker] = None
        self.intent_evaluator = IntentEvaluator()

    def setup_tracker(self, service_name: str, split: str = "test") -> None:
        """初始化 FnCTOD 追踪器。"""
        try:
            self.llm_client = AdkLLMClient()
        except Exception as e:
            logger.error(f"LLM 客户端初始化失败: {e}")
            raise

        schema = self.adapter.get_domain_schema(service_name, split=split)

        parameters = [
            FunctionParameter(
                name=slot_name,
                description=slot_info.get("description", slot_name),
                param_type=ParameterType.STRING,
                required=False,
            )
            for slot_name, slot_info in schema.get("slots", {}).items()
        ]
        domain_spec = DomainSpec(
            name=service_name,
            description=schema.get("description", service_name),
            parameters=parameters,
        )
        fm = FunctionManager()
        fm.add_domain(domain_spec)
        self.tracker = FnCTODTracker(function_manager=fm)
        logger.info(f"✅ FnCTOD 追踪器初始化 - 服务: {service_name}，槽位数: {len(parameters)}")

    def _strip_prefix(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """去除预测状态中的域前缀。"""
        result: Dict[str, Any] = {}
        prefix = None
        for key in state:
            if "-" in key:
                prefix = key.split("-", 1)[0] + "-"
                break
        for key, value in state.items():
            slot = key[len(prefix):] if prefix and key.startswith(prefix) else key
            if isinstance(value, dict):
                result.update(value)
            else:
                result[slot] = value
        return result

    async def evaluate_dialogue(
        self, dialogue_id: str, split: str = "test", verbose: bool = False
    ) -> Dict[str, Any]:
        """对单个对话进行 FnCTOD 评测。"""
        dialogue = self.adapter.load_dialogue(dialogue_id, split=split)
        self.tracker.reset()

        correct_slots = total_slots = correct_turns = 0
        cumulative_expected: Dict[str, str] = {}
        all_predicted_pairs: set = set()
        all_gt_pairs: set = set()
        all_user_utterances: List[str] = []

        for turn in dialogue.turns:
            user_utt = turn.user_utterance
            all_user_utterances.append(user_utt)
            turn_expected = turn.expected_slots_flat

            try:
                response = await self.tracker.process_turn(user_utt)
                raw_state = response.get("state", {})
                pred_slots = self._strip_prefix(raw_state)

                cumulative_expected.update(turn_expected)
                turn_total = len(cumulative_expected)
                turn_matched = 0
                total_slots += turn_total

                for slot, gt_val in cumulative_expected.items():
                    if str(pred_slots.get(slot, "")) == str(gt_val):
                        turn_matched += 1
                        correct_slots += 1

                for slot, gt_val in turn_expected.items():
                    all_gt_pairs.add((slot, str(gt_val)))
                    if slot in pred_slots:
                        all_predicted_pairs.add((slot, str(pred_slots[slot])))
                for slot, val in pred_slots.items():
                    if slot not in turn_expected:
                        all_predicted_pairs.add((slot, str(val)))

                if turn_total > 0 and turn_matched == turn_total:
                    correct_turns += 1

                if verbose:
                    print(f"  T{turn.turn_id}: {user_utt[:50]}...")
                    print(f"    pred={pred_slots}  gt={turn_expected}")

            except Exception as exc:
                logger.error(f"轮次 {turn.turn_id} 失败: {exc}")

        slot_acc = correct_slots / total_slots if total_slots else 0.0
        joint_acc = correct_turns / len(dialogue.turns) if dialogue.turns else 0.0

        tp = len(all_predicted_pairs & all_gt_pairs)
        fp = len(all_predicted_pairs - all_gt_pairs)
        fn = len(all_gt_pairs - all_predicted_pairs)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

        final_state = self._strip_prefix(self.tracker.current_state)
        self.intent_evaluator.add_dialogue_evaluation(
            dialogue_id=dialogue_id,
            domain=dialogue.domain,
            predicted_intent=dialogue.domain,
            dialogue_slots=final_state,
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
    parser = argparse.ArgumentParser(description="FnCTOD on SGD 评测")
    parser.add_argument("--service", type=str, default=None, help="指定 SGD 服务名称")
    parser.add_argument("--split", type=str, default="test", choices=["train", "dev", "val", "test"])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--data-root", type=str, default="./data/SGD")
    parser.add_argument("--verbose", action="store_true", default=False)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    setup_logging(LogLevel.DEBUG if args.verbose else LogLevel.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)

    print(f"\n{'=' * 70}\n=== FnCTOD on SGD 评测 ===\n{'=' * 70}\n")

    evaluator = SGDFnCTODEvaluator(data_root=args.data_root)

    try:
        all_ids = evaluator.adapter.list_dialogue_ids(split=args.split, service=args.service)
    except Exception as exc:
        print(f"❌ 加载数据集失败: {exc}")
        return

    if not all_ids:
        print("未找到对话数据")
        return
    if args.limit:
        all_ids = all_ids[: args.limit]

    print(f"共 {len(all_ids)} 个对话实例")

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

                print(f"[{idx}/{len(all_ids)}] {did}", end=" ", flush=True)
                metrics = loop.run_until_complete(
                    evaluator.evaluate_dialogue(did, split=args.split, verbose=args.verbose)
                )
                all_metrics.append(metrics)
                service_metrics[current_service].append(metrics)
                print(f"✅ slot_acc={metrics['slot_accuracy']:.3f} f1={metrics['f1']:.3f}")
            except Exception as exc:
                print(f"❌ {exc}")
    finally:
        loop.close()

    if not all_metrics:
        print("\n没有成功评测的对话")
        return

    def avg(key: str, records: List[Dict]) -> float:
        return sum(r[key] for r in records) / len(records) if records else 0.0

    print(f"\n{'=' * 70}\n=== 汇总 ({len(all_metrics)} 对话) ===")
    overall = {k: avg(k, all_metrics) for k in ["slot_accuracy", "joint_accuracy", "precision", "recall", "f1"]}
    for k, v in overall.items():
        print(f"  {k}: {v * 100:.2f}%")

    print("\n按服务汇总:")
    for svc, recs in sorted(service_metrics.items()):
        print(f"  {svc}: {len(recs)} 对话  slot_acc={avg('slot_accuracy', recs) * 100:.2f}%  f1={avg('f1', recs) * 100:.2f}%")

    if args.output:
        output_data = {
            "timestamp": datetime.datetime.now().isoformat(),
            "dataset": "SGD", "algorithm": "FnCTOD", "split": args.split,
            "total_dialogues": len(all_metrics),
            "overall": overall,
            "service_breakdown": {
                s: {"count": len(recs), **{k: avg(k, recs) for k in ["slot_accuracy", "joint_accuracy", "precision", "recall", "f1"]}}
                for s, recs in service_metrics.items()
            },
            "per_dialogue": all_metrics,
        }
        Path(args.output).write_text(json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n📄 结果已保存至: {args.output}")


if __name__ == "__main__":
    main()
