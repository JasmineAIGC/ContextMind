"""
安逸花外呼促活场景 · PyTOD 批量质检器

对 chat_test_100.json 中的会话执行批量质检，支持两种模式：

模式 1（默认）：纯 LLM 质检
    所有检测均通过 LLM 调用完成，PyTOD ExecutionEngine 提供预分析 hint。

模式 2：Hybrid（PyTOD 优先，LLM 兜底）— use_pytod_first=True
    对于数据错误和重复询问（机械性错误）先尝试纯规则预测；
    若规则无法判断，再交由 LLM 处理。
    实测：约 32% 会话可无 LLM 直接给出答案（精度 81%），节省 token 开销。

五个质量标签：
    - 数据错误：坐席引用金额与用户实际信息不符（偏差 > 300 元）
    - 重复询问：坐席回复与历史发言高度重复
    - 不当告别：用户有未解决问题时坐席执行告别话术
    - 答非所问：用户明确提问但坐席回复完全无关
    - 无标签命中：不存在上述任何质量问题

基于 docs/analysis/pytod-on-chat-test-100.md §6 和 §8 实现。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any, Dict, List, Optional

from .detectors import detect_session_llm, predict_label_pytod


# 各标签的置信度估计（固定值，LLM 结果不附带置信度）
_LABEL_CONFIDENCE: Dict[str, float] = {
    "数据错误": 0.85,
    "重复询问": 0.85,
    "不当告别": 0.85,
    "答非所问": 0.80,
    "无标签命中": 0.75,
}


class PyTODQualityChecker:
    """
    安逸花外呼对话 PyTOD 批量质检器

    支持两种检测模式：
    - 纯 LLM 模式（默认）：所有检测均由 LLM 完成；
      PyTOD ExecutionEngine 提供结构化 hint 注入 prompt。
    - Hybrid 模式（use_pytod_first=True）：
      先由 predict_label_pytod() 尝试纯规则判断（无 LLM）；
      规则无法判断时再调用 LLM；节省约 32% token 开销。

    使用示例::

        import json
        from contextmind.infra.llm_client import SimpleLLMClient, LLMConfig

        with open("resources/data/chat_test_100.json") as f:
            data = json.load(f)

        config = LLMConfig.from_env()
        llm = SimpleLLMClient(config)
        checker = PyTODQualityChecker()

        # 单条检测（纯 LLM 模式）
        pred = checker.check(data[0], llm_client=llm)
        print(pred)  # {"label": "不当告别", "reason": "...", "confidence": 0.85}

        # 单条检测（Hybrid 模式：PyTOD 优先，LLM 兜底）
        pred = checker.check(data[0], llm_client=llm, use_pytod_first=True)
        print(pred)  # {"label": "重复询问", "reason": "...", "confidence": 0.87, "source": "pytod"}

        # 批量检测（含 P/R/F1 报告）
        results = checker.run_batch(data, llm_client=llm)
        print(f"总体准确率: {results['accuracy']:.1%}")
    """

    def check(
        self,
        session: Dict[str, Any],
        use_full_history: bool = False,
        llm_client: Optional[Any] = None,
        use_pytod_first: bool = False,
    ) -> Dict[str, Any]:
        """
        对单条会话进行质量分类，支持纯 LLM 模式或 Hybrid 模式。

        参数:
            session:           单条 chat_test_100.json 记录
            use_full_history:  True 时将完整对话历史送入 LLM（默认 False）
            llm_client:        LLMClient 实例；use_pytod_first=True 时为可选，
                               规则无法判断的会话仍需 LLMClient
            use_pytod_first:   True 时启用 Hybrid 模式：
                               优先尝试 predict_label_pytod() 纯规则预测；
                               规则无法判断时再调用 LLM。
                               实测可节省约 32% LLM 调用（以 81% 精度）。

        返回:
            包含以下键的字典::

                {
                    "label":      str,    # 预测标签
                    "reason":     str,    # 判断理由
                    "confidence": float,  # 置信度（规则命中时为 0.87，LLM 时为 0.75~0.85）
                    "source":     str,    # "pytod"（规则预测）或 "llm"（LLM 预测）
                }

        异常:
            ValueError: use_pytod_first=False 且 llm_client 未提供时抛出
        """
        # ------------------------------------------------------------------ #
        # Hybrid 模式：PyTOD 规则优先
        # ------------------------------------------------------------------ #
        if use_pytod_first:
            label, confidence, reason = predict_label_pytod(session)
            if label is not None:
                return {
                    "label": label,
                    "reason": reason,
                    "confidence": confidence,
                    "source": "pytod",
                }
            # 规则无法判断：fall back to LLM

        # ------------------------------------------------------------------ #
        # LLM 模式
        # ------------------------------------------------------------------ #
        if llm_client is None:
            raise ValueError(
                "规则无法判断该会话，需要 LLM 处理，"
                "请传入已初始化的 LLMClient 实例（如 SimpleLLMClient）。"
            )

        try:
            # 检测是否已在运行中的事件循环内
            asyncio.get_running_loop()
            # 已在事件循环中，使用独立线程执行以避免嵌套 asyncio.run
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    asyncio.run,
                    detect_session_llm(session, llm_client, use_full_history),
                )
                label, reason = future.result()
        except RuntimeError:
            # 没有运行中的事件循环，直接使用 asyncio.run
            label, reason = asyncio.run(
                detect_session_llm(session, llm_client, use_full_history)
            )

        return {
            "label": label,
            "reason": reason,
            "confidence": _LABEL_CONFIDENCE.get(label, 0.75),
            "source": "llm",
        }

    def run_batch(
        self,
        data: List[Dict[str, Any]],
        verbose: bool = False,
        use_full_history: bool = False,
        llm_client: Optional[Any] = None,
        use_pytod_first: bool = False,
    ) -> Dict[str, Any]:
        """
        批量质检并计算与人工校验的一致性。

        参数:
            data:              chat_test_100.json 数据列表
            verbose:           True 则逐条打印预测错误的会话信息
            use_full_history:  传递给 check() 的同名参数（默认 False）
            llm_client:        LLMClient 实例（use_pytod_first=False 时必须提供）
            use_pytod_first:   True 时启用 Hybrid 模式（见 check() 参数说明）

        返回:
            包含以下键的字典::

                {
                    "predictions": list,          # 每条预测结果
                    "accuracy":    float,          # 总体准确率
                    "by_label":    dict,           # 各标签的 TP/FP/FN 及 P/R/F1
                    "pytod_rate":  float,          # Hybrid 模式下规则预测比例
                }
        """
        predictions: List[Dict[str, Any]] = []
        correct = 0
        by_label: Dict[str, Dict[str, int]] = {}

        for session in data:
            pred = self.check(
                session,
                use_full_history=use_full_history,
                llm_client=llm_client,
                use_pytod_first=use_pytod_first,
            )
            gold = session.get("人工校验", "")

            pred["session_id"] = session["session_id"]
            pred["gold_label"] = gold
            pred["correct"] = pred["label"] == gold

            if pred["correct"]:
                correct += 1
            predictions.append(pred)

            if verbose and not pred["correct"]:
                sid = session["session_id"][-8:]
                print(f"❌ {sid} | 预测: {pred['label']} | 实际: {gold}")
                print(f"   原因: {pred['reason']}")

        accuracy = correct / len(data) if data else 0.0
        pytod_count = sum(1 for p in predictions if p.get("source") == "pytod")
        pytod_rate = pytod_count / len(data) if data else 0.0

        # 统计各标签的 TP / FP / FN
        for pred in predictions:
            gold = pred["gold_label"]
            predicted = pred["label"]
            for lbl in {gold, predicted}:
                if lbl not in by_label:
                    by_label[lbl] = {"TP": 0, "FP": 0, "FN": 0}
            if gold == predicted:
                by_label[gold]["TP"] += 1
            else:
                by_label[gold]["FN"] += 1
                by_label[predicted]["FP"] += 1

        # 打印摘要
        print(f"\n总体准确率: {accuracy:.1%} ({correct}/{len(data)})")
        if pytod_count > 0:
            pytod_correct = sum(
                1 for p in predictions if p.get("source") == "pytod" and p["correct"]
            )
            print(
                f"PyTOD 规则预测: {pytod_count}/{len(data)} 条（{pytod_rate:.0%}），"
                f"其中正确 {pytod_correct}/{pytod_count}（精度 {pytod_correct/pytod_count:.0%}）"
            )
        print("\n各标签统计:")
        for label, stats in by_label.items():
            tp = stats["TP"]
            fp = stats["FP"]
            fn = stats["FN"]
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = (
                2 * precision * recall / (precision + recall)
                if (precision + recall) > 0
                else 0.0
            )
            print(f"  {label}: P={precision:.0%} R={recall:.0%} F1={f1:.0%}")
            by_label[label]["precision"] = round(precision, 4)
            by_label[label]["recall"] = round(recall, 4)
            by_label[label]["f1"] = round(f1, 4)

        return {
            "predictions": predictions,
            "accuracy": accuracy,
            "by_label": by_label,
            "pytod_rate": pytod_rate,
        }
