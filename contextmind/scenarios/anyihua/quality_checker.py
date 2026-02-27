"""
安逸花外呼促活场景 · PyTOD 批量质检器

对 chat_test_100.json 中的会话执行批量质检，由 LLM 直接完成五分类判断。
所有检测均通过 LLM 调用完成，不使用任何规则。

五个质量标签：
    - 数据错误：坐席引用金额与用户实际信息不符（偏差 > 300 元）
    - 重复询问：坐席回复与历史发言高度重复
    - 不当告别：用户有未解决问题时坐席执行告别话术
    - 答非所问：用户明确提问但坐席回复完全无关
    - 无标签命中：不存在上述任何质量问题

基于 docs/analysis/pytod-on-chat-test-100.md §6 实现。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any, Dict, List, Optional

from .detectors import detect_session_llm


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

    所有检测均由 LLM 完成（无规则）。需传入已初始化的 llm_client。

    使用示例::

        import json
        from contextmind.infra.llm_client import SimpleLLMClient, LLMConfig

        with open("resources/data/chat_test_100.json") as f:
            data = json.load(f)

        config = LLMConfig.from_env()
        llm = SimpleLLMClient(config)
        checker = PyTODQualityChecker()

        # 单条检测
        pred = checker.check(data[0], llm_client=llm)
        print(pred)  # {"label": "不当告别", "reason": "...", "confidence": 0.85}

        # 批量检测（含 P/R/F1 报告）
        results = checker.run_batch(data, llm_client=llm)
        print(f"总体准确率: {results['accuracy']:.1%}")
    """

    def check(
        self,
        session: Dict[str, Any],
        use_full_history: bool = False,
        llm_client: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        对单条会话调用 LLM 进行质量分类。

        参数:
            session:          单条 chat_test_100.json 记录
            use_full_history: True 时将完整对话历史送入 LLM；
                              False（默认）时仅发送最近 10 轮（节省 token）
            llm_client:       LLMClient 实例（必须提供，不支持纯规则模式）

        返回:
            包含以下键的字典::

                {
                    "label":      str,    # 预测标签
                    "reason":     str,    # LLM 给出的判断理由
                    "confidence": float,  # 置信度估计
                }

        异常:
            ValueError: llm_client 未提供时抛出
        """
        if llm_client is None:
            raise ValueError(
                "llm_client 是必须参数。所有检测均基于 LLM，"
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
        }

    def run_batch(
        self,
        data: List[Dict[str, Any]],
        verbose: bool = False,
        use_full_history: bool = False,
        llm_client: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        批量质检并计算与人工校验的一致性。

        参数:
            data:             chat_test_100.json 数据列表
            verbose:          True 则逐条打印预测错误的会话信息
            use_full_history: 传递给 check() 的同名参数（默认 False）
            llm_client:       LLMClient 实例（必须提供）

        返回:
            包含以下键的字典::

                {
                    "predictions": list,   # 每条预测结果
                    "accuracy":    float,  # 总体准确率
                    "by_label":    dict,   # 各标签的 TP/FP/FN 及 P/R/F1
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
        }
