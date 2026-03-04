"""
Evolve (进化式上下文优化) 算法评测模块

评测 EvolveEngine 在对话中的上下文管理表现，指标对应三个核心能力：
  1. 记忆提取（Memory Extraction）— 从对话中提取有效知识的成功率
  2. 上下文利用（Context Utilization）— 检索并注入长期记忆的成功率
  3. 回复生成（Response Generation）— 最终生成非空回复的成功率

与 DST / FnCTOD / PyTOD 评测模块保持结构一致。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any


@dataclass
class EvolveMetrics:
    """Evolve 算法评测指标。"""

    # 记忆提取：从对话轮次中成功提取到知识的占比
    memory_extraction_rate: float = 0.0
    # 上下文利用：成功检索并注入了长期记忆的轮次占比
    context_utilization_rate: float = 0.0
    # 回复生成：生成了非空回复的轮次占比
    response_generation_rate: float = 0.0
    # 全流程：三项能力均成功的轮次占比
    full_pipeline_rate: float = 0.0

    total_turns: int = 0
    turns_with_extraction: int = 0
    turns_with_context: int = 0
    turns_with_response: int = 0
    turns_full_pipeline: int = 0

    scenario_metrics: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_extraction": {
                "memory_extraction_rate": round(self.memory_extraction_rate, 4),
            },
            "context_utilization": {
                "context_utilization_rate": round(self.context_utilization_rate, 4),
            },
            "response_generation": {
                "response_generation_rate": round(self.response_generation_rate, 4),
            },
            "full_pipeline": {
                "rate": round(self.full_pipeline_rate, 4),
            },
            "statistics": {
                "total_turns": self.total_turns,
                "turns_with_extraction": self.turns_with_extraction,
                "turns_with_context": self.turns_with_context,
                "turns_with_response": self.turns_with_response,
                "turns_full_pipeline": self.turns_full_pipeline,
            },
            "scenario_breakdown": self.scenario_metrics,
        }


class EvolveEvaluator:
    """Evolve 算法评测器。"""

    def __init__(self) -> None:
        self._records: List[Dict[str, Any]] = []

    def add_turn(
        self,
        extracted_knowledge_count: int,
        context_items_used: int,
        response: str,
        scenario: str = "unknown",
    ) -> None:
        """
        记录一轮对话的评测数据。

        Args:
            extracted_knowledge_count: 本轮从对话中提取到的知识条目数（0 表示提取失败/无内容）
            context_items_used:        本轮注入的上下文条目数（0 表示未使用长期记忆）
            response:                  最终生成的回复文本（空字符串表示生成失败）
            scenario:                  场景名称（用于按场景汇总指标）
        """
        has_extraction = extracted_knowledge_count > 0
        has_context = context_items_used > 0
        has_response = bool(response and response.strip())
        full_ok = has_extraction and has_context and has_response
        self._records.append({
            "has_extraction": has_extraction,
            "has_context": has_context,
            "has_response": has_response,
            "full_ok": full_ok,
            "scenario": scenario,
        })

    def calculate_metrics(self) -> EvolveMetrics:
        """计算并返回聚合评测指标。"""
        if not self._records:
            return EvolveMetrics()

        total = len(self._records)
        n_ext = sum(1 for r in self._records if r["has_extraction"])
        n_ctx = sum(1 for r in self._records if r["has_context"])
        n_resp = sum(1 for r in self._records if r["has_response"])
        n_full = sum(1 for r in self._records if r["full_ok"])

        # Per-scenario breakdown
        scenario_stats: Dict[str, Dict[str, int]] = {}
        for r in self._records:
            s = r["scenario"]
            if s not in scenario_stats:
                scenario_stats[s] = {"total": 0, "ext": 0, "ctx": 0, "resp": 0, "full": 0}
            scenario_stats[s]["total"] += 1
            if r["has_extraction"]:
                scenario_stats[s]["ext"] += 1
            if r["has_context"]:
                scenario_stats[s]["ctx"] += 1
            if r["has_response"]:
                scenario_stats[s]["resp"] += 1
            if r["full_ok"]:
                scenario_stats[s]["full"] += 1

        scenario_metrics: Dict[str, Dict[str, float]] = {}
        for s, st in scenario_stats.items():
            t = st["total"]
            scenario_metrics[s] = {
                "memory_extraction_rate": round(st["ext"] / t, 4) if t else 0.0,
                "context_utilization_rate": round(st["ctx"] / t, 4) if t else 0.0,
                "response_generation_rate": round(st["resp"] / t, 4) if t else 0.0,
                "full_pipeline_rate": round(st["full"] / t, 4) if t else 0.0,
                "total_turns": t,
            }

        return EvolveMetrics(
            memory_extraction_rate=n_ext / total,
            context_utilization_rate=n_ctx / total,
            response_generation_rate=n_resp / total,
            full_pipeline_rate=n_full / total,
            total_turns=total,
            turns_with_extraction=n_ext,
            turns_with_context=n_ctx,
            turns_with_response=n_resp,
            turns_full_pipeline=n_full,
            scenario_metrics=scenario_metrics,
        )

    def reset(self) -> None:
        """清空已记录的评测数据。"""
        self._records = []
