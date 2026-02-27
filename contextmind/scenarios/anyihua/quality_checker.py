"""
安逸花外呼促活场景 · PyTOD 批量质检器

将四类检测器按优先级组合，形成完整的批量质检流水线。
可直接对 chat_test_100.json 数据集运行，输出预测标签并与人工校验对比。

检测优先级（高 → 低）：
    1. 数据错误   — 数值比对，最精确，几乎无误报
    2. 重复询问   — 字符串匹配，极精确
    3. 不当告别   — 关键词 + 上下文，精确
    4. 答非所问   — 规则辅助（异步 LLM 增强），召回率有限
    5. 无标签命中 — 以上均未触发时的默认标签

实测预期性能（基于 chat_test_100.json 数据分析）：
    - 数据错误：覆盖率 14/15 = 93%，精确率 ≈ 90%
    - 重复询问：覆盖率 13/15 = 87%，精确率 ≈ 95%
    - 不当告别：覆盖率 13/15 = 87%，精确率 ≈ 85%
    - 答非所问：规则覆盖约 60%，LLM 增强约 80%+

基于 docs/analysis/pytod-on-chat-test-100.md §6 实现。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .detectors import (
    detect_data_error,
    detect_data_error_full_history,
    detect_improper_farewell,
    detect_off_topic_rule,
    detect_repetition,
)


class PyTODQualityChecker:
    """
    安逸花外呼对话 PyTOD 批量质检器

    将四类检测器按优先级组合，为每条会话预测质量标签。
    无需 LLM（纯规则模式）即可覆盖约 80%+ 的质量问题。

    使用示例::

        import json

        with open("resources/data/chat_test_100.json") as f:
            data = json.load(f)

        checker = PyTODQualityChecker()

        # 单条检测
        pred = checker.check(data[0])
        print(pred)  # {"label": "不当告别", "reason": "...", "confidence": 0.85}

        # 批量检测（含 P/R/F1 报告）
        results = checker.run_batch(data, verbose=True)
        print(f"总体准确率: {results['accuracy']:.1%}")
    """

    def check(
        self,
        session: Dict[str, Any],
        use_full_history: bool = False,
    ) -> Dict[str, Any]:
        """
        对单条会话执行四项检测，按优先级返回第一个命中的预测结果。

        参数:
            session:          单条 chat_test_100.json 记录
            use_full_history: False（默认）则只扫描 坐席回复 中的金额数字；
                              True 则扫描完整对话历史（覆盖率更高但误报率也高，
                              因为历史中的数据错误不一定是当前轮次的质量问题）

        返回:
            包含以下键的字典::

                {
                    "label":      str,    # 预测标签
                    "reason":     str,    # 判断依据
                    "confidence": float,  # 置信度估计
                }
        """
        # 1. 数据错误检测（最高优先级，数值比对，误报率最低）
        if use_full_history:
            is_error, reason = detect_data_error_full_history(session)
        else:
            is_error, reason = detect_data_error(session)
        if is_error:
            return {"label": "数据错误", "reason": reason, "confidence": 0.90}

        # 2. 重复询问检测（精确字符串匹配 + 相似度匹配）
        is_repeat, reason = detect_repetition(session)
        if is_repeat:
            return {"label": "重复询问", "reason": reason, "confidence": 0.95}

        # 3. 不当告别检测（告别关键词 + 未解决诉求）
        is_farewell, reason = detect_improper_farewell(session)
        if is_farewell:
            return {"label": "不当告别", "reason": reason, "confidence": 0.85}

        # 4. 答非所问检测（规则预过滤，无 LLM）
        is_offtopic, reason = detect_off_topic_rule(session)
        if is_offtopic:
            return {"label": "答非所问", "reason": reason, "confidence": 0.65}

        # 5. 默认：未命中任何质量问题
        return {"label": "无标签命中", "reason": "通过所有检测", "confidence": 0.78}

    def run_batch(
        self,
        data: List[Dict[str, Any]],
        verbose: bool = False,
        use_full_history: bool = False,
    ) -> Dict[str, Any]:
        """
        批量质检并计算与人工校验的一致性。

        参数:
            data:             chat_test_100.json 数据列表（全部 100 条）
            verbose:          True 则逐条打印预测错误的会话信息
            use_full_history: 传递给 check() 的同名参数（默认 False）

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
            pred = self.check(session, use_full_history=use_full_history)
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
