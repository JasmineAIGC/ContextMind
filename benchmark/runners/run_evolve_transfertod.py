#!/usr/bin/env python3
"""
Evolve 模式 - TransferTOD 数据集评测脚本

使用 TransferTOD 数据集测试 EvolveApplication 的上下文管理能力。

Evolve 的评测指标对应三个核心能力：
  - 记忆提取率（Knowledge Extraction Rate）：从对话中成功提取知识的轮次占比
  - 上下文利用率（Context Utilization Rate）：检索并注入长期记忆的轮次占比
  - 回复生成率（Response Generation Rate）：生成非空回复的轮次占比
  - 全流程成功率（Full Pipeline Rate）：三项均成功的轮次占比

使用方式:
    python benchmark/runners/run_evolve_transfertod.py
    python benchmark/runners/run_evolve_transfertod.py --domain 酒店 --data-type clean --limit 5
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

from benchmark.datasets.transfertod.adapter import TransferTODAdapter
from benchmark.algorithms.evolve import EvolveEvaluator
from contextmind.modes.evolve import EvolveEngine, EvolveApplication
from contextmind.infra.llm_client import AdkLLMClient
from contextmind.infra.logger import get_logger, setup_logging, LogLevel

logger = get_logger(__name__)

# 最小相关度阈值：超过此值的检索项被视为"已利用"
RELEVANCE_THRESHOLD = 0.3


def _create_app(llm_client: AdkLLMClient, domain: str, dialogue_id: str) -> EvolveApplication:
    """为单个对话评测创建独立的 EvolveApplication 实例。

    每个对话使用独立的 EvolveEngine（独立记忆库），避免跨对话知识污染。
    """
    engine = EvolveEngine(
        app_name=f"benchmark_evolve_{domain}",
        user_id=f"benchmark_{dialogue_id}",
        llm_client=llm_client,
    )
    system_prompt = (
        f"你是一个任务型对话助手，专门处理 {domain} 领域的对话。"
        f"请从对话中准确提取用户意图和相关信息，并给出简洁的回复。"
    )
    return EvolveApplication(
        evolve_engine=engine,
        system_prompt=system_prompt,
        llm_client=llm_client,
    )


class TransferTODEvolveEvaluator:
    """TransferTOD 数据集上的 Evolve 评测器。"""

    def __init__(
        self,
        data_root: str = "./data/TransferTOD",
        schemas_file: Optional[str] = None,
    ) -> None:
        self.adapter = TransferTODAdapter(data_root, schemas_file=schemas_file)
        self.llm_client: Optional[AdkLLMClient] = None
        self.evaluator = EvolveEvaluator()

    def setup(self) -> None:
        """初始化 LLM 客户端。"""
        try:
            self.llm_client = AdkLLMClient()
            logger.info("✅ LLM 客户端初始化成功")
        except Exception as e:
            logger.error(f"❌ LLM 客户端初始化失败: {e}")
            raise

    async def evaluate_dialogue(
        self, dialogue_id: str, data_type: str = "clean", verbose: bool = False
    ) -> Dict[str, Any]:
        """对单个对话进行 Evolve 评测。"""
        dialogue = self.adapter.load_dialogue(dialogue_id, data_type=data_type)
        scenario = f"{dialogue.domain}/{dialogue_id}"

        app = _create_app(self.llm_client, dialogue.domain, dialogue_id)
        self.evaluator.reset()

        if verbose:
            print(f"\n{'=' * 60}")
            print(f"对话: {dialogue_id}  领域: {dialogue.domain}  轮次: {len(dialogue.turns)}")
            print("=" * 60)

        prior_memory_count = 0

        for turn in dialogue.turns:
            user_utt = turn.user_utterance
            try:
                # 获取记忆库处理前的知识数量
                mem_before = len(app.evolve_engine.memory_bank.get_memory_cache())

                # 处理轮次（debug=True 以获取构建的 prompt 内容）
                response, debug_info = await app.process_turn(user_utt, debug=True)

                # 1. 上下文利用率：检查 prompt 中是否包含长期记忆片段
                prompt_text = debug_info.get("prompt", "")
                has_context = "## 已知信息" in prompt_text

                # 2. 主动触发知识提取（benchmark 中同步执行）
                await app.evolve_engine.extract_knowledge(auto_store=True)
                mem_after = len(app.evolve_engine.memory_bank.get_memory_cache())

                # 3. 知识提取：本轮提取到了新知识
                new_knowledge = mem_after - mem_before
                has_extraction = new_knowledge > 0

                # 4. 回复生成：非空回复
                has_response = bool(response and str(response).strip())

                self.evaluator.add_turn(
                    extracted_knowledge_count=new_knowledge,
                    context_items_used=1 if has_context else 0,
                    response=str(response) if response else "",
                    scenario=scenario,
                )

                if verbose:
                    print(f"  T{turn.turn_id}: {user_utt[:50]}...")
                    print(f"    extract={has_extraction}  ctx={has_context}  resp={has_response}")
                    print(f"    回复: {str(response)[:60]}")

            except Exception as exc:
                logger.error(f"轮次 {turn.turn_id} 失败: {exc}")
                self.evaluator.add_turn(0, 0, "", scenario)

        metrics = self.evaluator.calculate_metrics()
        return {"dialogue_id": dialogue_id, "domain": dialogue.domain, **metrics.to_dict()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evolve on TransferTOD 评测")
    parser.add_argument("--domain", type=str, default=None)
    parser.add_argument("--data-type", type=str, default="clean", choices=["clean", "noise"])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--data-root", type=str, default="./data/TransferTOD")
    parser.add_argument("--schemas-file", type=str, default=None)
    parser.add_argument("--verbose", action="store_true", default=False)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    setup_logging(LogLevel.DEBUG if args.verbose else LogLevel.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)

    print(f"\n{'=' * 70}\n=== Evolve on TransferTOD 评测 ===\n{'=' * 70}\n")

    evaluator = TransferTODEvolveEvaluator(data_root=args.data_root, schemas_file=args.schemas_file)
    try:
        evaluator.setup()
    except Exception as exc:
        print(f"❌ LLM 客户端初始化失败: {exc}")
        return

    try:
        dialogue_ids = evaluator.adapter.get_dialogues_by_domain(args.domain, args.data_type)
    except Exception as exc:
        print(f"❌ 加载数据集失败: {exc}")
        return

    if not dialogue_ids:
        print("未找到对话数据")
        return
    if args.limit:
        dialogue_ids = dialogue_ids[: args.limit]

    print(f"共 {len(dialogue_ids)} 个对话实例")

    all_results: List[Dict] = []
    domain_results: Dict[str, List[Dict]] = defaultdict(list)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        for idx, did in enumerate(dialogue_ids, 1):
            try:
                dlg = evaluator.adapter.load_dialogue(did, data_type=args.data_type)
                domain = dlg.domain
                print(f"[{idx}/{len(dialogue_ids)}] {did} ({domain})", end=" ", flush=True)
                result = loop.run_until_complete(evaluator.evaluate_dialogue(did, data_type=args.data_type, verbose=args.verbose))
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
            "dataset": "TransferTOD", "algorithm": "Evolve",
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
