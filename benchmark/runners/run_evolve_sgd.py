#!/usr/bin/env python3
"""
Evolve 模式 - SGD 数据集评测脚本

使用 Google SGD 数据集测试 EvolveApplication 的上下文管理能力。

使用方式:
    python benchmark/runners/run_evolve_sgd.py
    python benchmark/runners/run_evolve_sgd.py --service Flights_4 --split test --limit 5
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
from benchmark.algorithms.evolve import EvolveEvaluator
from contextmind.modes.evolve import EvolveEngine, EvolveApplication
from contextmind.infra.llm_client import AdkLLMClient
from contextmind.infra.logger import get_logger, setup_logging, LogLevel

logger = get_logger(__name__)


class SGDEvolveEvaluator:
    """SGD 数据集上的 Evolve 评测器。"""

    def __init__(self, data_root: str = "./data/SGD") -> None:
        self.adapter = SGDAdapter(data_root)
        self.llm_client: Optional[AdkLLMClient] = None
        self.evaluator = EvolveEvaluator()

    def setup(self) -> None:
        try:
            self.llm_client = AdkLLMClient()
            logger.info("✅ LLM 客户端初始化成功")
        except Exception as e:
            logger.error(f"❌ LLM 客户端初始化失败: {e}")
            raise

    async def evaluate_dialogue(
        self, dialogue_id: str, split: str = "test", verbose: bool = False
    ) -> Dict[str, Any]:
        """对单个对话进行 Evolve 评测。"""
        dialogue = self.adapter.load_dialogue(dialogue_id, split=split)
        scenario = f"{dialogue.domain}/{dialogue_id}"
        schema = self.adapter.get_domain_schema(dialogue.domain, split=split)

        engine = EvolveEngine(
            app_name=f"benchmark_evolve_sgd_{dialogue.domain}",
            user_id=f"benchmark_{dialogue_id}",
            llm_client=self.llm_client,
        )
        app = EvolveApplication(
            evolve_engine=engine,
            system_prompt=(
                f"You are a task-oriented dialogue assistant specializing in {dialogue.domain}. "
                f"{schema.get('description', '')} "
                f"Please understand the user's intent and provide concise, accurate responses."
            ),
            llm_client=self.llm_client,
        )
        self.evaluator.reset()

        for turn in dialogue.turns:
            user_utt = turn.user_utterance
            try:
                mem_before = len(app.evolve_engine.memory_bank.get_memory_cache())
                response, debug_info = await app.process_turn(user_utt, debug=True)
                await app.evolve_engine.extract_knowledge(auto_store=True)
                mem_after = len(app.evolve_engine.memory_bank.get_memory_cache())

                new_knowledge = mem_after - mem_before
                has_context = "## 已知信息" in debug_info.get("prompt", "")

                self.evaluator.add_turn(
                    extracted_knowledge_count=new_knowledge,
                    context_items_used=1 if has_context else 0,
                    response=str(response) if response else "",
                    scenario=scenario,
                )

                if verbose:
                    print(f"  T{turn.turn_id}: {user_utt[:50]}  extract={new_knowledge>0}  ctx={has_context}")
            except Exception as exc:
                logger.error(f"轮次 {turn.turn_id} 失败: {exc}")
                self.evaluator.add_turn(0, 0, "", scenario)

        metrics = self.evaluator.calculate_metrics()
        return {"dialogue_id": dialogue_id, "service": dialogue.domain, **metrics.to_dict()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evolve on SGD 评测")
    parser.add_argument("--service", type=str, default=None)
    parser.add_argument("--split", type=str, default="test", choices=["train", "dev", "val", "test"])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--data-root", type=str, default="./data/SGD")
    parser.add_argument("--verbose", action="store_true", default=False)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    setup_logging(LogLevel.DEBUG if args.verbose else LogLevel.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)

    print(f"\n{'=' * 70}\n=== Evolve on SGD 评测 ===\n{'=' * 70}\n")

    evaluator = SGDEvolveEvaluator(data_root=args.data_root)
    try:
        evaluator.setup()
    except Exception as exc:
        print(f"❌ 初始化失败: {exc}")
        return

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

    all_results: List[Dict] = []
    service_results: Dict[str, List[Dict]] = defaultdict(list)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        for idx, did in enumerate(all_ids, 1):
            try:
                service = evaluator.adapter.get_domain(did, split=args.split)
                print(f"[{idx}/{len(all_ids)}] {did} ({service})", end=" ", flush=True)
                result = loop.run_until_complete(
                    evaluator.evaluate_dialogue(did, split=args.split, verbose=args.verbose)
                )
                all_results.append(result)
                service_results[service].append(result)
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
        return sum(r.get(k1, {}).get(k2, 0) for r in records) / len(records) if records else 0.0

    print(f"\n{'=' * 70}\n=== 汇总 ({len(all_results)} 对话) ===")
    print(f"  记忆提取率:  {avg_nested(all_results, 'memory_extraction', 'memory_extraction_rate') * 100:.2f}%")
    print(f"  上下文利用率: {avg_nested(all_results, 'context_utilization', 'context_utilization_rate') * 100:.2f}%")
    print(f"  回复生成率:  {avg_nested(all_results, 'response_generation', 'response_generation_rate') * 100:.2f}%")
    print(f"  全流程成功率: {avg_nested(all_results, 'full_pipeline', 'rate') * 100:.2f}%")

    if args.output:
        output_data = {
            "timestamp": datetime.datetime.now().isoformat(),
            "dataset": "SGD", "algorithm": "Evolve", "split": args.split,
            "total_dialogues": len(all_results),
            "overall": {
                "memory_extraction_rate": avg_nested(all_results, "memory_extraction", "memory_extraction_rate"),
                "context_utilization_rate": avg_nested(all_results, "context_utilization", "context_utilization_rate"),
                "response_generation_rate": avg_nested(all_results, "response_generation", "response_generation_rate"),
                "full_pipeline_rate": avg_nested(all_results, "full_pipeline", "rate"),
            },
            "per_dialogue": all_results,
        }
        Path(args.output).write_text(json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n📄 结果已保存至: {args.output}")


if __name__ == "__main__":
    main()
