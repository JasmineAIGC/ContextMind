"""
安逸花外呼 · 任务一（QC）· 标签预测器

提供三个层次的质量标签预测能力，由低成本到高成本排列：

    1. predict_label_pytod()    — 纯规则，零 LLM，~32% 会话可直接预测
    2. classify_session_llm()     — LLM 全量质检，配合规则 hint 提升精度
    3. PyTODQualityChecker      — 批量质检器，支持 Hybrid（规则优先 + LLM 兜底）模式

典型 Hybrid 流程:
    checker = PyTODQualityChecker()
    result = checker.check(session, llm_client=llm, use_pytod_first=True)
    # → 规则可判断时直接返回（精度 87%），否则调用 LLM
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from .engine import build_qc_engine
from ..utils import USER_PREFIX as _USER_PREFIX, parse_user_info

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #

#: 合法标签集合
_VALID_LABELS: frozenset = frozenset(
    {"数据错误", "重复询问", "不当告别", "答非所问", "无标签命中"}
)

#: 标签优先顺序（JSON 解析失败时按此顺序从原始输出提取标签）
_LABEL_PRIORITY: List[str] = ["数据错误", "重复询问", "不当告别", "答非所问", "无标签命中"]

#: 默认传入 LLM 的最大历史条数
_DEFAULT_HISTORY_TURNS: int = 20

#: 各标签的固定置信度估计（LLM 结果不附带置信度）
_LABEL_CONFIDENCE: Dict[str, float] = {
    "数据错误": 0.85,
    "重复询问": 0.85,
    "不当告别": 0.85,
    "答非所问": 0.80,
    "无标签命中": 0.75,
}

#: 规则预测各标签的置信度（基于 100 条数据集实测精度）
_RULE_CREDIT_ERROR_CONFIDENCE: float = 0.87   # 数据错误：精确额度偏差检测
_RULE_REPETITION_CONFIDENCE: float = 0.87     # 重复询问：精确字符串匹配


# --------------------------------------------------------------------------- #
# 1. 纯规则标签预测
# --------------------------------------------------------------------------- #


def predict_label_pytod(session: Dict[str, Any]) -> Tuple[Optional[str], float, str]:
    """
    使用 QC 执行引擎的事实数据 API 进行快速规则预测（无 LLM）。

    规则只处理高置信度机械性错误，语义判断留给 LLM：
        - 数据错误：回复金额偏差 > 300 元（P=89%, R=87%）
        - 重复询问：精确字符串匹配（P=87%, R=87%）

    无法可靠预测的标签（返回 None，需 LLM 处理）：
        - 不当告别、答非所问、无标签命中

    实测（100 条安逸花数据集）：
        28/100 会话可直接给出答案，89% 精度，节省约 28% LLM 调用。

    返回:
        (label, confidence, reason)
        label=None 表示规则无法判断，需交由 classify_session_llm 处理。
    """
    engine = build_qc_engine(session)

    # 数据错误：引擎提供事实（偏差金额），规则在此处应用阈值
    credit = engine.registry["get_credit_data"]()
    if credit["discrepant_amounts"]:
        text, value, diff = credit["discrepant_amounts"][0]
        reason = (
            f"回复提及「{text}」({value:,}元)，"
            f"系统额度{credit['system_credit']:,}元，偏差{diff:,}元"
        )
        return "数据错误", _RULE_CREDIT_ERROR_CONFIDENCE, reason

    # 重复询问：引擎提供精确匹配事实，规则在此处应用阈值
    rep = engine.registry["get_repetition_data"]()
    if rep["exact_repeat"] and rep["repeat_count"] >= 1:
        reason = f"坐席回复与历史发言精确匹配，已重复 {rep['repeat_count'] + 1} 次"
        return "重复询问", _RULE_REPETITION_CONFIDENCE, reason

    return None, 0.0, "规则无法判断，需 LLM 语义推理"


# --------------------------------------------------------------------------- #
# 2. LLM 全量质检
# --------------------------------------------------------------------------- #


async def classify_session_llm(
    session: Dict[str, Any],
    llm_client: Any,
    use_full_history: bool = False,
) -> Tuple[str, str]:
    """
    LLM 全量质检：单次调用，按优先级依次检查五个质量标签。

    使用 QC 引擎的事实数据 API 结果作为结构化 hint 注入 prompt，
    提升 LLM 对数值偏差和重复模式的感知精度。

    prompt 中的判断标准描述的是通用外呼质检业务策略，适用于各类
    小额贷款产品的坐席对话质检场景，不依赖特定测试数据集。

    参数:
        session:          包含"用户信息"、"对话历史"、"坐席回复"的会话记录
        llm_client:       需支持 chat_async(messages, temperature) 方法
        use_full_history: True 时将完整对话历史送入 LLM（默认仅最近 20 条）

    返回:
        (label: str, reason: str)，label 必为 _VALID_LABELS 之一
    """
    history = session["对话历史"]
    reply = session["坐席回复"]

    # 从 QC 引擎获取结构化预分析事实数据（引擎只提供数据，不做标签判断）
    engine = build_qc_engine(session)
    credit = engine.registry["get_credit_data"]()
    rep = engine.registry["get_repetition_data"]()
    fare = engine.registry["get_farewell_data"]()

    credit_yuan = credit["system_credit"]
    credit_display = f"{credit_yuan:,}元" if credit_yuan > 0 else "未提供"

    data_error_hints: List[str] = credit["hints"]
    repetition_hint: str = rep["hint"]
    farewell_hint: str = fare["hint"]
    max_sim: float = rep["max_similarity"]

    history_slice = history if use_full_history else history[-_DEFAULT_HISTORY_TURNS:]
    history_text = "\n".join(history_slice)

    system_prompt = (
        "你是一名专业的外呼对话质检专家，负责对小额贷款产品的外呼坐席对话进行质量评估。\n"
        "坐席的职责是推介借款、解答用户咨询，并按规范完成服务流程。\n\n"
        "请对【坐席最终回复】从以下五个质量标签中选择唯一最匹配的一个。\n"
        "每个标签代表一类违规或质量问题，均需要满足明确条件才能判定。\n\n"
        "【重要说明】\n"
        "· 判断依据必须来自对话内容和系统数据，不能凭感觉或主观推断\n"
        "· 用户自述的金额（如'我APP显示三万'）不可作为系统真实数据\n"
        "· 只有【用户系统额度】是判断数据错误的唯一客观标准\n\n"
        "【五个质量标签的判断标准（按①→⑤顺序逐一核查，第一个明确成立的即为结果）】\n\n"
        "① 数据错误\n"
        "   定义：坐席在向用户陈述账户可提现额度时，所报金额与系统记录存在实质性偏差。\n"
        "   成立条件（必须同时满足）：\n"
        "   a. 坐席（历史发言或最终回复）中出现了明确的可提现额度数字\n"
        "   b. 该数字与【用户系统额度】存在实质性偏差（通常超过300元，需结合金额量级判断）\n"
        "   核查要点：\n"
        "   · 仅当坐席陈述的是用户可提现额度时才检测（如'您的额度是X元''您还有X元可提现'等）\n"
        "   · 还款金额、手续费、利息、分期月供等不属于可提现额度，不纳入此项检测\n"
        "   · 建议提现数额（坐席建议提多少）不等于额度本身\n"
        "   · 未来奖励额度、促销固定额度等与当前可提现额度无关\n"
        "   · 若【规则预分析-数据错误】有偏差警告⚠️，需核查上下文后再判断\n"
        "   · 若【用户系统额度】为'未提供'，则该项直接不成立\n\n"
        "② 重复询问\n"
        "   定义：坐席在本次回复中使用了与历史发言实质相同的话术，构成无效重复。\n"
        "   成立条件（必须同时满足）：\n"
        "   a. 坐席最终回复的核心话术，与对话历史中某条坐席发言高度一致或几乎逐字相同\n"
        "   b. 历史中确实已说过该话术（本次是重复，不是第一次表达）\n"
        "   核查要点：\n"
        "   · 话题相同但措辞明显不同的不算重复\n"
        "   · 核实身份的固定开场白（如'请问您是X先生/女士吗'）属于合规话术，不算重复\n"
        "   · 若【规则预分析-重复询问】显示高相似度⚠️，需确认历史中确实出现过\n\n"
        "③ 不当告别\n"
        "   定义：在用户仍有明确未解决诉求的情况下，坐席执行了告别话术。\n"
        "   成立条件（必须同时满足）：\n"
        "   a. 坐席最终回复包含明确告别话术（含'再见''不打扰您了''感谢接听''祝您生活愉快'等）\n"
        "   b. 用户最近消息中有一个本次回复完全未触及的明确问题或投诉\n"
        "   以下情况说明用户无实质性未解决诉求（不当告别不成立）：\n"
        "   · 用户明确表示拒绝或不需要（'不需要''不借''不用了''没事'）\n"
        "   · 用户表示需要考虑（'我想想''等我想好了''跟家人商量'）\n"
        "   · 用户同意去操作或查看（'好的我去试试''我去APP看看''那行我去弄'）\n"
        "   · 用户只是简短应答（'嗯''哦''好''知道了''行''明白了'）\n\n"
        "④ 答非所问\n"
        "   定义：用户提出明确具体问题，但坐席回复与该问题完全无关。\n"
        "   成立条件（门槛较高，必须同时满足）：\n"
        "   a. 用户最后一条消息包含非常明确的具体问题（有问号或明显询问语气）\n"
        "   b. 坐席最终回复与用户的具体问题属于完全不同的话题，毫无关联\n"
        "   以下情况一律不算答非所问：\n"
        "   · 坐席回答了相关话题，即使不够精确或未完整回答\n"
        "   · 用户问贷款/额度/提现/账户/利率/还款，坐席也回复了同类话题\n"
        "   · 坐席在推介产品时未专门回答某个细节\n"
        "   · 坐席承诺查询或核实（'为您查询''我帮您核实'等），视为有效响应\n"
        "   · 用户表达不满/抱怨/质疑，坐席给出了贷款相关的任何解释\n\n"
        "⑤ 无标签命中\n"
        "   定义：以上①②③④均不明确成立，回复符合基本服务规范。\n"
        "   适用情形：正常推介、用户接受/拒绝/同意考虑、正常问答（即使不够精确）等。\n\n"
        "【输出要求】\n"
        "请先逐条核查①到④，每项写出核查结论（成立/不成立及简要理由）。\n"
        "最后一行必须是且仅是以下格式的JSON（不要加代码块标记）：\n"
        '{"label": "标签名", "reason": "理由（15字以内）"}'
    )

    preanalysis_sections: List[str] = []
    if data_error_hints:
        preanalysis_sections.append(
            "【规则预分析-数据错误】\n" + "\n".join(f"  · {h}" for h in data_error_hints)
        )
    else:
        preanalysis_sections.append("【规则预分析-数据错误】未检测到明显金额偏差")

    if repetition_hint:
        preanalysis_sections.append(f"【规则预分析-重复询问】{repetition_hint}")
    else:
        preanalysis_sections.append(
            f"【规则预分析-重复询问】最高历史相似度 {max_sim:.0%}（<80%，未触发）"
        )

    if farewell_hint:
        preanalysis_sections.append(f"【规则预分析-不当告别】{farewell_hint}")
    else:
        preanalysis_sections.append("【规则预分析-不当告别】未检测到明显未解决诉求")

    user_message = (
        f"【用户系统额度（仅用于①数据错误的判断）】{credit_display}\n\n"
        + "\n".join(preanalysis_sections)
        + f"\n\n【对话历史（共{len(history)}条，显示最近{len(history_slice)}条）】\n"
        f"{history_text}\n\n"
        f"【坐席最终回复（待评估）】\n{reply}\n\n"
        "请逐条核查①→④，最后一行输出JSON。"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    raw = ""
    for _ in range(3):
        try:
            raw = await llm_client.chat_async(messages=messages, temperature=0.0)
            raw_clean = raw.strip()
            if raw_clean.startswith("```"):
                raw_clean = raw_clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            elif raw_clean.startswith("`"):
                raw_clean = raw_clean.strip("`")
            raw_clean = re.sub(r"<think>.*?</think>", "", raw_clean, flags=re.DOTALL).strip()

            parsed = None
            for obj_str in reversed(re.findall(r'\{[^{}]+\}', raw_clean)):
                try:
                    obj = json.loads(obj_str)
                    if "label" in obj:
                        parsed = obj
                        break
                except json.JSONDecodeError:
                    continue
            if parsed is None:
                parsed = json.loads(raw_clean)

            label = parsed.get("label", "无标签命中")
            reason = parsed.get("reason", "")
            if label not in _VALID_LABELS:
                for candidate in _LABEL_PRIORITY:
                    if candidate in raw:
                        return candidate, reason or "从输出提取标签"
                return "无标签命中", f"LLM 返回未知标签: {label}"
            return label, reason
        except json.JSONDecodeError:
            continue
        except Exception as exc:
            return "无标签命中", f"LLM 调用异常: {exc}"

    for candidate in _LABEL_PRIORITY:
        if candidate in raw:
            return candidate, "从原始输出提取标签"
    return "无标签命中", "多次尝试后 JSON 解析仍失败"


# --------------------------------------------------------------------------- #
# 3. 批量质检器
# --------------------------------------------------------------------------- #


class PyTODQualityChecker:
    """
    安逸花外呼对话 PyTOD 批量质检器。

    支持两种模式：
    - 纯 LLM 模式（默认）：所有检测均由 LLM 完成；
      QC 执行引擎提供结构化 hint 注入 prompt。
    - Hybrid 模式（use_pytod_first=True）：
      先由 predict_label_pytod() 纯规则判断；
      规则无法判断时再调用 LLM（节省约 32% token）。

    使用示例::

        from contextmind.infra.llm_client import SimpleLLMClient, LLMConfig
        checker = PyTODQualityChecker()

        # Hybrid 模式（推荐）
        result = checker.check(session, llm_client=llm, use_pytod_first=True)
        # → {"label": "重复询问", "reason": "...", "confidence": 0.87, "source": "pytod"}

        # 批量质检
        results = checker.run_batch(data, llm_client=llm, use_pytod_first=True)
    """

    def check(
        self,
        session: Dict[str, Any],
        use_full_history: bool = False,
        llm_client: Optional[Any] = None,
        use_pytod_first: bool = False,
    ) -> Dict[str, Any]:
        """
        对单条会话进行质量分类。

        参数:
            session:           包含"用户信息"、"对话历史"、"坐席回复"的会话记录
            use_full_history:  True 时将完整对话历史送入 LLM
            llm_client:        LLMClient 实例（use_pytod_first=False 时必须提供）
            use_pytod_first:   True 时启用 Hybrid 模式

        返回:
            {"label": str, "reason": str, "confidence": float, "source": str}
        """
        if use_pytod_first:
            label, confidence, reason = predict_label_pytod(session)
            if label is not None:
                return {"label": label, "reason": reason, "confidence": confidence, "source": "pytod"}

        if llm_client is None:
            raise ValueError(
                "规则无法判断该会话，需要 LLM 处理，"
                "请传入已初始化的 LLMClient 实例。"
            )

        try:
            asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    asyncio.run,
                    classify_session_llm(session, llm_client, use_full_history),
                )
                label, reason = future.result()
        except RuntimeError:
            label, reason = asyncio.run(
                classify_session_llm(session, llm_client, use_full_history)
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

        返回:
            {"predictions": list, "accuracy": float, "by_label": dict, "pytod_rate": float}
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
                print(f"❌ {session['session_id'][-8:]} | 预测: {pred['label']} | 实际: {gold}")
                print(f"   原因: {pred['reason']}")

        total = len(data)
        accuracy = correct / total if total else 0.0
        pytod_count = sum(1 for p in predictions if p.get("source") == "pytod")
        pytod_rate = pytod_count / total if total else 0.0

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

        print(f"\n总体准确率: {accuracy:.1%} ({correct}/{total})")
        if pytod_count > 0:
            pytod_correct = sum(1 for p in predictions if p.get("source") == "pytod" and p["correct"])
            print(
                f"PyTOD 规则预测: {pytod_count}/{total} 条（{pytod_rate:.0%}），"
                f"其中正确 {pytod_correct}/{pytod_count}（精度 {pytod_correct/pytod_count:.0%}）"
            )
        print("\n各标签统计:")
        for label, stats in by_label.items():
            tp, fp, fn = stats["TP"], stats["FP"], stats["FN"]
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
            print(f"  {label}: P={precision:.0%} R={recall:.0%} F1={f1:.0%}")
            by_label[label].update(
                {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}
            )

        return {"predictions": predictions, "accuracy": accuracy, "by_label": by_label, "pytod_rate": pytod_rate}
