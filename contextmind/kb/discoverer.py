"""
通用对话发现器（GenericDialogueDiscoverer）

从单条对话中开放式发现槽位（slot_value）和意图（intent）。
通过 ``langextract`` 为每条提取结果附加字符级**溯源信息**（provenance），
指向知识来源的原始轮次话语位置。

当 ``langextract`` 未安装时，自动降级为纯 LLM 提取模式（``provenance=None``）。

依赖关系
--------
本模块是 ``contextmind.kb`` 的子模块，**仅依赖**：

- ``contextmind.infra.llm_client``（项目基础设施，非业务场景模块）
- ``contextmind.infra.logger``（同上）
- ``langextract``（知识溯源，可选依赖；未安装时自动降级）

不依赖 ``contextmind.modes.*`` 或 ``contextmind.scenarios.*`` 等其他子模块。

基本用法（有 langextract）::

    from contextmind.kb.discoverer import GenericDialogueDiscoverer
    from contextmind.infra.llm_client import AdkLLMClient

    discoverer = GenericDialogueDiscoverer(
        llm_client=AdkLLMClient(),
        scene_name="银行贷款外呼",
    )
    items = discoverer.extract({"对话历史": ["坐席：你好", "用户：你好"]})
    for item in items:
        print(f"[{item.extraction_class}] {item.label}: {item.value}")
        if item.provenance:
            print(f"  溯源: {item.provenance}")

溯源字段格式
-----------
- 溯源成功：``「原文片段」[第N轮(说话人) 位置 start:end]``
- 溯源失败：``「原文片段」[第N轮(说话人) 溯源失败]``
- 降级模式：``None``（langextract 未安装）
"""

from __future__ import annotations

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

    属性
    ----
    extraction_class:
        ``"slot_value"``、``"intent"`` 或 ``"fact"``。
    label:
        槽位/意图名称（英文小写下划线）。
    value:
        提取的值（槽位的具体值，或意图的中文描述）。
    provenance:
        原文溯源字符串；仅在 ``langextract`` 可用时填充。格式：

        - 溯源成功：``「原文片段」[第N轮(说话人) 位置 start:end]``
        - 溯源失败：``「原文片段」[第N轮(说话人) 溯源失败]``
        - 降级模式：``None``
    """

    extraction_class: str
    label: str
    value: str
    provenance: Optional[str] = None


# ------------------------------------------------------------------
# langextract 适配器（langextract 可用时有效）
# ------------------------------------------------------------------


def _sanitize_infer_yaml(text: str) -> str:
    """清洗 LLM 返回的 YAML/JSON 文本，过滤掉 ``extraction_text`` 为 None/null/空字符串的条目。

    langextract ``resolver.py`` 在解析 LLM 输出时，若遇到 ``extraction_text`` 不是
    ``str / int / float`` 类型（例如 YAML ``null``），会触发：
      ``ERROR:absl:Extraction text must be a string, integer, or float.``
    并抛出 ``ValueError``。通过此函数提前过滤无效条目，可完全消除该错误日志。

    若 YAML 解析失败，原样返回输入文本（best-effort）。
    """
    try:
        import yaml  # type: ignore[import]
        items = yaml.safe_load(text)
        if not isinstance(items, list):
            return text
        cleaned = []
        for item in items:
            if not isinstance(item, dict):
                continue
            et = item.get("extraction_text")
            if not isinstance(et, (str, int, float)):
                logger.debug(
                    "[AdkLLMClientAdapter] 过滤 extraction_text 无效条目 "
                    "(类型=%s): %r",
                    type(et).__name__,
                    item,
                )
                continue
            if isinstance(et, str) and not et.strip():
                logger.debug(
                    "[AdkLLMClientAdapter] 过滤 extraction_text 为空字符串的条目: %r",
                    item,
                )
                continue
            cleaned.append(item)
        if not cleaned:
            return "[]"
        return yaml.dump(cleaned, allow_unicode=True, default_flow_style=False)
    except Exception:
        return text


class AdkLLMClientAdapter(BaseLanguageModel):  # type: ignore[misc]
    """将 :class:`~contextmind.infra.llm_client.AdkLLMClient` 适配为
    langextract ``BaseLanguageModel`` 接口。

    通过此适配器，可将现有的 ADK/OpenAI 兼容 LLM 端点无缝接入
    ``lx.extract()`` 的完整提取管道（Annotator → Resolver → WordAligner
    → ``char_interval``），而无需切换到 Gemini 内置模型。

    参数:
        client: 已初始化的 :class:`~contextmind.infra.llm_client.AdkLLMClient` 实例
    """

    def __init__(self, client: AdkLLMClient) -> None:
        super().__init__()
        self._client = client

    def infer(
        self,
        batch_prompts: Sequence[str],
        **kwargs: Any,
    ) -> Iterator[Sequence[Any]]:
        """实现 langextract ``BaseLanguageModel.infer()`` 接口。

        逐条处理 ``batch_prompts``，调用 ``AdkLLMClient.generate()`` 获取响应，
        并包装为 ``ScoredOutput(score=1.0, output=text)``。

        参数:
            batch_prompts: 待推理的 prompt 列表
            **kwargs:      预留参数（当前忽略）

        Yields:
            每个 prompt 对应一个 ``[ScoredOutput]`` 列表
        """
        if not _LANGEXTRACT_AVAILABLE:  # pragma: no cover
            raise RuntimeError("langextract 未安装，无法使用 AdkLLMClientAdapter")
        for prompt in batch_prompts:
            try:
                _reasoning, text = self._client.generate(prompt)
                if not text.strip():
                    # 空响应返回合法空列表，避免 langextract 内部 JSON 解析异常
                    logger.debug("[AdkLLMClientAdapter] LLM 返回空响应，本轮无提取结果")
                    yield [ScoredOutput(score=0.0, output="[]")]
                else:
                    # 过滤掉 extraction_text 为 None/null/非字符串的条目，
                    # 防止 langextract resolver 因类型校验失败而抛出 ValueError
                    # 并触发 ERROR:absl:Extraction text must be a string... 错误日志。
                    sanitized = _sanitize_infer_yaml(text)
                    yield [ScoredOutput(score=1.0, output=sanitized)]
            except Exception as exc:
                logger.warning(f"[AdkLLMClientAdapter] LLM 推理失败: {exc}")
                yield [ScoredOutput(score=0.0, output="[]")]


# ------------------------------------------------------------------
# LLM prompt 模板（纯 LLM 降级模式）
# ------------------------------------------------------------------

_DISCOVERY_SYSTEM = """\
你是一名任务型对话系统分析专家。给定一段业务对话，请提取其中所有出现的：

1. 槽位值（slot_value）：对话中出现的具体业务字段和值（如姓名、金额、日期、电话号码等）
2. 意图（intent）：说话人表达的业务动作或目标（如核实身份、查询额度、申请贷款、拒绝等）
3. 关键事实（fact）：不属于槽位值也不属于意图的重要业务陈述

## 输出格式（严格 JSON 数组，只输出 JSON）

[
  {"class": "slot_value", "label": "槽位名称（英文下划线）", "value": "提取的值"},
  {"class": "intent", "label": "意图名称（英文动词短语）", "value": "意图的中文描述"},
  {"class": "fact", "label": "事实标签（英文下划线）", "value": "事实的中文描述"},
  ...
]

## 规范说明

- class 只能是 "slot_value"、"intent" 或 "fact"
- label 使用英文小写下划线命名（如 customer_name、verify_identity）
- 只提取真实出现在对话中的内容，不推测未提及的内容
- 尽可能完整，不遗漏重要槽位和意图
- 只输出 JSON 数组，不加任何说明或 markdown 代码块"""

_DISCOVERY_USER_TEMPLATE = """\
## 业务场景：{scene_name}

## 对话内容：
{dialogue_text}

请提取此对话中的槽位值、意图和关键事实（只输出 JSON 数组）："""


# ------------------------------------------------------------------
# langextract 逐轮提取辅助
# ------------------------------------------------------------------

# 通用 prompt（开放式，不绑定任何特定场景的槽位/意图列表）
_LANGEXTRACT_PROMPT_TEMPLATE = """\
你是{scene_name}对话的知识提取专家。

从给定的单轮对话话语中提取结构化知识。
输出为 YAML 列表，每项包含以下字段：
  - extraction_class: 类别，必须是 slot_value / intent / fact 之一
  - extraction_text:  话语中的原始逐字文本片段（verbatim），\
必须是输入话语的精确子串，不得改写或省略
  - attributes.label: 槽位名称 / 意图编码 / 事实标签（英文小写下划线）
  - attributes.value: 提取到的值或自然语言描述

提取规则：
  1. extraction_text 必须是本轮话语的精确子串，不能修改任何字符
  2. 仅提取当前话语中明确出现的信息，不推断、不猜测
  3. 若提供了对话历史（additional_context），历史仅供理解上下文用，
     extraction_text 必须来自当前话语，不得截取自历史内容
  4. 同一信息只提取一次，选取最具代表性的文本片段
  5. 若当前话语无可提取信息，输出空列表 []

【槽位（slot_value）—— 对话中涉及的具体业务信息，如姓名、金额、日期等，自行命名 label】
【意图（intent）—— 说话人表达的业务动作或目标，自行命名 label】
【事实（fact）—— 不属于槽位值也不属于意图的重要业务陈述，自行命名 label】"""


def _build_langextract_prompt(scene_name: str) -> str:
    """根据场景名生成 langextract ``prompt_description`` 字符串。"""
    return _LANGEXTRACT_PROMPT_TEMPLATE.format(scene_name=scene_name)


def _build_langextract_examples() -> List[Any]:
    """构建 langextract 逐轮提取所需的 few-shot 示例（``ExampleData`` 列表）。

    ``lx.extract()`` 要求至少一个 ``ExampleData`` 对象，每个示例中的
    ``extraction_text`` 必须是 ``text`` 的精确子串（verbatim）。

    此处提供三条通用中文业务对话示例，覆盖三种提取类别：
    - ``slot_value``：具体业务字段值
    - ``intent``：说话人意图
    - ``fact``：重要业务事实
    """
    if not _LANGEXTRACT_AVAILABLE:
        return []
    return [
        ExampleData(
            text="您好，请问是李先生吗？",
            extractions=[
                Extraction(
                    extraction_class="intent",
                    extraction_text="请问是李先生吗",
                    attributes={"label": "verify_identity", "value": "核实用户身份"},
                ),
            ],
        ),
        ExampleData(
            text="可用额度是五万元，年化利率十二个百分点",
            extractions=[
                Extraction(
                    extraction_class="slot_value",
                    extraction_text="可用额度是五万元",
                    attributes={"label": "available_credit", "value": "五万元"},
                ),
                Extraction(
                    extraction_class="slot_value",
                    extraction_text="年化利率十二个百分点",
                    attributes={"label": "annual_rate", "value": "十二个百分点"},
                ),
            ],
        ),
        ExampleData(
            text="分十二期每月还款约四千四百三十一元。",
            extractions=[
                Extraction(
                    extraction_class="fact",
                    extraction_text="分十二期每月还款约四千四百三十一元",
                    attributes={"label": "repayment_plan", "value": "12期月供4431元"},
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

    返回:
        ``[(turn_idx, speaker, utterance), ...]``，``turn_idx`` 从 0 开始。
    """
    history = normalized_dlg.get("对话历史", [])
    turns: List[Tuple[int, str, str]] = []
    for idx, line in enumerate(history):
        line = str(line).strip()
        if not line:
            continue
        if line.startswith("坐席：") or line.startswith("坐席:"):
            speaker = "坐席"
            utterance = re.sub(r"^坐席[：:]\s*", "", line)
        elif line.startswith("用户：") or line.startswith("用户:"):
            speaker = "用户"
            utterance = re.sub(r"^用户[：:]\s*", "", line)
        else:
            # 英文前缀兜底
            m = re.match(
                r"^(agent|system|assistant)\s*[：:]\s*(.+)$", line, re.IGNORECASE
            )
            if m:
                speaker = "坐席"
                utterance = m.group(2)
            else:
                m2 = re.match(
                    r"^(user|human|customer)\s*[：:]\s*(.+)$", line, re.IGNORECASE
                )
                if m2:
                    speaker = "用户"
                    utterance = m2.group(2)
                else:
                    speaker = "未知"
                    utterance = line
        if utterance.strip():
            turns.append((idx, speaker, utterance))
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

        当 ``langextract`` 可用时，采用逐轮提取模式，每条结果均附带溯源信息。
        当 ``langextract`` 不可用时，采用纯 LLM 整体提取，结果无溯源信息。

        参数
        ----
        normalized_dlg:
            归一化后的对话 dict，含 ``"对话历史"`` 字段
            （由 :func:`~contextmind.kb.normalizer.normalize_dialogue` 生成）。

        返回
        ----
        :class:`DiscoveryItem` 列表（可能为空）。
        """
        if _LANGEXTRACT_AVAILABLE:
            return self._extract_with_langextract(normalized_dlg)
        return self._extract_with_llm(normalized_dlg)

    def extract_per_turn(
        self,
        normalized_dlg: Dict[str, Any],
    ) -> List[Tuple[int, str, str, List[DiscoveryItem]]]:
        """逐轮提取，返回每轮的提取结果。

        与 :meth:`extract` 相比，此方法保留每条提取结果对应的轮次信息，
        供生成 SGD 格式对话文件时按轮注释使用。

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

        if _LANGEXTRACT_AVAILABLE:
            return self._extract_per_turn_with_langextract(turns)
        return self._extract_per_turn_with_llm(normalized_dlg, turns)

    # ------------------------------------------------------------------
    # langextract 逐轮提取（推荐路径）
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
        """逐轮 langextract 提取核心实现，返回每轮 (turn_idx, speaker, utterance, items)。"""
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

                provenance = _build_provenance(
                    extraction_text, turn_idx, speaker, char_start, char_end
                )
                turn_items.append(
                    DiscoveryItem(
                        extraction_class=cls,
                        label=label,
                        value=value,
                        provenance=provenance,
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

        整体提取后将所有结果附到最后一轮（因无法区分来源轮次），
        其他各轮 items 为空列表。
        """
        items = self._extract_with_llm(normalized_dlg)
        result: List[Tuple[int, str, str, List[DiscoveryItem]]] = []
        for i, (turn_idx, speaker, utterance) in enumerate(turns):
            # 将所有提取结果附到最后一轮
            turn_items = items if i == len(turns) - 1 else []
            result.append((turn_idx, speaker, utterance, turn_items))
        return result

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _format_dialogue(normalized_dlg: Dict[str, Any]) -> str:
        """将归一化对话 dict 格式化为可读的对话文本。"""
        history = normalized_dlg.get("对话历史", [])
        return "\n".join(str(turn) for turn in history if turn)

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
        """以同步方式调用 LLM 的 chat_async。"""
        import asyncio
        import concurrent.futures

        async def _run() -> str:
            return await self._llm.chat_async(messages)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _run())
                return future.result()
        else:
            return asyncio.run(_run())
