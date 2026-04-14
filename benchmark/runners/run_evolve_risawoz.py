#!/usr/bin/env python3
"""
Evolve 模式 - RiSAWOZ 数据集评测脚本

使用 RiSAWOZ 数据集测试 EvolveApplication 的上下文管理能力。

使用方式:
    python benchmark/runners/run_evolve_risawoz.py
    python benchmark/runners/run_evolve_risawoz.py --domain 酒店 --split val --limit 5
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
from benchmark.algorithms.evolve import EvolveEvaluator
from contextmind.modes.evolve import EvolveEngine, EvolveApplication
from contextmind.infra.llm_client import AdkLLMClient
from contextmind.infra.logger import get_logger, setup_logging, LogLevel

logger = get_logger(__name__)


class RiSAWOZEvolveEvaluator:
    """RiSAWOZ 数据集上的 Evolve 评测器。"""

    def __init__(
        self,
        data_root: str = "./data/RiSAWOZ",
        file_mapping: Optional[Dict[str, str]] = None,
    ) -> None:
        self.adapter = RiSAWOZAdapter(data_root, file_mapping=file_mapping)
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
        self, dialogue_id: str, split: str = "val", verbose: bool = False
    ) -> Dict[str, Any]:
        """对单个对话进行 Evolve 评测。"""
        dialogue = self.adapter.load_dialogue(dialogue_id, split=split)
        scenario = f"{dialogue.domain}/{dialogue_id}"

        engine = EvolveEngine(
            app_name=f"benchmark_evolve_{dialogue.domain}",
            user_id=f"benchmark_{dialogue_id}",
            llm_client=self.llm_client,
        )
        app = EvolveApplication(
            evolve_engine=engine,
            system_prompt=f"你是一个专注 {dialogue.domain} 领域的任务型对话助手，请准确理解用户意图并给出简洁回复。",
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
        return {"dialogue_id": dialogue_id, "domain": dialogue.domain, **metrics.to_dict()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evolve on RiSAWOZ 评测")
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

    print(f"\n{'=' * 70}\n=== Evolve on RiSAWOZ 评测 ===\n{'=' * 70}\n")

    file_mapping = RISAWOZ_FILE_MAPPINGS.get(args.format)
    evaluator = RiSAWOZEvolveEvaluator(data_root=args.data_root, file_mapping=file_mapping)
    try:
        evaluator.setup()
    except Exception as exc:
        print(f"❌ 初始化失败: {exc}")
        return

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

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        for idx, did in enumerate(all_ids, 1):
            try:
                domain = evaluator.adapter.load_dialogue(did, split=args.split).domain
                print(f"[{idx}/{len(all_ids)}] {did} ({domain})", end=" ", flush=True)
                result = loop.run_until_complete(
                    evaluator.evaluate_dialogue(did, split=args.split, verbose=args.verbose)
                )
                all_results.append(result)
                domain_results[domain].append(result)
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
            "dataset": "RiSAWOZ", "algorithm": "Evolve", "split": args.split,
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
