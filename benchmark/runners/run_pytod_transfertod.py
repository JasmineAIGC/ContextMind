#!/usr/bin/env python3
"""
PyTOD 模式 - TransferTOD 数据集评测脚本

使用 TransferTOD 数据集测试 AdkPyTODTracker 的三步流程（AP → EE → DM）。

PyTOD 的评测指标不是槽位准确率，而是流程完整性：
  - 程序生成率（AP 生成了有效 PyTOD 程序的轮次占比）
  - 执行成功率（EE 执行无错误的轮次占比）
  - 回复生成率（DM 生成非空回复的轮次占比）
  - 全流程成功率（三步均成功的轮次占比）

由于 TransferTOD 没有预生成的 pytod_apis.py 文件，本评测使用存根模式（stub mode），
API 函数接受任意参数并返回成功标记，仅验证三步流程本身的完整性。

使用方式:
    python benchmark/runners/run_pytod_transfertod.py
    python benchmark/runners/run_pytod_transfertod.py --domain 酒店 --data-type clean --limit 5
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
from benchmark.algorithms.pytod import PyTODEvaluator
from contextmind.modes.pytod import AdkPyTODTracker
from contextmind.modes.pytod.schemas import ServiceSchema, SlotDefinition, IntentDefinition
from contextmind.modes.pytod.execution_engine import ExecutionEngine
from contextmind.modes.pytod.tracker import _register_apis_from_schema
from contextmind.infra.llm_client import AdkLLMClient
from contextmind.infra.logger import get_logger, setup_logging, LogLevel

logger = get_logger(__name__)


def _build_service_schema_from_transfertod(domain: str, schema: Dict) -> ServiceSchema:
    """将 TransferTOD schema 字典转换为 ServiceSchema 对象（供 PyTOD 使用）。

    由于 TransferTOD schema 没有意图层级，每个领域被视为单一意图，
    所有槽位均作为可选参数注册。
    """
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
        description=schema.get("description", f"{domain} 领域对话状态追踪"),
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


class TransferTODPyTODEvaluator:
    """TransferTOD 数据集上的 PyTOD 评测器。"""

    def __init__(
        self,
        data_root: str = "./data/TransferTOD",
        schemas_file: Optional[str] = None,
    ) -> None:
        self.adapter = TransferTODAdapter(data_root, schemas_file=schemas_file)
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
        service_schema = _build_service_schema_from_transfertod(domain, schema_dict)

        engine = ExecutionEngine()
        _register_apis_from_schema(engine, service_schema, replace_existing=True)

        self.tracker = AdkPyTODTracker(
            llm_client=self.llm_client,
            engine=engine,
            schema=service_schema,
            scenario_context=f"TransferTOD 数据集 {domain} 领域评测",
            top_k_intents=5,
        )
        logger.info(f"✅ PyTOD 追踪器初始化 - 领域: {domain}")

    async def evaluate_dialogue(
        self, dialogue_id: str, data_type: str = "clean", verbose: bool = False
    ) -> Dict[str, Any]:
        """对单个对话进行 PyTOD 评测。"""
        dialogue = self.adapter.load_dialogue(dialogue_id, data_type=data_type)
        scenario = f"{dialogue.domain}/{dialogue_id}"

        if verbose:
            print(f"\n{'=' * 60}")
            print(f"对话: {dialogue_id}  领域: {dialogue.domain}  轮次: {len(dialogue.turns)}")
            print("=" * 60)

        # 重置 tracker 状态（每个对话独立）
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
                    print(f"    program={program_text[:80]}  exec_ok={exec_success}  resp={response[:40]}")

            except Exception as exc:
                logger.error(f"轮次 {turn.turn_id} 失败: {exc}")
                # 失败轮次计为 exec_failed / no_response
                self.evaluator.add_turn(
                    program_text="",
                    exec_success=False,
                    response="",
                    scenario=scenario,
                )

        metrics = self.evaluator.calculate_metrics()
        return {
            "dialogue_id": dialogue_id,
            "domain": dialogue.domain,
            **metrics.to_dict(),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="PyTOD on TransferTOD 评测")
    parser.add_argument("--domain", type=str, default=None, help="指定测试领域")
    parser.add_argument("--data-type", type=str, default="clean", choices=["clean", "noise"])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--data-root", type=str, default="./data/TransferTOD")
    parser.add_argument("--schemas-file", type=str, default=None)
    parser.add_argument("--verbose", action="store_true", default=False)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    setup_logging(LogLevel.DEBUG if args.verbose else LogLevel.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)

    print(f"\n{'=' * 70}\n=== PyTOD on TransferTOD 评测 ===\n{'=' * 70}\n")

    evaluator = TransferTODPyTODEvaluator(data_root=args.data_root, schemas_file=args.schemas_file)

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

    all_metrics: List[Dict] = []
    domain_metrics: Dict[str, List[Dict]] = defaultdict(list)
    current_domain: Optional[str] = None

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        for idx, did in enumerate(dialogue_ids, 1):
            try:
                dlg = evaluator.adapter.load_dialogue(did, data_type=args.data_type)
                domain = dlg.domain
                if domain != current_domain:
                    current_domain = domain
                    print(f"\n切换领域: {current_domain}")
                    evaluator.setup_tracker(current_domain)

                print(f"[{idx}/{len(dialogue_ids)}] {did}", end=" ", flush=True)
                result = loop.run_until_complete(evaluator.evaluate_dialogue(did, data_type=args.data_type, verbose=args.verbose))
                all_metrics.append(result)
                domain_metrics[current_domain].append(result)
                fp_rate = result.get("full_pipeline", {}).get("rate", 0)
                print(f"✅ full_pipeline={fp_rate:.3f}")
            except Exception as exc:
                print(f"❌ {exc}")
    finally:
        loop.close()

    if not all_metrics:
        print("\n没有成功评测的对话")
        return

    def avg_nested(records: List[Dict], *keys: str) -> float:
        vals = [r.get(keys[0], {}).get(keys[1], 0) if len(keys) == 2 else r.get(keys[0], 0) for r in records]
        return sum(vals) / len(vals) if vals else 0.0

    print(f"\n{'=' * 70}\n=== 汇总 ({len(all_metrics)} 对话) ===")
    print(f"  程序生成率:  {avg_nested(all_metrics, 'action_parser', 'program_generation_rate') * 100:.2f}%")
    print(f"  执行成功率:  {avg_nested(all_metrics, 'execution_engine', 'execution_success_rate') * 100:.2f}%")
    print(f"  回复生成率:  {avg_nested(all_metrics, 'dialogue_manager', 'response_generation_rate') * 100:.2f}%")
    print(f"  全流程成功率: {avg_nested(all_metrics, 'full_pipeline', 'rate') * 100:.2f}%")

    if args.output:
        output_data = {
            "timestamp": datetime.datetime.now().isoformat(),
            "dataset": "TransferTOD", "algorithm": "PyTOD",
            "total_dialogues": len(all_metrics),
            "overall": {
                "program_generation_rate": avg_nested(all_metrics, "action_parser", "program_generation_rate"),
                "execution_success_rate": avg_nested(all_metrics, "execution_engine", "execution_success_rate"),
                "response_generation_rate": avg_nested(all_metrics, "dialogue_manager", "response_generation_rate"),
                "full_pipeline_rate": avg_nested(all_metrics, "full_pipeline", "rate"),
            },
            "per_dialogue": all_metrics,
        }
        Path(args.output).write_text(json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n📄 结果已保存至: {args.output}")


if __name__ == "__main__":
    main()
