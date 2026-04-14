#!/usr/bin/env python3
"""
PyTOD 模式 - RiSAWOZ 数据集评测脚本

使用 RiSAWOZ 数据集测试 AdkPyTODTracker 的三步流程（AP → EE → DM）。

由于 RiSAWOZ 没有预生成的 pytod_apis.py 文件，使用存根模式（stub mode）评测。

使用方式:
    python benchmark/runners/run_pytod_risawoz.py
    python benchmark/runners/run_pytod_risawoz.py --domain 酒店 --split val --limit 5
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

from benchmark.datasets.risawoz.adapter import RiSAWOZAdapter, RISAWOZ_FILE_MAPPINGS
from benchmark.algorithms.pytod import PyTODEvaluator
from contextmind.modes.pytod import AdkPyTODTracker
from contextmind.modes.pytod.schemas import ServiceSchema, SlotDefinition, IntentDefinition
from contextmind.modes.pytod.execution_engine import ExecutionEngine
from contextmind.modes.pytod.tracker import _register_apis_from_schema
from contextmind.infra.llm_client import AdkLLMClient
from contextmind.infra.logger import get_logger, setup_logging, LogLevel

logger = get_logger(__name__)


def _build_service_schema_from_risawoz(domain: str, schema: Dict) -> ServiceSchema:
    """将 RiSAWOZ schema 字典转换为 PyTOD ServiceSchema。"""
    slots = [
        SlotDefinition(
            name=slot_name,
            description=slot_info.get("description", slot_name),
            is_categorical=False,
        )
        for slot_name, slot_info in schema.get("slots", {}).items()
    ]
    slot_names = [s.name for s in slots]
    intent = IntentDefinition(
        name=domain,
        description=schema.get("description", f"{domain} 领域"),
        required_slots=[],
        optional_slots=slot_names,
        result_slots=[],
    )
    return ServiceSchema(
        service_name=domain,
        description=schema.get("description", f"{domain} 服务"),
        slots=slots,
        intents=[intent],
    )


class RiSAWOZPyTODEvaluator:
    """RiSAWOZ 数据集上的 PyTOD 评测器。"""

    def __init__(
        self,
        data_root: str = "./data/RiSAWOZ",
        file_mapping: Optional[Dict[str, str]] = None,
    ) -> None:
        self.adapter = RiSAWOZAdapter(data_root, file_mapping=file_mapping)
        self.llm_client: Optional[AdkLLMClient] = None
        self.tracker: Optional[AdkPyTODTracker] = None
        self.evaluator = PyTODEvaluator()

    def setup_tracker(self, domain: str) -> None:
        """为指定领域初始化 PyTOD 追踪器。"""
        try:
            self.llm_client = AdkLLMClient()
        except Exception as e:
            logger.error(f"LLM 客户端初始化失败: {e}")
            raise

        schema_dict = self.adapter.get_domain_schema(domain)
        service_schema = _build_service_schema_from_risawoz(domain, schema_dict)

        engine = ExecutionEngine()
        _register_apis_from_schema(engine, service_schema, replace_existing=True)

        self.tracker = AdkPyTODTracker(
            llm_client=self.llm_client,
            engine=engine,
            schema=service_schema,
            scenario_context=f"RiSAWOZ 数据集 {domain} 领域评测",
            top_k_intents=5,
        )
        logger.info(f"✅ PyTOD 追踪器初始化 - 领域: {domain}")

    async def evaluate_dialogue(
        self, dialogue_id: str, split: str = "val", verbose: bool = False
    ) -> Dict[str, Any]:
        """对单个对话进行 PyTOD 评测。"""
        dialogue = self.adapter.load_dialogue(dialogue_id, split=split)
        scenario = f"{dialogue.domain}/{dialogue_id}"

        self.tracker.reset()
        self.evaluator.reset()

        for turn in dialogue.turns:
            user_utt = turn.user_utterance
            try:
                result = await self.tracker.process_turn(user_utt)
                program_text = result.get("program_text", "")
                exec_result = result.get("execution")
                exec_success = exec_result.success if exec_result else False
                response = result.get("response", "")

                self.evaluator.add_turn(
                    program_text=program_text,
                    exec_success=exec_success,
                    response=response,
                    scenario=scenario,
                )

                if verbose:
                    print(f"  T{turn.turn_id}: {user_utt[:50]}...")
                    print(f"    prog={program_text[:60]}  exec={exec_success}  resp={response[:40]}")

            except Exception as exc:
                logger.error(f"轮次 {turn.turn_id} 失败: {exc}")
                self.evaluator.add_turn("", False, "", scenario)

        metrics = self.evaluator.calculate_metrics()
        return {"dialogue_id": dialogue_id, "domain": dialogue.domain, **metrics.to_dict()}


def main() -> None:
    parser = argparse.ArgumentParser(description="PyTOD on RiSAWOZ 评测")
    parser.add_argument("--domain", type=str, default=None)
    parser.add_argument("--split", type=str, default="val", choices=["train", "val", "test"])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--data-root", type=str, default="./data/RiSAWOZ-data/source-data")
    parser.add_argument("--format", type=str, default="source-data", choices=list(RISAWOZ_FILE_MAPPINGS.keys()))
    parser.add_argument("--verbose", action="store_true", default=False)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    setup_logging(LogLevel.DEBUG if args.verbose else LogLevel.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)

    print(f"\n{'=' * 70}\n=== PyTOD on RiSAWOZ 评测 ===\n{'=' * 70}\n")

    file_mapping = RISAWOZ_FILE_MAPPINGS.get(args.format)
    evaluator = RiSAWOZPyTODEvaluator(data_root=args.data_root, file_mapping=file_mapping)

    try:
        all_ids = evaluator.adapter.get_dialogues_by_domain(domain=args.domain, split=args.split)
    except Exception as exc:
        print(f"❌ 加载数据集失败: {exc}")
        return

    if not all_ids:
        print("未找到对话数据")
        return
    if args.limit:
        all_ids = all_ids[: args.limit]

    print(f"共 {len(all_ids)} 个对话实例")

    all_results: List[Dict] = []
    domain_results: Dict[str, List[Dict]] = defaultdict(list)
    current_domain: Optional[str] = None

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

                print(f"[{idx}/{len(all_ids)}] {did}", end=" ", flush=True)
                result = loop.run_until_complete(evaluator.evaluate_dialogue(did, split=args.split, verbose=args.verbose))
                all_results.append(result)
                domain_results[current_domain].append(result)
                fp = result.get("full_pipeline", {}).get("rate", 0)
                print(f"✅ full_pipeline={fp:.3f}")
            except Exception as exc:
                print(f"❌ {exc}")
    finally:
        loop.close()

    if not all_results:
        print("\n没有成功评测的对话")
        return

    def avg_nested(records: List[Dict], k1: str, k2: str) -> float:
        vals = [r.get(k1, {}).get(k2, 0) for r in records]
        return sum(vals) / len(vals) if vals else 0.0

    print(f"\n{'=' * 70}\n=== 汇总 ({len(all_results)} 对话) ===")
    print(f"  程序生成率:  {avg_nested(all_results, 'action_parser', 'program_generation_rate') * 100:.2f}%")
    print(f"  执行成功率:  {avg_nested(all_results, 'execution_engine', 'execution_success_rate') * 100:.2f}%")
    print(f"  回复生成率:  {avg_nested(all_results, 'dialogue_manager', 'response_generation_rate') * 100:.2f}%")
    print(f"  全流程成功率: {avg_nested(all_results, 'full_pipeline', 'rate') * 100:.2f}%")

    if args.output:
        output_data = {
            "timestamp": datetime.datetime.now().isoformat(),
            "dataset": "RiSAWOZ", "algorithm": "PyTOD", "split": args.split,
            "total_dialogues": len(all_results),
            "overall": {
                "program_generation_rate": avg_nested(all_results, "action_parser", "program_generation_rate"),
                "execution_success_rate": avg_nested(all_results, "execution_engine", "execution_success_rate"),
                "response_generation_rate": avg_nested(all_results, "dialogue_manager", "response_generation_rate"),
                "full_pipeline_rate": avg_nested(all_results, "full_pipeline", "rate"),
            },
            "per_dialogue": all_results,
        }
        Path(args.output).write_text(json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n📄 结果已保存至: {args.output}")


if __name__ == "__main__":
    main()
