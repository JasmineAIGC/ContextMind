"""
PyTOD (Program-execution TOD) 算法评测模块

评测 PyTOD 追踪器在任务型对话中的表现，指标对应三步流程：
  1. 动作解析器（Action Parser）— 程序生成准确率
  2. 执行引擎（Execution Engine）— API 执行成功率
  3. 对话管理器（Dialogue Manager）— 回复生成成功率

与 DST / FnCTOD 评测模块保持结构一致。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any


@dataclass
class PyTODMetrics:
    """PyTOD 评测指标。"""

    # 程序生成
    program_generation_rate: float = 0.0   # 生成了有效程序（非 NONE）的轮次占比
    # 执行成功
    execution_success_rate: float = 0.0    # 执行引擎成功（无错误）的轮次占比
    # 回复生成
    response_generation_rate: float = 0.0  # 生成了非空回复的轮次占比
    # 全流程：三步均成功
    full_pipeline_rate: float = 0.0

    total_turns: int = 0
    turns_with_program: int = 0
    turns_exec_success: int = 0
    turns_with_response: int = 0
    turns_full_pipeline: int = 0

    scenario_metrics: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_parser": {
                "program_generation_rate": round(self.program_generation_rate, 4),
            },
            "execution_engine": {
                "execution_success_rate": round(self.execution_success_rate, 4),
            },
            "dialogue_manager": {
                "response_generation_rate": round(self.response_generation_rate, 4),
            },
            "full_pipeline": {
                "rate": round(self.full_pipeline_rate, 4),
            },
            "statistics": {
                "total_turns": self.total_turns,
                "turns_with_program": self.turns_with_program,
                "turns_exec_success": self.turns_exec_success,
                "turns_with_response": self.turns_with_response,
                "turns_full_pipeline": self.turns_full_pipeline,
            },
            "scenario_breakdown": self.scenario_metrics,
        }


class PyTODEvaluator:
    """PyTOD 评测器。"""

    def __init__(self) -> None:
        self._records: List[Dict[str, Any]] = []

    def add_turn(
        self,
        program_text: str,
        exec_success: bool,
        response: str,
        scenario: str = "unknown",
    ) -> None:
        """
        记录一轮对话的评测数据。

        Args:
            program_text:  动作解析器生成的程序文本（空字符串或 "NONE()" 表示未生成）
            exec_success:  执行引擎是否成功（无报错）
            response:      对话管理器生成的回复文本（空字符串表示生成失败）
            scenario:      场景名称（用于按场景汇总指标）
        """
        has_program = bool(program_text and program_text.strip() and program_text.strip() != "NONE()")
        has_response = bool(response and response.strip())
        full_ok = has_program and exec_success and has_response
        self._records.append({
            "has_program": has_program,
            "exec_success": exec_success,
            "has_response": has_response,
            "full_ok": full_ok,
            "scenario": scenario,
        })

    def calculate_metrics(self) -> PyTODMetrics:
        """计算并返回聚合评测指标。"""
        if not self._records:
            return PyTODMetrics()

        total = len(self._records)
        n_prog = sum(1 for r in self._records if r["has_program"])
        n_exec = sum(1 for r in self._records if r["exec_success"])
        n_resp = sum(1 for r in self._records if r["has_response"])
        n_full = sum(1 for r in self._records if r["full_ok"])

        # Per-scenario breakdown
        scenario_stats: Dict[str, Dict[str, int]] = {}
        for r in self._records:
            s = r["scenario"]
            if s not in scenario_stats:
                scenario_stats[s] = {"total": 0, "prog": 0, "exec": 0, "resp": 0, "full": 0}
            scenario_stats[s]["total"] += 1
            if r["has_program"]:
                scenario_stats[s]["prog"] += 1
            if r["exec_success"]:
                scenario_stats[s]["exec"] += 1
            if r["has_response"]:
                scenario_stats[s]["resp"] += 1
            if r["full_ok"]:
                scenario_stats[s]["full"] += 1

        scenario_metrics: Dict[str, Dict[str, float]] = {}
        for s, st in scenario_stats.items():
            t = st["total"]
            scenario_metrics[s] = {
                "program_generation_rate": round(st["prog"] / t, 4) if t else 0.0,
                "execution_success_rate": round(st["exec"] / t, 4) if t else 0.0,
                "response_generation_rate": round(st["resp"] / t, 4) if t else 0.0,
                "full_pipeline_rate": round(st["full"] / t, 4) if t else 0.0,
                "total_turns": t,
            }

        return PyTODMetrics(
            program_generation_rate=n_prog / total,
            execution_success_rate=n_exec / total,
            response_generation_rate=n_resp / total,
            full_pipeline_rate=n_full / total,
            total_turns=total,
            turns_with_program=n_prog,
            turns_exec_success=n_exec,
            turns_with_response=n_resp,
            turns_full_pipeline=n_full,
            scenario_metrics=scenario_metrics,
        )

    def reset(self) -> None:
        """清空已记录的评测数据。"""
        self._records = []
