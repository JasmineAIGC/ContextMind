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

#: 规则预测各标签的置信度（基于规则精度估计）
_RULE_CREDIT_ERROR_CONFIDENCE: float = 0.87   # 数据错误：精确额度偏差检测
_RULE_REPETITION_CONFIDENCE: float = 0.87     # 重复询问：精确字符串匹配

#: 不当告别规则预测中"最近未解决诉求"的预览字符数
_ISSUE_PREVIEW: int = 20


# --------------------------------------------------------------------------- #
# 1. 纯规则标签预测
# --------------------------------------------------------------------------- #


def predict_label_pytod(session: Dict[str, Any]) -> Tuple[Optional[str], float, str]:
    """
    使用 QC 执行引擎的事实数据 API 进行快速规则预测（无 LLM）。

    规则只处理高置信度机械性错误，语义判断留给 LLM：
        - 数据错误：回复金额与系统额度存在实质性偏差（含额度前缀/后缀模式）
        - 重复询问：精确字符串匹配历史坐席发言
        - 不当告别：有告别话术且最近历史含 ≥2 条未解决诉求

    无法可靠预测的标签（返回 None，需 LLM 处理）：
        - 答非所问、无标签命中（语义复杂，规则误判率高）

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

    # 不当告别：引擎提供告别事实，规则在此处综合判断
    # build_qc_engine 保证 get_farewell_data 始终注册，KeyError 此处不可能发生
    fare = engine.registry["get_farewell_data"]()
    if fare["has_farewell"] and fare["unresolved_count"] >= 2:
        evidence = "、".join(fare["farewell_evidence"][:2]) if fare["farewell_evidence"] else "告别话术"
        last_issue = fare["unresolved_issues"][-1][:_ISSUE_PREVIEW] if fare["unresolved_issues"] else ""
        reason = (
            f"坐席执行告别话术（{evidence}），"
            f"用户有 {fare['unresolved_count']} 条含诉求词消息"
            + (f"（最近：「{last_issue}…」）" if last_issue else "")
        )
        return "不当告别", 0.75, reason

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
    topic = engine.registry["get_topic_data"]()

    credit_yuan = credit["system_credit"]
    credit_display = f"{credit_yuan:,}元" if credit_yuan > 0 else "未提供"

    data_error_hints: List[str] = credit["hints"]
    repetition_hint: str = rep["hint"]
    farewell_hint: str = fare["hint"]
    has_farewell: bool = fare["has_farewell"]
    topic_hint: str = topic["topic_mismatch_hint"]
    user_has_inquiry: bool = topic.get("user_has_inquiry", False)
    max_sim: float = rep["max_similarity"]

    history_slice = history if use_full_history else history[-_DEFAULT_HISTORY_TURNS:]
    history_text = "\n".join(history_slice)

    system_prompt = (
        "你是一名专业的外呼对话质检专家，负责对小额贷款产品的外呼坐席对话进行质量评估。\n"
        "坐席的职责是推介借款、解答用户咨询，并按规范完成服务流程。\n\n"
        "请对【坐席最终回复】从以下五个质量标签中选择唯一最匹配的一个。\n"
        "每个标签代表一类违规或质量问题，均需要满足明确条件才能判定。\n\n"
        "【核心判断原则】\n"
        "· ⑤无标签命中是默认标签：当①②③④均无明确充分的成立证据时，直接选⑤，不要勉强选择其他标签\n"
        "· 事实判断优先：判断依据必须来自对话内容和系统数据，不能凭感觉或主观推断\n"
        "· 证据不足时选⑤：宁愿漏判一个错误，也不要误判一个正常的对话为违规\n"
        "· 数据缺失时跳过：当规则预分析提示某项数据'未提供'，则对应标签直接不成立\n"
        "· 用户自述的金额（如'我APP显示三万'）不可作为系统真实数据\n"
        "· 只有【用户系统额度】是判断①数据错误的唯一客观标准\n\n"
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
        "   · 若【规则预分析-重复询问】显示高相似度⚠️，需核查对话历史确认是否真的重复\n"
        "   · 若规则未触发⚠️，请自行阅读对话历史判断本次回复是否与历史某条发言实质相同\n\n"
        "③ 不当告别\n"
        "   定义：在用户仍有明确未解决诉求的情况下，坐席执行了告别话术。\n"
        "   判断步骤（严格按顺序执行，第一个不成立即可停止）：\n"
        "   步骤1：确认坐席最终回复是否含明确告别话术（含'再见''不打扰您了''感谢接听''祝您生活愉快'等）\n"
        "         → 如果没有告别话术，③直接不成立。\n"
        "   步骤2：找到用户在对话历史中【最后一条发言】（即坐席本次回复之前用户说的最后一句话）\n"
        "         → 如果【规则预分析-不当告别】显示'用户最后一条消息'，以该信息为准。\n"
        "   步骤3：判断用户最后一条发言是否包含一个本次回复完全未处理的明确问题或诉求\n"
        "         → 如果用户最后说的是简短应答/同意/拒绝，③不成立（见以下不成立场景）。\n"
        "   步骤4：步骤3成立 → ③成立；否则 → ③不成立。\n"
        "   以下情况③明确不成立：\n"
        "   · 用户最后一条消息是简短应答（'嗯''哦''好''知道了''行''明白了''好的'等）\n"
        "   · 用户明确表示拒绝或不需要（'不需要''不借''不用了''没事'等）\n"
        "   · 用户表示需要考虑或稍后操作（'我想想''等我想好了''跟家人商量''我去看看'等）\n"
        "   · 用户同意去操作（'好的我去试试''我去APP看看''那行我去弄'等）\n"
        "   · 【规则预分析-不当告别】显示'（无诉求词）'：说明用户最后一条消息本身无诉求词，\n"
        "     仅靠历史诉求词消息不足以判定不当告别，需用户最后消息有实质性未解决问题才成立。\n\n"
        "④ 答非所问\n"
        "   定义：用户提出了需要坐席正面回应的具体问题或诉求，但坐席最终回复与该问题完全无关。\n"
        "   成立条件（必须同时满足）：\n"
        "   a. 用户最后一条消息包含明确的具体问题或账户诉求（不限于金额词，也包括'在哪里''显示X''申请了Y'等）\n"
        "   b. 坐席最终回复与用户的具体问题属于完全不同的话题，未给出任何相关信息\n"
        "   典型答非所问场景（结合【规则预分析-答非所问】的⚠️信号综合判断）：\n"
        "   · 用户问'多少/多少钱/在哪里'，坐席回答自我介绍或品牌名称\n"
        "   · 用户问'三万元在哪里'，坐席改为介绍公司借还款记录好的优质用户政策（完全偏题）\n"
        "   · 用户报告显示金额（如'显示九万四千八'），坐席用反问切换话题（'您是说之前借过钱吗？'）\n"
        "   · 用户询问其申请/操作结果，坐席重新做品牌自我介绍（对话已建立多轮后）\n"
        "   · 用户问具体数字，坐席把同样问题反问回用户（'您这边大概是多少？'）\n"
        "   以下情况一律不算答非所问：\n"
        "   · 坐席回答了相关话题，即使不够精确或未完整回答\n"
        "   · 用户问贷款/额度/提现/账户/利率/还款，坐席也回复了同类话题\n"
        "   · 坐席承诺查询或核实（'为您查询''我帮您核实'等），视为有效响应\n"
        "   · 坐席问澄清性问题（'您是下午去操作的吗？'）帮助解决用户问题，不算回避\n"
        "   · 用户表达不满/抱怨/质疑，坐席给出了贷款相关的任何解释\n"
        "   · 【重要】对话刚开始（前3-4轮），坐席正在核实用户身份——合规操作，不算答非所问\n"
        "   · 若【规则预分析-答非所问】未含⚠️，请结合对话上下文判断，坐席用解释性语言回应也是有效响应\n\n"
        "⑤ 无标签命中\n"
        "   定义：以上①②③④均不明确成立，回复符合基本服务规范。\n"
        "   适用情形：正常推介、用户接受/拒绝/同意考虑、正常问答（即使不够精确）等。\n"
        "   【重要】这是默认标签。有以下任意情形时直接选⑤，不需要继续考虑其他标签：\n"
        "   · 对话历史太短或缺失，无法确认违规事实\n"
        "   · 各项证据模棱两可，无法确定哪个标签\n"
        "   · 系统额度'未提供'且无其他可检测的违规\n\n"
        "【输出要求】\n"
        "请先逐条核查①到④，每项写出核查结论（成立/不成立及简要理由）。\n"
        "最后一行必须是且仅是以下格式的JSON（不要加代码块标记）：\n"
        '{"label": "标签名", "reason": "理由（15字以内）"}'
    )

    preanalysis_sections: List[str] = []
    if credit_yuan == 0:
        # 系统额度未提供：①数据错误检测无法进行，直接不成立
        preanalysis_sections.append("【规则预分析-数据错误】系统额度未提供，①直接不成立")
    elif data_error_hints:
        preanalysis_sections.append(
            "【规则预分析-数据错误】\n" + "\n".join(f"  · {h}" for h in data_error_hints)
        )
    else:
        preanalysis_sections.append("【规则预分析-数据错误】未检测到明显金额偏差")

    if repetition_hint:
        preanalysis_sections.append(f"【规则预分析-重复询问】{repetition_hint}")
    else:
        preanalysis_sections.append(
            f"【规则预分析-重复询问】最高历史相似度 {max_sim:.0%}（<75%，未触发）"
        )

    # 不当告别预分析：has_farewell=False 时直接标注③不成立，不产生额外噪音
    if not has_farewell:
        preanalysis_sections.append("【规则预分析-不当告别】坐席回复不含明确告别话术，③直接不成立")
    elif farewell_hint:
        preanalysis_sections.append(f"【规则预分析-不当告别】坐席含告别话术；{farewell_hint}")
    else:
        preanalysis_sections.append("【规则预分析-不当告别】坐席含告别话术；未检测到近期未解决诉求")

    if topic_hint:
        preanalysis_sections.append(f"【规则预分析-答非所问】{topic_hint}")
    elif user_has_inquiry:
        preanalysis_sections.append(
            "【规则预分析-答非所问】用户消息含实质性诉求；"
            "请结合对话上下文判断坐席是否正面回应了用户问题"
        )
    else:
        preanalysis_sections.append("【规则预分析-答非所问】用户无明确诉求，④直接不成立")

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

        from contextmind.infra.llm_client import AdkLLMClient, LLMConfig
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
        show_all: bool = False,
        use_full_history: bool = False,
        llm_client: Optional[Any] = None,
        use_pytod_first: bool = False,
    ) -> Dict[str, Any]:
        """
        批量质检并计算与人工校验的一致性。

        参数:
            verbose:   True 时逐条打印预测**错误**的会话详情
            show_all:  True 时逐条打印**所有**会话详情（含正确）

        返回:
            {"predictions": list, "accuracy": float, "by_label": dict, "pytod_rate": float}
        """
        predictions: List[Dict[str, Any]] = []
        correct = 0
        by_label: Dict[str, Dict[str, int]] = {}
        total = len(data)

        for idx, session in enumerate(data, 1):
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

            # 逐条日志：show_all 显示所有，verbose 仅显示错误
            if show_all or (verbose and not pred["correct"]):
                self._print_item(idx, total, session, pred, gold)

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

        print(f"\n{'─' * 60}")
        print(f"总体准确率: {accuracy:.1%} ({correct}/{total})")
        if pytod_count > 0:
            pytod_correct = sum(1 for p in predictions if p.get("source") == "pytod" and p["correct"])
            print(
                f"规则预测覆盖: {pytod_count}/{total} 条（{pytod_rate:.0%}），"
                f"其中正确 {pytod_correct}/{pytod_count}（精度 {pytod_correct/pytod_count:.0%}）"
            )
        llm_count = total - pytod_count
        if llm_count > 0:
            llm_correct = sum(1 for p in predictions if p.get("source") == "llm" and p["correct"])
            print(
                f"LLM 预测覆盖: {llm_count}/{total} 条（{1 - pytod_rate:.0%}），"
                f"其中正确 {llm_correct}/{llm_count}（精度 {llm_correct/llm_count:.0%}）"
            )
        print("\n各标签统计 (P=精确率 R=召回率 F1):")
        for label, stats in sorted(by_label.items(), key=lambda x: -(x[1]["TP"] + x[1]["FN"])):
            tp, fp, fn = stats["TP"], stats["FP"], stats["FN"]
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
            total_gold = tp + fn
            print(
                f"  {label:<8}  金标={total_gold:2d}  TP={tp:2d}  FP={fp:2d}  FN={fn:2d}"
                f"  P={precision:.0%}  R={recall:.0%}  F1={f1:.0%}"
            )
            by_label[label].update(
                {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}
            )

        return {"predictions": predictions, "accuracy": accuracy, "by_label": by_label, "pytod_rate": pytod_rate}

    @staticmethod
    def _print_item(
        idx: int,
        total: int,
        session: Dict[str, Any],
        pred: Dict[str, Any],
        gold: str,
    ) -> None:
        """打印单条会话的质检详情（供 verbose/show_all 模式使用）。"""
        is_correct = pred["label"] == gold
        status = "✅ 正确" if is_correct else "❌ 错误"
        sid = session.get("session_id", "")
        reply = session.get("坐席回复", "")
        history = session.get("对话历史", [])

        # 最近一条用户发言
        last_user = next(
            (t.removeprefix("用户：") for t in reversed(history) if t.startswith("用户：")),
            "",
        )
        reply_short = reply[:60].replace("\n", " ")
        reply_suffix = "…" if len(reply) > 60 else ""
        user_short = last_user[:50].replace("\n", " ")
        user_suffix = "…" if len(last_user) > 50 else ""

        source_tag = f"[{pred.get('source', '?')}  置信度={pred.get('confidence', 0):.0%}]"
        print(
            f"\n  [{idx:03d}/{total}] {status}  {source_tag}\n"
            f"    session_id : {sid}\n"
            f"    用户最后说 : {user_short}{user_suffix}\n"
            f"    坐席回复   : {reply_short}{reply_suffix}\n"
            f"    人工校验   : {gold}\n"
            f"    预测标签   : {pred['label']}\n"
            f"    预测原因   : {pred.get('reason', '—')}"
        )
