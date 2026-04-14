#!/usr/bin/env python3
"""
FnCTOD 模式 - RiSAWOZ 数据集评测脚本

使用 RiSAWOZ 数据集测试 FnCTODTracker 的函数调用能力（槽位提取）。

使用方式:
    python benchmark/runners/run_fnctod_risawoz.py
    python benchmark/runners/run_fnctod_risawoz.py --domain 酒店 --split val --limit 10
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
from typing import Any, Dict, List

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

from benchmark.datasets.risawoz.adapter import RiSAWOZAdapter, RISAWOZ_FILE_MAPPINGS
from benchmark.shared.intent_evaluator import IntentEvaluator
from benchmark.shared.intent_label_loader import IntentLabelLoader
from contextmind.modes.fnctod import FnCTODTracker, FunctionManager
from contextmind.modes.fnctod.function_manager import DomainSpec, FunctionParameter, ParameterType
from contextmind.infra.llm_client import AdkLLMClient
from contextmind.infra.logger import get_logger, setup_logging, LogLevel

logger = get_logger(__name__)


class RiSAWOZFnCTODEvaluator:
    """RiSAWOZ 数据集上的 FnCTOD 评测器。"""

    def __init__(
        self,
        data_root: str = "./data/RiSAWOZ",
        file_mapping: Dict[str, str] = None,
    ) -> None:
        """初始化评测器。

        Args:
            data_root:    RiSAWOZ 数据集根目录（指向含 JSON 文件的子目录）。
            file_mapping: 自定义文件名映射（可选，不传则使用默认映射）。
        """
        self.adapter = RiSAWOZAdapter(data_root, file_mapping=file_mapping)
        self.llm_client = None
        self.tracker = None

        risawoz_intent_config = Path(__file__).parent.parent / "shared" / "configs" / "intent_labels_risawoz.json"
        self.intent_label_loader = IntentLabelLoader(str(risawoz_intent_config))
        self.intent_evaluator = IntentEvaluator(intent_label_loader=self.intent_label_loader)

    def setup_tracker(self, domain: str) -> None:
        """为指定领域初始化 LLM 客户端和 FnCTOD 追踪器。

        Args:
            domain: 领域名称（如 ``"酒店"``）。
        """
        try:
            self.llm_client = AdkLLMClient()
            logger.info("✅ LLM 客户端初始化成功")
        except Exception as e:
            logger.error(f"❌ LLM 客户端初始化失败: {e}")
            raise

        # 获取 RiSAWOZ 领域 Schema（动态加载）
        schema = self.adapter.get_domain_schema(domain)

        function_manager = FunctionManager()
        domain_spec = self._build_domain_spec(domain, schema)
        function_manager.add_domain(domain_spec)

        self.tracker = FnCTODTracker(function_manager=function_manager)
        logger.info(f"✅ FnCTOD 追踪器初始化完成 - 领域: {domain}，槽位数: {len(schema.get('slots', {}))}")

    def _build_domain_spec(self, domain: str, schema: Dict) -> DomainSpec:
        """将 RiSAWOZ schema 转换为 FnCTOD DomainSpec。"""
        parameters = []
        for slot_name, slot_info in schema.get("slots", {}).items():
            param = FunctionParameter(
                name=slot_name,
                description=slot_info.get("description", slot_name),
                param_type=ParameterType.STRING,
                required=False,
            )
            parameters.append(param)

        return DomainSpec(
            name=domain,
            description=schema.get("description", f"{domain} 领域对话"),
            parameters=parameters,
        )

    def _strip_domain_prefix(self, state: Dict[str, Any], domain: str) -> Dict[str, Any]:
        """从预测状态中去除域前缀（如 ``"hotel-星级"`` → ``"星级"``）。"""
        result: Dict[str, Any] = {}
        # 动态检测前缀
        prefix = None
        for key in state:
            if "-" in key:
                prefix = key.split("-", 1)[0] + "-"
                break

        for key, value in state.items():
            if prefix and key.startswith(prefix):
                slot = key[len(prefix):]
            else:
                slot = key
            if isinstance(value, dict):
                result.update(value)
            else:
                result[slot] = value
        return result

    async def evaluate_dialogue(
        self, dialogue_id: str, split: str = "val", verbose: bool = False
    ) -> Dict[str, Any]:
        """对单个对话进行 FnCTOD 评测。

        Args:
            dialogue_id: 对话 ID。
            split:       数据集划分（train/val/test）。
            verbose:     是否输出逐轮详细信息。

        Returns:
            评测指标字典。
        """
        dialogue = self.adapter.load_dialogue(dialogue_id, split=split)

        if verbose:
            print(f"\n{'=' * 60}")
            print(f"测试对话: {dialogue_id}  领域: {dialogue.domain}  轮次: {len(dialogue.turns)}")
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
            try:
                response = await self.tracker.process_turn(user_utt)
                raw_state = response.get("state", {})
                pred_slots = self._strip_domain_prefix(raw_state, dialogue.domain)

                cumulative_expected.update(turn.expected_slots)
                turn_total = len(cumulative_expected)
                turn_matched = 0
                total_slots += turn_total

                for slot, gt_val in cumulative_expected.items():
                    if str(pred_slots.get(slot, "")) == str(gt_val):
                        turn_matched += 1
                        correct_slots += 1

                for slot, gt_val in turn.expected_slots.items():
                    all_gt_pairs.add((slot, str(gt_val)))
                    if slot in pred_slots:
                        all_predicted_pairs.add((slot, str(pred_slots[slot])))
                for slot, val in pred_slots.items():
                    if slot not in turn.expected_slots:
                        all_predicted_pairs.add((slot, str(val)))

                if turn_total > 0 and turn_matched == turn_total:
                    correct_turns += 1

                if verbose:
                    print(f"  轮次 {turn.turn_id + 1}: 用户={user_utt[:40]}...")
                    print(f"    预测: {pred_slots}  期望: {turn.expected_slots}")

            except Exception as exc:
                logger.error(f"处理轮次 {turn.turn_id} 失败: {exc}")

        slot_acc = correct_slots / total_slots if total_slots else 0.0
        joint_acc = correct_turns / len(dialogue.turns) if dialogue.turns else 0.0

        tp = len(all_predicted_pairs & all_gt_pairs)
        fp = len(all_predicted_pairs - all_gt_pairs)
        fn = len(all_gt_pairs - all_predicted_pairs)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

        # 意图评测
        final_state_no_prefix = self._strip_domain_prefix(
            self.tracker.current_state, dialogue.domain
        )
        self.intent_evaluator.add_dialogue_evaluation(
            dialogue_id=dialogue_id,
            domain=dialogue.domain,
            predicted_intent=dialogue.domain,
            dialogue_slots=final_state_no_prefix,
            user_utterances=all_user_utterances,
        )

        return {
            "dialogue_id": dialogue_id,
            "domain": dialogue.domain,
            "slot_accuracy": slot_acc,
            "joint_accuracy": joint_acc,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "total_slots": total_slots,
            "correct_slots": correct_slots,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="FnCTOD on RiSAWOZ 评测")
    parser.add_argument("--domain", type=str, default=None, help="指定测试领域（如 '酒店'）")
    parser.add_argument("--split", type=str, default="val", choices=["train", "val", "test"], help="数据集划分")
    parser.add_argument("--limit", type=int, default=None, help="限制测试对话数量")
    parser.add_argument(
        "--data-root",
        type=str,
        default="./data/RiSAWOZ-data/source-data",
        help="RiSAWOZ 数据目录（含 JSON 文件的子目录）",
    )
    parser.add_argument(
        "--format",
        type=str,
        default="source-data",
        choices=list(RISAWOZ_FILE_MAPPINGS.keys()),
        help="RiSAWOZ 数据格式",
    )
    parser.add_argument("--verbose", action="store_true", default=False, help="输出逐轮详细日志")
    parser.add_argument("--output", type=str, default=None, help="将评测结果保存到 JSON 文件")
    args = parser.parse_args()

    setup_logging(LogLevel.DEBUG if args.verbose else LogLevel.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)

    print(f"\n{'=' * 70}")
    print("=== FnCTOD on RiSAWOZ 评测 ===")
    print(f"数据目录: {args.data_root}  格式: {args.format}  划分: {args.split}")
    print(f"{'=' * 70}\n")

    file_mapping = RISAWOZ_FILE_MAPPINGS.get(args.format)
    evaluator = RiSAWOZFnCTODEvaluator(data_root=args.data_root, file_mapping=file_mapping)

    try:
        all_ids = evaluator.adapter.get_dialogues_by_domain(domain=args.domain, split=args.split)
    except Exception as exc:
        print(f"❌ 加载数据集失败: {exc}")
        print(f"请确保数据集位于 {args.data_root}")
        return

    if not all_ids:
        print("未找到符合条件的对话数据")
        return

    if args.limit:
        all_ids = all_ids[: args.limit]

    print(f"共 {len(all_ids)} 个对话实例待评测")

    all_metrics: List[Dict] = []
    domain_metrics: Dict[str, List[Dict]] = defaultdict(list)
    current_domain = None

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        for idx, did in enumerate(all_ids, 1):
            try:
                domain = evaluator.adapter.load_dialogue(did, split=args.split).domain
                if domain != current_domain:
                    current_domain = domain
                    print(f"\n切换领域: {current_domain}")
                    evaluator.setup_tracker(current_domain)
                    if evaluator.tracker is None:
                        print(f"❌ 初始化领域 {current_domain} 失败，跳过")
                        continue

                print(f"处理对话 {idx}/{len(all_ids)}: {did}", end=" ", flush=True)
                metrics = loop.run_until_complete(
                    evaluator.evaluate_dialogue(did, split=args.split, verbose=args.verbose)
                )
                all_metrics.append(metrics)
                domain_metrics[current_domain].append(metrics)
                print(f"✅ slot_acc={metrics['slot_accuracy']:.3f} f1={metrics['f1']:.3f}")
            except Exception as exc:
                print(f"❌ {exc}")
                logger.error(f"对话 {did} 评测失败: {exc}", exc_info=True)
    finally:
        loop.close()

    if not all_metrics:
        print("\n没有成功评测的对话")
        return

    # 汇总指标
    def avg(key: str, records: List[Dict]) -> float:
        return sum(r[key] for r in records) / len(records) if records else 0.0

    print(f"\n{'=' * 70}")
    print(f"=== 汇总评测结果 ({len(all_metrics)} 个对话) ===")
    print(f"{'=' * 70}")
    overall = {
        "slot_accuracy": avg("slot_accuracy", all_metrics),
        "joint_accuracy": avg("joint_accuracy", all_metrics),
        "precision":      avg("precision",     all_metrics),
        "recall":         avg("recall",        all_metrics),
        "f1":             avg("f1",            all_metrics),
    }
    for k, v in overall.items():
        print(f"  {k}: {v * 100:.2f}%")

    print(f"\n按领域汇总:")
    for domain, recs in sorted(domain_metrics.items()):
        slot_acc = avg("slot_accuracy", recs)
        f1 = avg("f1", recs)
        print(f"  {domain}: {len(recs)} 对话  slot_acc={slot_acc * 100:.2f}%  f1={f1 * 100:.2f}%")

    if args.output:
        output_data = {
            "timestamp": datetime.datetime.now().isoformat(),
            "dataset": "RiSAWOZ",
            "algorithm": "FnCTOD",
            "split": args.split,
            "total_dialogues": len(all_metrics),
            "overall": overall,
            "domain_breakdown": {
                d: {
                    "count":        len(recs),
                    "slot_accuracy": avg("slot_accuracy", recs),
                    "joint_accuracy": avg("joint_accuracy", recs),
                    "precision":     avg("precision",     recs),
                    "recall":        avg("recall",        recs),
                    "f1":            avg("f1",            recs),
                }
                for d, recs in domain_metrics.items()
            },
            "per_dialogue": all_metrics,
        }
        Path(args.output).write_text(
            json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n📄 结果已保存至: {args.output}")


if __name__ == "__main__":
    main()
