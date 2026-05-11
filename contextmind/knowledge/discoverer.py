"""
通用对话发现器（GenericDialogueDiscoverer）

从单条对话中开放式发现槽位（slot_value）和意图（intent）。
通过 ``langextract`` 为每条提取结果附加字符级溯源（provenance），
指向知识来源的原始话语位置。langextract 未安装时自动降级为纯 LLM 提取模式。

溯源字段格式
-----------
- 溯源成功：``「原文片段」[第N轮(说话人) 位置 start:end]``
- 溯源失败：``「原文片段」[第N轮(说话人) 溯源失败]``
- 降级模式：``None``
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from contextmind.infra.llm_client import AdkLLMClient, LLMConfig
from contextmind.infra.logger import get_logger

logger = get_logger(__name__)


# ------------------------------------------------------------------
# 可选依赖：langextract
# ------------------------------------------------------------------

try:
    import langextract as lx  # type: ignore[import-untyped]
    from langextract.core.base_model import BaseLanguageModel  # type: ignore[import-untyped]
    from langextract.core.types import ScoredOutput  # type: ignore[import-untyped]
    from langextract.data import ExampleData, Extraction  # type: ignore[import-untyped]

    _LANGEXTRACT_AVAILABLE = True
except ImportError:  # pragma: no cover
    lx = None  # type: ignore[assignment]
    BaseLanguageModel = object  # type: ignore[assignment,misc]
    ScoredOutput = None  # type: ignore[assignment,misc]
    ExampleData = None  # type: ignore[assignment,misc]
    Extraction = None  # type: ignore[assignment,misc]
    _LANGEXTRACT_AVAILABLE = False
    logger.debug(
        "[GenericDialogueDiscoverer] langextract 未安装，溯源功能不可用；"
        "安装方式：pip install langextract"
    )


# ------------------------------------------------------------------
# 数据模型
# ------------------------------------------------------------------


@dataclass
class DiscoveryItem:
    """单条开放式发现结果项，含可选的原文溯源信息。

    extraction_class: ``"slot_value"``、``"intent"`` 或 ``"fact"``
    provenance: 溯源字符串，仅在 langextract 可用时填充
    """

    extraction_class: str
    label: str
    value: str
    provenance: Optional[str] = None
    extraction_text: str = ""


# ------------------------------------------------------------------
# langextract 适配器（langextract 可用时有效）
# ------------------------------------------------------------------


def _strip_code_fences(text: str) -> str:
    """提取 LLM 输出中 ``` 代码围栏内的内容，无围栏时原样返回。"""
    m = re.search(r"```(?:yaml|json)?\s*([\s\S]+?)\s*```", text)
    if m:
        return m.group(1).strip()
    return text


def _sanitize_infer_yaml(text: str) -> str:
    """清洗 LLM 返回的 YAML/JSON 文本，过滤非法条目，返回带 ``extractions`` 包装键的 JSON 字符串。

    支持三种格式：
    - 格式 A：``{"extraction_class": ..., "extraction_text": ..., "attributes": {...}}``
    - 格式 B：``{"intent": ..., "intent_attributes": {...}}``（langextract 原生）
    - 格式 C：``{"extractions": [{...}, ...]}``（已含包装键）

    非法 extraction_text（非 str/int/float）和非法属性值均被过滤；解析失败返回空包装对象。
    """
    _EMPTY = '{"extractions": []}'
    try:
        import yaml  # type: ignore[import]
        # 先去除 LLM 可能输出的 markdown 代码围栏
        content = _strip_code_fences(text)
        if not content.strip():
            return _EMPTY
        parsed = yaml.safe_load(content)
        if isinstance(parsed, dict) and "extractions" in parsed:
            raw_items = parsed["extractions"]
            items = raw_items if isinstance(raw_items, list) else []
        elif isinstance(parsed, list):
            items = parsed
        else:
            return _EMPTY
        cleaned = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if "extraction_class" in item and "extraction_text" in item:
                ec = item.get("extraction_class")
                et = item.get("extraction_text")
                attrs = item.get("attributes")
                if not isinstance(ec, str) or not ec.strip():
                    logger.debug(
                        f"[AdkLLMClientAdapter] 过滤格式A条目（extraction_class无效）: {item!r}"
                    )
                    continue
                if not isinstance(et, (str, int, float)):
                    logger.debug(
                        f"[AdkLLMClientAdapter] 过滤格式A条目"
                        f"（extraction_text类型={type(et).__name__}）: {item!r}"
                    )
                    continue
                if isinstance(et, str) and not et.strip():
                    logger.debug(
                        f"[AdkLLMClientAdapter] 过滤格式A条目（extraction_text为空）: {item!r}"
                    )
                    continue
                converted: Dict[str, Any] = {ec: et}
                if isinstance(attrs, dict) and attrs:
                    converted[f"{ec}_attributes"] = attrs
                cleaned.append(converted)
            else:
                filtered: Dict[str, Any] = {}
                has_valid = False
                for k, v in item.items():
                    if k.endswith("_attributes"):
                        if isinstance(v, (dict, type(None))):
                            filtered[k] = v
                        else:
                            logger.debug(
                                f"[AdkLLMClientAdapter] 过滤格式B属性字段"
                                f"（类型={type(v).__name__}）: key={k!r}"
                            )
                    else:
                        if isinstance(v, (str, int, float)) and (
                            not isinstance(v, str) or v.strip()
                        ):
                            filtered[k] = v
                            has_valid = True
                        else:
                            logger.debug(
                                f"[AdkLLMClientAdapter] 过滤格式B条目"
                                f"（值类型={type(v).__name__}）: key={k!r}"
                            )
                if has_valid:
                    cleaned.append(filtered)
        if not cleaned:
            return _EMPTY
        return json.dumps({"extractions": cleaned}, ensure_ascii=False)
    except Exception:
        return _EMPTY


class AdkLLMClientAdapter(BaseLanguageModel):  # type: ignore[misc]
    """将 AdkLLMClient 适配为 langextract BaseLanguageModel 接口。"""

    def __init__(self, client: AdkLLMClient) -> None:
        super().__init__()
        self._client = client

    def infer(
        self,
        batch_prompts: Sequence[str],
        **kwargs: Any,
    ) -> Iterator[Sequence[Any]]:
        """实现 langextract BaseLanguageModel.infer() 接口，逐条调用 LLM 并包装为 ScoredOutput。"""
        if not _LANGEXTRACT_AVAILABLE:  # pragma: no cover
            raise RuntimeError("langextract 未安装，无法使用 AdkLLMClientAdapter")
        for prompt in batch_prompts:
            try:
                _reasoning, text = self._client.generate(prompt)
                if not text.strip():
                    logger.debug("[AdkLLMClientAdapter] LLM 返回空响应，本轮无提取结果")
                    yield [ScoredOutput(score=0.0, output='{"extractions": []}')]
                else:
                    sanitized = _sanitize_infer_yaml(text)
                    yield [ScoredOutput(score=1.0, output=sanitized)]
            except Exception as exc:
                logger.warning(f"[AdkLLMClientAdapter] LLM 推理失败: {exc}")
                yield [ScoredOutput(score=0.0, output='{"extractions": []}')]


# ------------------------------------------------------------------
# LLM prompt 模板（纯 LLM 降级模式）
# ------------------------------------------------------------------

_DISCOVERY_SYSTEM = """\
你是一名任务型对话系统分析专家。给定一段业务对话，请从对话的**所有发言**（坐席和用户）中提取：

1. 槽位值（slot_value）：对话中涉及的具体业务字段和值（如金额、期数、意向、利率、姓名、状态等）
2. 意图（intent）：发言人表达的业务动作、目标或态度（如询问月供、拒绝贷款、抱怨利率高等）
3. 关键事实（fact）：对话中不属于槽位值也不属于意图的重要业务陈述（如核实结果、额度说明等）

注意：
- 坐席（机器人）话语中包含大量业务数据（金额、利率、额度等），请务必提取
- 用户话语中包含其意图和提供的个人信息，也要提取
- 对话中 "机器人：" 前缀的轮次是机器人，"用户：" 前缀的轮次是客户
- 尽可能完整，不遗漏任何业务相关的槽位、意图和事实

## 输出格式（严格 JSON 数组，只输出 JSON）

[
  {"class": "slot_value", "label": "槽位名称（英文下划线）", "value": "提取的值"},
  {"class": "intent", "label": "意图名称（英文动词短语）", "value": "意图的中文描述"},
  {"class": "fact", "label": "事实标签（英文下划线）", "value": "事实的中文描述"},
  ...
]

## 规范说明

- class 只能是 "slot_value"、"intent" 或 "fact"
- label 使用英文小写下划线命名（如 inquire_monthly_payment、available_credit）
- 尽可能完整，不遗漏重要槽位、意图和事实
- 只输出 JSON 数组，不加任何说明或 markdown 代码块"""

_DISCOVERY_USER_TEMPLATE = """\
## 业务场景：{scene_name}

## 对话内容（请从用户发言中提取）：
{dialogue_text}

请从上述对话的**用户**发言中提取槽位值、意图和关键事实（只输出 JSON 数组）："""

# ------------------------------------------------------------------
# 逐轮批量提取 prompt（单次 LLM 调用完成全对话所有轮次的提取）
# ------------------------------------------------------------------

_DISCOVERY_PERTURN_SYSTEM = """\
你是一名任务型对话系统分析专家。给定一段编号的业务对话，请从话语中提取三类信息：

1. 槽位值（slot_value）：话语中涉及的具体业务字段和值（如金额、期数、利率、姓名、状态等）
   - 坐席和用户话语均需提取业务字段值，覆盖所有关键数据

2. 意图（intent）：说话人表达的**核心业务动作或目标**
   - **每轮话语至多提取 1 个意图**（该轮最核心的业务动作）；大多数轮次（如简短回应、过渡语、问候）应返回 0 个意图
   - **只提取有明确业务意义的动作**（如 verify_identity、offer_loan、decline_offer、inquire_payment）
   - **跳过问候、确认、感谢、道别、客套等非业务性话语**（这些不构成业务意图）
   - **相同类型的动作统一使用同一个 label**，同一条对话中不要为同类动作创建多个不同 label
   - 坐席意图只提取对业务流程有明显推进意义的动作（如 verify_identity、inform_credit_limit、guide_to_borrow）
   - 用户意图侧重其态度和决策（如 agree_to_verify、decline_loan、inquire_installment）
   - 整条对话的意图种类通常不超过 10 个，不要过度细化

3. 关键事实（fact）：不属于槽位值也不属于意图的重要业务陈述（如核实结果、额度说明、政策解释等）

## 输出格式（严格 JSON 数组，只输出 JSON）

[
  {"turn_idx": 0, "class": "slot_value", "label": "槽位名称（英文下划线）", "value": "提取的值"},
  {"turn_idx": 1, "class": "intent", "label": "意图名称（英文动词短语）", "value": "意图的中文描述"},
  {"turn_idx": 2, "class": "fact", "label": "事实标签（英文下划线）", "value": "事实的中文描述"},
  ...
]

## 规范说明

- turn_idx 必须是输入对话行号（0-based），对应输入格式中每行开头的数字
- class 只能是 "slot_value"、"intent" 或 "fact"
- label 使用英文小写下划线命名（如 inquire_monthly_payment、available_credit）
- 意图 label 要精简一致：同类动作复用同一 label，不随措辞变化另起名称
- 只输出 JSON 数组，不加任何说明或 markdown 代码块"""

_DISCOVERY_PERTURN_USER_TEMPLATE = """\
## 业务场景：{scene_name}

## 对话内容（格式：行号 说话人：话语内容）：
{turns_text}

请从上述对话的每一行话语中提取槽位值、意图和关键事实，并标注对应的 turn_idx 行号（只输出 JSON 数组）："""


# ------------------------------------------------------------------
# langextract 逐轮提取辅助
# ------------------------------------------------------------------

# 通用 prompt（开放式，不绑定任何特定场景的槽位/意图列表）
_LANGEXTRACT_PROMPT_TEMPLATE = """\
你是{scene_name}对话的知识提取专家。

从给定的单轮对话话语（坐席或用户均可）中提取结构化知识。
输出为 YAML 列表，每项包含以下字段：
  - extraction_class: 类别，必须是 slot_value / intent / fact 之一
  - extraction_text:  话语中的原始逐字文本片段（verbatim），\
必须是输入话语的精确子串，不得改写或省略
  - attributes.label: 槽位名称 / 意图编码 / 事实标签（英文小写下划线）
  - attributes.value: 提取到的值或自然语言描述

提取规则：
  1. extraction_text 必须是本轮话语的精确子串，不能修改任何字符
  2. 尽可能完整提取话语中所有业务相关信息（金额、期数、利率、姓名、状态等），不遗漏
  3. 若提供了对话历史（additional_context），历史仅供理解上下文用，
     extraction_text 必须来自当前话语，不得截取自历史内容
  4. 同一信息只提取一次，选取最具代表性的文本片段
  5. 若当前话语无可提取信息，输出空列表 []

【槽位（slot_value）—— 话语中涉及的具体业务字段和值，如姓名、金额、期数、利率、状态等】
【意图（intent）—— 说话人表达的业务动作、目标或态度，如询问、拒绝、同意、投诉等】
【事实（fact）—— 不属于槽位值也不属于意图的重要业务陈述，如身份核实结果、额度说明等】"""


def _build_langextract_prompt(scene_name: str) -> str:
    """根据场景名生成 langextract ``prompt_description`` 字符串。"""
    return _LANGEXTRACT_PROMPT_TEMPLATE.format(scene_name=scene_name)


def _build_langextract_examples() -> List[Any]:
    """构建 langextract 逐轮提取所需的 few-shot 示例（``ExampleData`` 列表）。

    每个示例只含一条提取项，且 ``extraction_text`` 与 ``text`` 完全相同，
    避免 langextract 子串对齐失败告警。覆盖 intent、slot_value、fact 三类。
    """
    if not _LANGEXTRACT_AVAILABLE:
        return []
    return [
        ExampleData(
            text="感觉利率有点高",
            extractions=[
                Extraction(
                    extraction_class="intent",
                    extraction_text="感觉利率有点高",
                    attributes={"label": "complain_interest_rate", "value": "用户认为利率偏高"},
                ),
            ],
        ),
        ExampleData(
            text="分十二期",
            extractions=[
                Extraction(
                    extraction_class="slot_value",
                    extraction_text="分十二期",
                    attributes={"label": "term_months", "value": "12"},
                ),
            ],
        ),
        ExampleData(
            text="月供大概多少",
            extractions=[
                Extraction(
                    extraction_class="intent",
                    extraction_text="月供大概多少",
                    attributes={"label": "inquire_monthly_payment", "value": "询问分期月还款额"},
                ),
            ],
        ),
        ExampleData(
            text="暂时不需要",
            extractions=[
                Extraction(
                    extraction_class="intent",
                    extraction_text="暂时不需要",
                    attributes={"label": "decline_offer", "value": "拒绝当前贷款方案"},
                ),
            ],
        ),
    ]


def _build_provenance(
    extraction_text: str,
    turn_idx: int,
    speaker: str,
    char_start: Optional[int],
    char_end: Optional[int],
) -> str:
    """构建单条知识的溯源字符串。

    参数:
        extraction_text: langextract 提取的逐字原文片段
        turn_idx:        对话轮次下标（0-based）
        speaker:         说话人（"坐席" 或 "用户"）
        char_start:      字符区间起始位置（None 表示对齐失败）
        char_end:        字符区间结束位置（None 表示对齐失败）

    返回:
        格式化的溯源字符串
    """
    turn_label = f"第{turn_idx + 1}轮({speaker})"
    if char_start is not None:
        return f"「{extraction_text}」[{turn_label} 位置 {char_start}:{char_end}]"
    return f"「{extraction_text}」[{turn_label} 溯源失败]"


def _parse_turns(normalized_dlg: Dict[str, Any]) -> List[Tuple[int, str, str]]:
    """将归一化对话 dict 拆解为逐轮列表。

    Args:
        normalized_dlg: 经 normalize_dialogue() 处理的 dict，对话历史为配对 dict 列表。

    Returns:
        ``[(turn_idx, speaker, utterance), ...]``，``turn_idx`` 从 0 开始。
    """
    history = normalized_dlg.get("对话历史", [])
    turns: List[Tuple[int, str, str]] = []
    utterance_idx = 0
    for entry in history:
        if isinstance(entry, dict):
            agent_utt = entry.get("机器人", "").strip()
            user_utt = entry.get("用户", "").strip()
            if agent_utt:
                turns.append((utterance_idx, "机器人", agent_utt))
                utterance_idx += 1
            if user_utt:
                turns.append((utterance_idx, "用户", user_utt))
                utterance_idx += 1
    return turns


def _build_history_context(
    turns: List[Tuple[int, str, str]],
    current_list_idx: int,
    context_window: int,
) -> Optional[str]:
    """构建当前轮提取时要传入的历史上下文字符串。

    参数:
        turns:             全部轮次列表
        current_list_idx:  当前轮在列表中的位置（0-based）
        context_window:    历史窗口大小

    返回:
        格式化的历史上下文字符串；若无历史则返回 ``None``
    """
    if context_window <= 0 or current_list_idx == 0:
        return None
    start = max(0, current_list_idx - context_window)
    history = turns[start:current_list_idx]
    if not history:
        return None
    lines = ["[对话历史（供参考，勿从中提取）]"]
    for turn_idx, speaker, utterance in history:
        lines.append(f"第{turn_idx + 1}轮 ({speaker}): {utterance}")
    return "\n".join(lines)


# ------------------------------------------------------------------
# GenericDialogueDiscoverer
# ------------------------------------------------------------------


class GenericDialogueDiscoverer:
    """通用对话发现器：从单条对话中开放式发现槽位、意图和关键事实。

    当 ``langextract`` 已安装时，使用 ``lx.extract()`` 逐轮提取，为每条
    知识附加字符级溯源信息（``DiscoveryItem.provenance``），精确定位知识
    在原始话语中的位置。

    当 ``langextract`` 未安装时，自动降级为纯 LLM 调用模式，提取结果中
    ``provenance=None``，其余字段不变。

    参数
    ----
    llm_client:
        :class:`~contextmind.infra.llm_client.AdkLLMClient` 实例；
        若为 ``None``，从 ``.env`` 自动加载。
    scene_name:
        业务场景名称，用于提示词（如 ``"银行贷款外呼"``）。
    context_window:
        langextract 逐轮提取时，传入 ``additional_context`` 的历史轮次数
        （0 = 不传历史上下文）。仅在 langextract 可用时生效。
    """

    def __init__(
        self,
        llm_client: Optional[AdkLLMClient] = None,
        scene_name: str = "对话场景",
        context_window: int = 3,
    ) -> None:
        if llm_client is None:
            try:
                llm_client = AdkLLMClient(config=LLMConfig.from_env())
            except Exception as exc:
                raise RuntimeError(
                    "LLM 客户端初始化失败，请在 .env 中配置 LLM_API_KEY / "
                    f"LLM_BASE_URL / LLM_MODEL。原始错误: {exc}"
                ) from exc
        self._llm = llm_client
        self.scene_name = scene_name
        self.context_window = context_window

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def extract(self, normalized_dlg: Dict[str, Any]) -> List[DiscoveryItem]:
        """从单条归一化对话中开放式提取槽位值、意图和关键事实。

        参数
        ----
        normalized_dlg:
            归一化后的对话 dict，含 ``"对话历史"`` 字段
            （由 :func:`~contextmind.knowledge.normalizer.normalize_dialogue` 生成）。

        返回
        ----
        :class:`DiscoveryItem` 列表（可能为空）。
        """
        per_turn = self.extract_per_turn(normalized_dlg)
        return [item for _, _, _, items in per_turn for item in items]

    def extract_per_turn(
        self,
        normalized_dlg: Dict[str, Any],
    ) -> List[Tuple[int, str, str, List[DiscoveryItem]]]:
        """逐轮提取，返回每轮的提取结果。

        与 :meth:`extract` 相比，此方法保留每条提取结果对应的轮次信息，
        供生成 SGD 格式对话文件时按轮注释使用。

        使用**单次 LLM 调用**完成全对话提取（按 turn_idx 归位），
        相比原先逐轮 langextract 调用（每轮 1-2 次 LLM）可将调用次数
        从 N 次降至 1 次，大幅提升 build_kb 速度。

        参数
        ----
        normalized_dlg:
            归一化后的对话 dict，含 ``"对话历史"`` 字段。

        返回
        ----
        ``[(turn_idx, speaker, utterance, items), ...]`` 列表，
        每项对应一轮对话及其提取结果。``items`` 可能为空列表。
        """
        turns = _parse_turns(normalized_dlg)
        if not turns:
            return []
        return self._extract_per_turn_with_llm_batch(normalized_dlg, turns)

    # ------------------------------------------------------------------
    # 单批次 LLM 逐轮提取（默认路径，性能最优）
    # ------------------------------------------------------------------

    def _extract_per_turn_with_llm_batch(
        self,
        normalized_dlg: Dict[str, Any],
        turns: List[Tuple[int, str, str]],
    ) -> List[Tuple[int, str, str, List[DiscoveryItem]]]:
        """单次 LLM 调用完成全对话逐轮提取（主路径）。

        将整条对话格式化为带行号的文本，通过**一次** LLM 调用提取所有轮次的
        槽位/意图/事实，并按 ``turn_idx`` 分配到对应轮次。

        相比逐轮 langextract 调用（每条对话 N-2N 次 LLM 调用），此方法将
        调用次数降至 **1 次**，是 build_kb 的关键性能优化。

        参数
        ----
        normalized_dlg:
            归一化后的对话 dict（已解析，此处仅用于格式化文本）。
        turns:
            由 :func:`_parse_turns` 生成的逐轮列表。

        返回
        ----
        ``[(turn_idx, speaker, utterance, items), ...]``，结构与
        :meth:`_extract_per_turn_with_langextract` 完全兼容。
        """
        if not turns:
            return []

        # 格式化带行号的对话文本（行号对应 turn_idx）
        lines = [
            f"{i} {speaker}：{utterance}"
            for i, (turn_idx, speaker, utterance) in enumerate(turns)
        ]
        turns_text = "\n".join(lines)

        user_msg = _DISCOVERY_PERTURN_USER_TEMPLATE.format(
            scene_name=self.scene_name,
            turns_text=turns_text,
        )
        messages = [
            {"role": "system", "content": _DISCOVERY_PERTURN_SYSTEM},
            {"role": "user", "content": user_msg},
        ]

        try:
            response = self._chat_sync(messages)
        except Exception as exc:
            logger.warning(
                f"[GenericDialogueDiscoverer] 单批次 LLM 调用失败，此对话跳过: {exc}"
            )
            return [(t[0], t[1], t[2], []) for t in turns]

        # 解析 per-turn JSON 响应
        n_turns = len(turns)
        turn_items: Dict[int, List[DiscoveryItem]] = {i: [] for i in range(n_turns)}

        raw: Any = None
        try:
            raw = json.loads(response.strip())
        except json.JSONDecodeError:
            content = _strip_code_fences(response)
            try:
                raw = json.loads(content)
            except json.JSONDecodeError:
                m = re.search(r"\[[\s\S]+\]", response)
                if m:
                    try:
                        raw = json.loads(m.group(0))
                    except json.JSONDecodeError:
                        pass

        if isinstance(raw, list):
            for entry in raw:
                if not isinstance(entry, dict):
                    continue
                turn_i = entry.get("turn_idx")
                cls = str(entry.get("class", "")).strip()
                label = str(entry.get("label", "")).strip()
                value = str(entry.get("value", "")).strip()

                if not isinstance(turn_i, int) or turn_i < 0 or turn_i >= n_turns:
                    logger.debug(
                        f"[GenericDialogueDiscoverer] 跳过无效 turn_idx={turn_i!r}: "
                        f"{entry!r}"
                    )
                    continue
                if cls not in ("slot_value", "intent", "fact") or not label:
                    continue

                turn_items[turn_i].append(
                    DiscoveryItem(extraction_class=cls, label=label, value=value)
                )

        total_items = sum(len(v) for v in turn_items.values())
        logger.debug(
            f"[GenericDialogueDiscoverer] 单批次提取结果: "
            f"{total_items} 条（{n_turns} 轮）"
        )

        return [
            (turn_idx, speaker, utterance, turn_items[i])
            for i, (turn_idx, speaker, utterance) in enumerate(turns)
        ]

    # ------------------------------------------------------------------
    # langextract 逐轮提取（保留供特殊用途；默认不再使用）
    # ------------------------------------------------------------------

    def _extract_with_langextract(
        self,
        normalized_dlg: Dict[str, Any],
    ) -> List[DiscoveryItem]:
        """使用 ``lx.extract()`` 逐轮提取，为每条知识附加 ``char_interval`` 溯源。"""
        turns = _parse_turns(normalized_dlg)
        if not turns:
            logger.debug("[GenericDialogueDiscoverer] 对话为空，跳过提取")
            return []
        per_turn = self._extract_per_turn_with_langextract(turns)
        return [item for _, _, _, items in per_turn for item in items]

    def _extract_per_turn_with_langextract(
        self,
        turns: List[Tuple[int, str, str]],
    ) -> List[Tuple[int, str, str, List[DiscoveryItem]]]:
        """逐轮 langextract 提取核心实现，返回每轮 (turn_idx, speaker, utterance, items)。

        对所有轮次（坐席和用户）执行提取；坐席轮次包含大量业务数据（金额、额度、利率等），
        不应跳过。
        """
        adapter = AdkLLMClientAdapter(self._llm)
        prompt_description = _build_langextract_prompt(self.scene_name)
        examples = _build_langextract_examples()

        result: List[Tuple[int, str, str, List[DiscoveryItem]]] = []
        total_aligned = 0

        for list_idx, (turn_idx, speaker, utterance) in enumerate(turns):
            if not utterance.strip():
                result.append((turn_idx, speaker, utterance, []))
                continue

            history_ctx = _build_history_context(turns, list_idx, self.context_window)

            logger.debug(
                f"[GenericDialogueDiscoverer] 第{turn_idx + 1}轮({speaker})"
                f"{' +历史' if history_ctx else ''}: {utterance[:50]}"
            )

            turn_items: List[DiscoveryItem] = []
            try:
                annotated_doc = lx.extract(
                    text_or_documents=utterance,
                    prompt_description=prompt_description,
                    examples=examples,
                    model=adapter,
                    additional_context=history_ctx,
                    max_char_buffer=500,
                    show_progress=False,
                    use_schema_constraints=False,
                )
            except Exception as exc:
                logger.warning(
                    f"[GenericDialogueDiscoverer] 第{turn_idx + 1}轮提取失败: {exc}"
                )
                result.append((turn_idx, speaker, utterance, turn_items))
                continue

            for ext in annotated_doc.extractions:
                cls = str(ext.extraction_class or "").strip()
                extraction_text = str(ext.extraction_text or "").strip()
                attrs = ext.attributes or {}
                label = str(attrs.get("label", cls)).strip()
                value = str(attrs.get("value", extraction_text)).strip()

                if not (cls and label and value and extraction_text):
                    logger.debug(
                        f"[GenericDialogueDiscoverer] 跳过不完整提取: "
                        f"cls={cls!r} label={label!r}"
                    )
                    continue

                char_start: Optional[int] = None
                char_end: Optional[int] = None
                if ext.char_interval is not None:
                    char_start = ext.char_interval.start_pos
                    char_end = ext.char_interval.end_pos
                    total_aligned += 1
                else:
                    # 溯源失败时，尝试在话语中直接搜索 extraction_text 作为兜底
                    idx = utterance.find(extraction_text)
                    if idx >= 0:
                        char_start = idx
                        char_end = idx + len(extraction_text)
                        total_aligned += 1
                        logger.debug(
                            f"[GenericDialogueDiscoverer] 字符串搜索兜底溯源成功: "
                            f"「{extraction_text}」→ {char_start}:{char_end}"
                        )

                provenance = _build_provenance(
                    extraction_text, turn_idx, speaker, char_start, char_end
                )
                turn_items.append(
                    DiscoveryItem(
                        extraction_class=cls,
                        label=label,
                        value=value,
                        provenance=provenance,
                        extraction_text=extraction_text,
                    )
                )

            result.append((turn_idx, speaker, utterance, turn_items))

        total_items = sum(len(items) for _, _, _, items in result)
        logger.debug(
            f"[GenericDialogueDiscoverer] langextract 提取结果: "
            f"{total_items} 条（溯源成功 {total_aligned} 条）"
        )
        return result

    # ------------------------------------------------------------------
    # 纯 LLM 降级路径（langextract 不可用时）
    # ------------------------------------------------------------------

    def _extract_with_llm(
        self,
        normalized_dlg: Dict[str, Any],
    ) -> List[DiscoveryItem]:
        """纯 LLM 整体提取（langextract 不可用时的降级路径）。

        将完整对话（含坐席话语）送给 LLM 以保留上下文，
        但通过 prompt 指示 LLM 仅从用户话语中提取。
        结果不含溯源信息（``provenance=None``）。
        """
        dialogue_text = self._format_dialogue(normalized_dlg)
        if not dialogue_text.strip():
            logger.debug("[GenericDialogueDiscoverer] 对话为空，跳过提取")
            return []

        user_msg = _DISCOVERY_USER_TEMPLATE.format(
            scene_name=self.scene_name,
            dialogue_text=dialogue_text,
        )
        messages = [
            {"role": "system", "content": _DISCOVERY_SYSTEM},
            {"role": "user", "content": user_msg},
        ]

        try:
            response = self._chat_sync(messages)
        except Exception as exc:
            logger.warning(f"[GenericDialogueDiscoverer] LLM 调用失败: {exc}")
            return []

        items = self._parse_llm_response(response)
        logger.debug(
            f"[GenericDialogueDiscoverer] LLM 降级提取结果: "
            f"{sum(1 for i in items if i.extraction_class == 'slot_value')} 个槽位值，"
            f"{sum(1 for i in items if i.extraction_class == 'intent')} 个意图"
        )
        return items

    def _extract_per_turn_with_llm(
        self,
        normalized_dlg: Dict[str, Any],
        turns: List[Tuple[int, str, str]],
    ) -> List[Tuple[int, str, str, List[DiscoveryItem]]]:
        """LLM 降级路径的逐轮版本。

        整体提取后将所有结果附到最后一轮（因无法区分来源轮次）；
        其他各轮 items 为空列表。
        """
        items = self._extract_with_llm(normalized_dlg)
        result: List[Tuple[int, str, str, List[DiscoveryItem]]] = []

        # 将所有提取结果附到最后一轮（兼容：LLM 整体提取无法区分来源轮次）
        last_idx = len(turns) - 1

        for i, (turn_idx, speaker, utterance) in enumerate(turns):
            turn_items = items if i == last_idx else []
            result.append((turn_idx, speaker, utterance, turn_items))
        return result

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _format_dialogue(normalized_dlg: Dict[str, Any]) -> str:
        """将归一化对话 dict 格式化为可读的对话文本（所有轮次）。

        支持新版配对 dict 格式（``{"机器人": "...", "用户": "..."}``）和旧版
        平铺字符串格式（``"机器人：..."`` / ``"用户：..."``）。对 dict 格式使用
        ``机器人：...`` / ``用户：...`` 前缀输出，而非 Python dict repr，确保
        LLM 能正确理解对话内容。
        """
        history = normalized_dlg.get("对话历史", [])
        lines: List[str] = []
        for turn in history:
            if not turn:
                continue
            if isinstance(turn, dict):
                agent = turn.get("机器人", "").strip()
                user = turn.get("用户", "").strip()
                if agent:
                    lines.append(f"机器人：{agent}")
                if user:
                    lines.append(f"用户：{user}")
                if not agent and not user:
                    logger.debug(
                        f"[GenericDialogueDiscoverer] 跳过无有效发言的轮次: "
                        f"{list(turn.keys())}"
                    )
            else:
                s = str(turn).strip()
                if s:
                    lines.append(s)
        return "\n".join(lines)

    @staticmethod
    def _format_user_turns(normalized_dlg: Dict[str, Any]) -> str:
        """将归一化对话 dict 中的用户话语格式化为文本（仅保留用户轮次）。

        支持新版配对 dict 格式（``{"机器人": "...", "用户": "..."}``）和旧版
        平铺字符串格式（``"用户：..."``）。
        """
        history = normalized_dlg.get("对话历史", [])
        lines: List[str] = []
        for turn in history:
            if not turn:
                continue
            if isinstance(turn, dict):
                user = turn.get("用户", "").strip()
                if user:
                    lines.append(f"用户：{user}")
            else:
                s = str(turn).strip()
                if s.startswith("用户：") or s.startswith("用户:"):
                    lines.append(s)
        return "\n".join(lines)

    @staticmethod
    def _parse_llm_response(text: str) -> List[DiscoveryItem]:
        """从纯 LLM 响应中解析 :class:`DiscoveryItem` 列表。"""
        try:
            raw = json.loads(text.strip())
        except json.JSONDecodeError:
            m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
            if m:
                try:
                    raw = json.loads(m.group(1))
                except json.JSONDecodeError:
                    raw = None
            else:
                raw = None
            if raw is None:
                m2 = re.search(r"\[[\s\S]+\]", text)
                if not m2:
                    return []
                try:
                    raw = json.loads(m2.group(0))
                except json.JSONDecodeError:
                    return []

        if not isinstance(raw, list):
            return []

        items: List[DiscoveryItem] = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            cls = entry.get("class", "").strip()
            label = entry.get("label", "").strip()
            value = str(entry.get("value", "")).strip()
            if cls in ("slot_value", "intent", "fact") and label:
                items.append(DiscoveryItem(extraction_class=cls, label=label, value=value))
        return items

    def _chat_sync(self, messages: List[Dict[str, Any]]) -> str:
        """以同步方式调用 LLM 的 chat_async。

        委托给 ``AdkLLMClient.generate()`` 使用的同一套全局共享事件循环机制，
        避免 litellm 的 aiohttp session 因绑定到已关闭的事件循环而抛出
        ``RuntimeError: Task attached to a different loop``。
        """
        import concurrent.futures
        from contextmind.infra.llm_client import _get_shared_loop

        async def _run() -> str:
            return await self._llm.chat_async(messages)

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is not None and running_loop.is_running():
            # 已有运行中的事件循环（如主线程 Jupyter 环境）：在独立线程以 asyncio.run()
            # 执行，该线程拥有全新 loop，不与主线程的 aiohttp 连接池共享
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _run())
                return future.result()
        else:
            # 普通线程（含 ThreadPoolExecutor worker）：使用全局共享持久 loop，
            # 确保所有线程的 litellm 调用均在同一 loop 中执行，消除并发时的
            # "bound to a different event loop" 错误
            fut = asyncio.run_coroutine_threadsafe(_run(), _get_shared_loop())
            return fut.result()
