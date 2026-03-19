#!/usr/bin/env python3
"""
PyTOD 模式 - 安逸花外呼数据集评测脚本

基于 data/anyihua_sgd/schema.json 中提取的 SGD 格式 schema，
在 resources/data/chat_test_100.json（安逸花外呼数据）上运行 PyTOD 算法，
评测三步流水线（动作解析器 → 执行引擎 → 对话管理器）的整体性能。

使用方式:
    python benchmark/runners/run_pytod_anyihua.py
    python benchmark/runners/run_pytod_anyihua.py --limit 10
    python benchmark/runners/run_pytod_anyihua.py --limit 5 --verbose
    python benchmark/runners/run_pytod_anyihua.py --output /tmp/results.json

评测指标:
    - program_generation_rate  : 动作解析器成功生成有效程序的轮次占比
    - execution_success_rate   : 执行引擎无错误执行的轮次占比
    - response_generation_rate : 对话管理器成功生成非空回复的轮次占比
    - full_pipeline_rate       : 三步均成功的轮次占比
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.algorithms.pytod import PyTODEvaluator
from benchmark.datasets.anyihua.adapter import AnyihuaSGDAdapter, AnyihuaDialogue
from contextmind.modes.pytod import (
    ExecutionEngine,
    AdkPyTODTracker,
    ServiceSchema,
    load_schema_from_dict,
)
from contextmind.scenarios.anyihua.generation.engine import build_generation_engine
from contextmind.scenarios.anyihua.generation.schema import ANYIHUA_SCHEMA
from contextmind.infra.llm_client import AdkLLMClient
from contextmind.infra.logger import get_logger, setup_logging, LogLevel

logger = get_logger(__name__)

# 说话人标签（与 adapter.py 对齐）
_SPEAKER_USER = "用户"
_SPEAKER_AGENT = "坐席"

# 安逸花外呼场景描述（注入到 Action Parser / Dialogue Manager 系统提示）
_SCENARIO_CONTEXT = (
    "这是一个外呼小额借款推介场景（安逸花外呼促活）。"
    "坐席代表安逸花/马上消费金融主动致电老用户，目标是激活用户闲置的借款额度。"
    "标准流程：① 核实用户身份（姓名/手机尾号）→ ② 告知可用额度和利率 → "
    "③ 解答疑问（还款方式、账单争议等）→ ④ 引导用户在 APP 完成借款操作 → "
    "⑤ 确认无未解决诉求后礼貌告别。"
    "注意：核实身份前不得告知账户详细信息；若用户有未解决诉求则不得直接告别。"
)

# 动作解析器"无需调用 API"时输出的固定标记
_NONE_PROGRAM = "NONE()"


class AnyihuaPyTODEvaluator:
    """
    安逸花数据集上的 PyTOD 评测器。

    加载 data/anyihua_sgd/schema.json 作为 ServiceSchema，
    在 resources/data/chat_test_100.json 上逐轮运行 PyTOD 三步流水线，
    并通过 PyTODEvaluator 汇总指标。
    """

    def __init__(
        self,
        data_root: str = str(PROJECT_ROOT),
        schema_path: str = "data/anyihua_sgd/schema.json",
        dialogues_path: str = "resources/data/chat_test_100.json",
    ) -> None:
        """
        初始化评测器。

        Args:
            data_root:      项目根目录
            schema_path:    SGD schema 文件相对路径
            dialogues_path: 对话数据文件相对路径
        """
        self.adapter = AnyihuaSGDAdapter(
            data_root=data_root,
            schema_path=schema_path,
            dialogues_path=dialogues_path,
        )
        self.evaluator = PyTODEvaluator()
        self._service_schema: Optional[ServiceSchema] = None

    def setup(self) -> None:
        """加载 schema（ADK 配置由 LLMConfig.from_env() 自动加载）。"""
        # 从 data/anyihua_sgd/schema.json 加载 ServiceSchema
        schema_raw = self.adapter.load_schema()
        self._service_schema = load_schema_from_dict(schema_raw)
        logger.info(
            f"✅ Schema 加载完成: {self._service_schema.service_name} "
            f"(意图数: {len(self._service_schema.intents)}, "
            f"槽位数: {len(self._service_schema.slots)})"
        )

    def _build_tracker(self, dialogue: AnyihuaDialogue) -> AdkPyTODTracker:
        """为单条对话构建 AdkPyTODTracker（每条对话使用独立的 ExecutionEngine）。"""
        engine = build_generation_engine(dialogue.raw_session)
        return AdkPyTODTracker(
            engine=engine,
            scenario_context=_SCENARIO_CONTEXT,
        )

    async def evaluate_dialogue(
        self,
        dialogue: AnyihuaDialogue,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """
        对单条对话运行 PyTOD 评测。

        仅处理用户侧轮次（"用户："开头），跳过纯坐席话轮。
        每轮记录：
          - program_text  ：动作解析器生成的程序
          - exec_success  ：执行引擎是否成功
          - response      ：对话管理器生成的回复

        Args:
            dialogue: 待评测对话
            verbose:  是否打印逐轮详情

        Returns:
            包含本条对话各轮次结果的字典
        """
        tracker = self._build_tracker(dialogue)
        results = []
        prev_agent_utt = ""

        for turn in dialogue.turns:
            if turn.speaker != _SPEAKER_USER:
                # 记录坐席话轮供下轮调用时传入 system_utterance
                prev_agent_utt = turn.utterance
                continue

            try:
                result = await tracker.process_turn(
                    user_utterance=turn.utterance,
                    system_utterance=prev_agent_utt,
                )
                program_text = result.get("program_text", "")
                response = result.get("response", "")
                exec_ok = (
                    result.get("execution") is not None
                    and result["execution"].success
                ) if program_text and program_text.strip() != _NONE_PROGRAM else True

                self.evaluator.add_turn(
                    program_text=program_text,
                    exec_success=exec_ok,
                    response=response,
                    scenario="anyihua_outbound",
                )
                results.append({
                    "turn_idx": turn.turn_idx,
                    "user_utterance": turn.utterance,
                    "program_text": program_text,
                    "exec_success": exec_ok,
                    "response": response,
                })
                if verbose:
                    print(f"  [轮 {turn.turn_idx}] 用户: {turn.utterance[:60]}")
                    print(f"           程序: {program_text[:80]}")
                    print(f"           回复: {response[:80]}")
            except Exception as exc:
                logger.warning(f"对话 {dialogue.session_id} 第 {turn.turn_idx} 轮处理失败: {exc}")
                self.evaluator.add_turn(
                    program_text="",
                    exec_success=False,
                    response="",
                    scenario="anyihua_outbound",
                )

        return {
            "session_id": dialogue.session_id,
            "turn_results": results,
        }

    async def run(
        self,
        limit: int = -1,
        verbose: bool = False,
        output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        在安逸花数据集上运行完整 PyTOD 评测。

        Args:
            limit:       最大评测对话数，-1 表示全部
            verbose:     是否打印逐轮详情
            output_path: 若指定，将结果 JSON 写入此路径

        Returns:
            包含整体和按场景分组指标的字典
        """
        self.setup()
        dialogues = self.adapter.load_dialogues(limit=limit)
        logger.info(f"📂 加载对话数: {len(dialogues)}")

        all_dialogue_results: List[Dict[str, Any]] = []
        for i, dlg in enumerate(dialogues):
            logger.info(f"[{i+1}/{len(dialogues)}] 处理对话 {dlg.session_id}...")
            if verbose:
                print(f"\n{'─'*60}")
                print(f"对话 {i+1}/{len(dialogues)}  ID: {dlg.session_id}")
                print(f"用户轮次数: {len(dlg.user_turns)}")
            dlg_result = await self.evaluate_dialogue(dlg, verbose=verbose)
            all_dialogue_results.append(dlg_result)

        metrics = self.evaluator.calculate_metrics()
        metrics_dict = metrics.to_dict()

        report = {
            "dataset": "anyihua_outbound (chat_test_100.json)",
            "schema": "data/anyihua_sgd/schema.json",
            "dialogues_evaluated": len(dialogues),
            "metrics": metrics_dict,
            "dialogue_results": all_dialogue_results,
        }

        if output_path:
            Path(output_path).write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            logger.info(f"✅ 结果已写入: {output_path}")

        return report


def _print_metrics(report: Dict[str, Any]) -> None:
    """以对齐格式打印评测结果。"""
    metrics = report["metrics"]
    n = report["dialogues_evaluated"]
    stats = metrics.get("statistics", {})

    print(f"\n{'='*60}")
    print(f"  PyTOD 评测结果 — 安逸花外呼数据集")
    print(f"{'='*60}")
    print(f"  数据集  : {report['dataset']}")
    print(f"  Schema  : {report['schema']}")
    print(f"  对话数  : {n}")
    print(f"  总轮次  : {stats.get('total_turns', 0)}")
    print(f"{'─'*60}")
    print(f"  动作解析器（程序生成率）: "
          f"{metrics['action_parser']['program_generation_rate']:.2%}")
    print(f"  执行引擎（执行成功率）  : "
          f"{metrics['execution_engine']['execution_success_rate']:.2%}")
    print(f"  对话管理器（回复生成率）: "
          f"{metrics['dialogue_manager']['response_generation_rate']:.2%}")
    print(f"  全流程成功率            : "
          f"{metrics['full_pipeline']['rate']:.2%}")
    print(f"{'='*60}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PyTOD 算法在安逸花外呼数据集上的评测脚本"
    )
    parser.add_argument(
        "--limit", type=int, default=-1,
        help="最大评测对话数，-1 表示全部（默认 -1）",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="打印逐轮详情",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="结果 JSON 输出路径（可选）",
    )
    parser.add_argument(
        "--data-root", type=str, default=str(PROJECT_ROOT),
        help=f"项目根目录（默认: {PROJECT_ROOT}）",
    )
    parser.add_argument(
        "--schema", type=str, default="data/anyihua_sgd/schema.json",
        help="SGD schema 文件路径（相对于 data-root）",
    )
    parser.add_argument(
        "--dialogues", type=str, default="resources/data/chat_test_100.json",
        help="对话数据文件路径（相对于 data-root）",
    )
    return parser.parse_args()


async def async_main() -> None:
    setup_logging(LogLevel.INFO)
    args = parse_args()

    ev = AnyihuaPyTODEvaluator(
        data_root=args.data_root,
        schema_path=args.schema,
        dialogues_path=args.dialogues,
    )

    print(f"\n{'='*60}")
    print("  PyTOD 算法 × 安逸花外呼数据集  评测启动")
    print(f"{'='*60}")
    print(f"  Schema  : {args.schema}")
    print(f"  数据集  : {args.dialogues}")
    print(f"  对话数  : {'全部' if args.limit < 0 else args.limit}")
    print(f"{'='*60}\n")

    report = await ev.run(
        limit=args.limit,
        verbose=args.verbose,
        output_path=args.output,
    )
    _print_metrics(report)


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
