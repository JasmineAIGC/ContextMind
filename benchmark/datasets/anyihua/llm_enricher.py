"""
LLM 驱动的 SGD 字段补全器（安逸花外呼场景）

使用 contextmind/infra/llm_client.py 提供的大模型，对规则无法精确推断的
SGD 字段进行逐轮语义补全：

  active_intent    → 结合完整对话上下文进行意图识别
  requested_slots  → 从用户疑问句中检测正在询问的槽位
  actions (USER)   → 识别用户主动 INFORM 的信息槽及值
  service_call     → 从坐席话语提取 API 参数（补充规则层漏失的参数）

设计原则：
  1. 单次 LLM 调用处理整条对话，通过 JSON 结构化输出降低 token 消耗。
  2. 返回结果为可合并的增量字典，不覆盖规则层已正确填充的字段。
  3. 所有 LLM 调用均有 try/except 保护，失败时静默回退到规则层结果。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from contextmind.infra.llm_client import SimpleLLMClient, LLMConfig
from contextmind.infra.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 常量（与 adapter.py 中的意图/槽位体系保持一致）
# ---------------------------------------------------------------------------

VALID_INTENTS = [
    "verify_identity",
    "explain_credit_limit",
    "explain_interest_rate",
    "calculate_repayment",
    "explain_displayed_amount",
    "handle_loan_dispute",
    "guide_loan_operation",
    "escalate_to_human",
    "say_goodbye",
    "general_inquiry",
]

VALID_SLOTS = [
    "customer_name",
    "phone_suffix",
    "dispute_date",
    "inquiry_amount",
    "term_months",
    "identity_confirmed",
    "available_credit",
    "temp_credit",
    "temp_credit_status",
    "temp_expiry_days",
    "annual_rate_pct",
    "loan_count",
    "last_loan_date",
    "outstanding_amount",
    "billing_day",
]

# ---------------------------------------------------------------------------
# 批量补全提示模板
# ---------------------------------------------------------------------------

_BATCH_ENRICHMENT_PROMPT = """\
你是安逸花外呼对话结构化标注助手。你的任务是对完整的外呼对话进行逐轮标注，
补全 SGD（Schema-Guided Dialogue）格式中规则层无法准确填充的字段。

业务背景：安逸花坐席主动致电老用户，目标是激活用户闲置的借款额度。
标准业务流程：核实身份 → 告知额度 → 解答疑问 → 引导借款 → 礼貌告别。

可用意图（valid_intents）：
verify_identity, explain_credit_limit, explain_interest_rate, calculate_repayment,
explain_displayed_amount, handle_loan_dispute, guide_loan_operation,
escalate_to_human, say_goodbye, general_inquiry

可用槽位（valid_slots）：
customer_name, phone_suffix, dispute_date, inquiry_amount, term_months,
identity_confirmed, available_credit, temp_credit, temp_credit_status,
temp_expiry_days, annual_rate_pct, loan_count, last_loan_date,
outstanding_amount, billing_day

对于对话中每一轮，需要返回：

USER 轮：
  - active_intent:     用户当前追求的意图（从 valid_intents 中选一个）
  - requested_slots:   用户疑问句中询问的槽位名称列表（可为空列表）
  - inform_slots:      用户主动告知的槽位及值（格式：{{"slot_name": "value"}}，可为空字典）

SYSTEM 轮：
  - service_call_params: 坐席话语中明确提及的 API 调用参数
                         格式：{{"slot_name": "value"}}，可为空字典
                         仅需 API 调用的轮次才填写（核实身份、查询额度、查借款记录等）

标注规则：
1. 用户意图具有持续性：短回应词（"嗯"、"对"、"好"、"啊"）继承上一个明确的用户意图。
2. 坐席话语不改变用户意图。
3. requested_slots 只在用户话语包含疑问句时非空。
4. inform_slots 只填写用户话语中明确提到的信息，不要推测。
5. 只返回 JSON，不要有任何说明文字。

输出格式（严格 JSON，对话共有 {turn_count} 轮）：
{{
  "turns": [
    {{
      "turn_index": 0,
      "speaker": "SYSTEM",
      "service_call_params": {{}}
    }},
    {{
      "turn_index": 1,
      "speaker": "USER",
      "active_intent": "verify_identity",
      "requested_slots": [],
      "inform_slots": {{}}
    }}
  ]
}}

---
以下是需要标注的完整对话（共 {turn_count} 轮）：

{dialogue_text}

请对以上所有 {turn_count} 轮逐一标注，返回严格 JSON。"""


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _parse_json_response(text: str, fallback: Any) -> Any:
    """从 LLM 输出中提取 JSON，失败时返回 fallback。"""
    # 1. 尝试直接解析
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # 2. 尝试提取 ```json ... ``` 块
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    # 3. 尝试提取最外层 { ... } 块（非贪婪，避免跨多个独立对象）
    match = re.search(r"\{[\s\S]+?\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    # 4. 贪婪匹配兜底（整个输出是一个大 JSON 对象时有效）
    match = re.search(r"\{[\s\S]+\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    logger.warning(f"LLM 输出无法解析为 JSON: {text[:200]!r}")
    return fallback


def _validate_intent(intent: str) -> str:
    """校验意图值，不合法时回退到 general_inquiry。"""
    if intent in VALID_INTENTS:
        return intent
    logger.debug(f"LLM 返回非法意图 '{intent}'，回退到 general_inquiry")
    return "general_inquiry"


def _validate_slots(slots: Any) -> List[str]:
    """校验 requested_slots 列表，过滤非法槽位名。"""
    if not isinstance(slots, list):
        return []
    return [s for s in slots if isinstance(s, str) and s in VALID_SLOTS]


def _validate_inform_slots(inform_slots: Any) -> Dict[str, str]:
    """校验 inform_slots 字典，过滤非法槽位名。"""
    if not isinstance(inform_slots, dict):
        return {}
    return {k: str(v) for k, v in inform_slots.items() if k in VALID_SLOTS}


# ---------------------------------------------------------------------------
# LLMEnricher 主类
# ---------------------------------------------------------------------------


class LLMEnricher:
    """
    使用 LLM 对 SGD turns 进行批量语义补全。

    用法示例（在 ChatTestToSGDConverter._convert_record 之后调用）：

        enricher = LLMEnricher.from_env()
        sgd_dialogue = enricher.enrich(sgd_dialogue)
    """

    def __init__(self, client: SimpleLLMClient) -> None:
        self._client = client

    @classmethod
    def from_env(cls) -> "LLMEnricher":
        """从环境变量初始化 LLM 客户端并创建 enricher。"""
        config = LLMConfig.from_env()
        # 较低温度保证结构化 JSON 输出的稳定性
        config.temperature = 0.1
        client = SimpleLLMClient(config)
        return cls(client)

    # ------------------------------------------------------------------ #
    # 公开接口
    # ------------------------------------------------------------------ #

    def enrich(self, sgd_dialogue: Dict) -> Dict:
        """
        对单条 SGD dialogue 进行 LLM 语义补全。

        流程：
          1. 一次性调用 LLM，传入完整对话，获得每轮的结构化标注。
          2. 将 LLM 返回的结果合并回 sgd_dialogue 的 turns。
          3. 保持规则层已正确填充的字段（slot_values、service_results 等）不变。

        参数：
            sgd_dialogue: adapter.py 已经生成的基础 SGD dialogue 字典

        返回：
            更新后的 sgd_dialogue（原地修改并返回）
        """
        turns = sgd_dialogue.get("turns", [])
        if not turns:
            return sgd_dialogue

        llm_results = self._batch_enrich(turns)
        if not llm_results:
            return sgd_dialogue

        self._merge_results(turns, llm_results)
        return sgd_dialogue

    # ------------------------------------------------------------------ #
    # 批量补全（单次 LLM 调用处理整条对话）
    # ------------------------------------------------------------------ #

    def _batch_enrich(self, turns: List[Dict]) -> Optional[List[Dict]]:
        """
        将整条对话发送给 LLM，一次性获取每轮的补全结果。

        返回：
            LLM 返回的 turns 列表（与 sgd turns 一一对应），
            或 None（LLM 调用失败时）
        """
        dialogue_text = self._format_dialogue_for_llm(turns)
        prompt = _BATCH_ENRICHMENT_PROMPT.format(
            turn_count=len(turns),
            dialogue_text=dialogue_text,
        )

        try:
            _, response = self._client.generate(prompt)
            parsed = _parse_json_response(response, fallback=None)
            if parsed is None:
                return None
            llm_turns = parsed.get("turns")
            if not isinstance(llm_turns, list):
                logger.warning("LLM 返回格式错误：缺少 'turns' 列表")
                return None
            return llm_turns
        except Exception as exc:
            logger.warning(f"LLM 批量补全失败，使用规则层结果: {exc}")
            return None

    def _format_dialogue_for_llm(self, turns: List[Dict]) -> str:
        """将 SGD turns 格式化为 LLM 可读的文本。"""
        lines = []
        for i, t in enumerate(turns):
            spk = "坐席" if t["speaker"] == "SYSTEM" else "用户"
            lines.append(f"[{i}][{spk}]: {t['utterance']}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # 结果合并
    # ------------------------------------------------------------------ #

    def _merge_results(
        self,
        sgd_turns: List[Dict],
        llm_turns: List[Dict],
    ) -> None:
        """
        将 LLM 补全结果合并回 sgd_turns。

        合并策略：
        - active_intent: 优先使用 LLM 结果（语义理解更准确）
        - requested_slots: 优先使用 LLM 结果（规则层 93% 为空）
        - USER actions: 追加 LLM 提取的 inform_slots（不删除规则层已提取的动作）
        - SYSTEM service_call.parameters: 补充 LLM 提供的缺失参数值
        """
        # 建立 turn_index → llm_result 的映射
        llm_by_index: Dict[int, Dict] = {}
        for lr in llm_turns:
            idx = lr.get("turn_index")
            if isinstance(idx, int) and 0 <= idx < len(sgd_turns):
                llm_by_index[idx] = lr

        for i, sgd_turn in enumerate(sgd_turns):
            lr = llm_by_index.get(i)
            if lr is None:
                continue

            frame = sgd_turn["frames"][0]
            speaker = sgd_turn["speaker"]

            if speaker == "USER":
                self._merge_user_turn(frame, lr)
            else:
                self._merge_system_turn(frame, lr)

    def _merge_user_turn(self, frame: Dict, lr: Dict) -> None:
        """合并 USER 轮的 LLM 结果。"""
        state = frame.get("state", {})

        # 1. active_intent：LLM 有明确意图时覆盖规则层结果
        llm_intent = lr.get("active_intent", "")
        if llm_intent:
            validated = _validate_intent(llm_intent)
            # 若 LLM 给出了非 general_inquiry 意图，直接采用；
            # 若 LLM 也给出 general_inquiry，只在规则层同样为 general_inquiry 时接受
            if validated != "general_inquiry" or state.get("active_intent") == "general_inquiry":
                state["active_intent"] = validated

        # 2. requested_slots：LLM 结果优先（规则层几乎全空）
        llm_req = _validate_slots(lr.get("requested_slots", []))
        if llm_req:
            state["requested_slots"] = llm_req

        # 3. USER actions：将 LLM 提取的 inform_slots 转换为 INFORM action，
        #    追加到规则层已提取的动作之后（不重复）
        llm_inform = _validate_inform_slots(lr.get("inform_slots", {}))
        if llm_inform:
            existing_actions: List[Dict] = frame.get("actions", [])
            existing_slots = {a["slot"] for a in existing_actions if a.get("act") == "INFORM"}
            for slot_name, value in llm_inform.items():
                if slot_name not in existing_slots:
                    existing_actions.append({
                        "act": "INFORM",
                        "slot": slot_name,
                        "values": [value],
                        "canonical_values": [value],
                    })
            frame["actions"] = existing_actions

        # 更新 state 回 frame
        frame["state"] = state

    def _merge_system_turn(self, frame: Dict, lr: Dict) -> None:
        """合并 SYSTEM 轮的 LLM 结果（仅补充 service_call 参数）。

        LLM 返回的 service_call_params 使用槽位名称（slot names），
        而 service_call.parameters 使用 API 参数键名，两者存在映射关系：
          customer_name → name
          其他槽位名 → 同名
        """
        llm_params = lr.get("service_call_params", {})
        if not isinstance(llm_params, dict) or not llm_params:
            return

        # 仅当已有 service_call 时补充 parameters（不凭空添加 service_call）
        if "service_call" not in frame:
            return

        # 槽位名 → API 参数名映射（与 adapter.py _build_service_call 保持一致）
        _slot_to_api_param: Dict[str, str] = {
            "customer_name": "name",
        }

        existing_params = frame["service_call"].get("parameters", {})
        for slot_name, value in llm_params.items():
            if slot_name not in VALID_SLOTS:
                continue
            api_key = _slot_to_api_param.get(slot_name, slot_name)
            if api_key not in existing_params:
                existing_params[api_key] = str(value)
        frame["service_call"]["parameters"] = existing_params
