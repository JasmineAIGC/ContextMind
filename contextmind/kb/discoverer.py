"""
通用对话发现器（GenericDialogueDiscoverer）

从单条对话中开放式发现槽位（slot_value）和意图（intent），
不依赖任何特定场景的提取器，直接通过 LLM 调用实现。

这是 :class:`~contextmind.kb.builder.KnowledgeBaseBuilder` 的发现阶段实现，
解耦了对 ``contextmind.scenarios.anyihua`` 模块（以及 ``langextract`` 库）的依赖，
使通用知识库构建功能可独立安装和使用。

基本用法::

    from contextmind.kb.discoverer import GenericDialogueDiscoverer
    from contextmind.infra.llm_client import AdkLLMClient

    discoverer = GenericDialogueDiscoverer(
        llm_client=AdkLLMClient(),
        scene_name="银行贷款外呼",
    )
    items = discoverer.extract({"对话历史": ["坐席：你好", "用户：你好"]})
    # items: [DiscoveryItem(extraction_class='slot_value', label='...', value='...'), ...]
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from contextmind.infra.llm_client import AdkLLMClient, LLMConfig
from contextmind.infra.logger import get_logger

logger = get_logger(__name__)

# ------------------------------------------------------------------
# LLM prompt 模板
# ------------------------------------------------------------------

_DISCOVERY_SYSTEM = """\
你是一名任务型对话系统分析专家。给定一段业务对话，请提取其中所有出现的：

1. 槽位值（slot_value）：对话中出现的具体业务字段和值（如姓名、金额、日期、电话号码等）
2. 意图（intent）：说话人表达的业务动作或目标（如核实身份、查询额度、申请贷款、拒绝等）

## 输出格式（严格 JSON 数组，只输出 JSON）

[
  {"class": "slot_value", "label": "槽位名称（英文下划线）", "value": "提取的值"},
  {"class": "intent", "label": "意图名称（英文动词短语）", "value": "意图的中文描述"},
  ...
]

## 规范说明

- class 只能是 "slot_value" 或 "intent"
- label 使用英文小写下划线命名（如 customer_name、verify_identity）
- 只提取真实出现在对话中的内容，不推测未提及的内容
- 尽可能完整，不遗漏重要槽位和意图
- 只输出 JSON 数组，不加任何说明或 markdown 代码块"""

_DISCOVERY_USER_TEMPLATE = """\
## 业务场景：{scene_name}

## 对话内容：
{dialogue_text}

请提取此对话中的槽位值和意图（只输出 JSON 数组）："""


# ------------------------------------------------------------------
# 数据模型
# ------------------------------------------------------------------


@dataclass
class DiscoveryItem:
    """单条开放式发现结果项。

    属性
    ----
    extraction_class:
        ``"slot_value"`` 或 ``"intent"``。
    label:
        槽位/意图名称（英文小写下划线）。
    value:
        提取的值（槽位的具体值，或意图的中文描述）。
    """

    extraction_class: str
    label: str
    value: str


# ------------------------------------------------------------------
# GenericDialogueDiscoverer
# ------------------------------------------------------------------


class GenericDialogueDiscoverer:
    """
    通用对话发现器：从单条对话中开放式发现槽位和意图。

    不依赖任何特定场景的提取器（如 AnyihuaKnowledgeExtractor），
    直接通过 LLM 调用实现。

    参数
    ----
    llm_client:
        :class:`~contextmind.infra.llm_client.AdkLLMClient` 实例；
        若为 None，从 ``.env`` 自动加载。
    scene_name:
        业务场景名称，用于提示词（如 ``"银行贷款外呼"``）。
    """

    def __init__(
        self,
        llm_client: Optional[AdkLLMClient] = None,
        scene_name: str = "对话场景",
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

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def extract(self, normalized_dlg: Dict[str, Any]) -> List[DiscoveryItem]:
        """
        从单条归一化对话中开放式提取槽位值和意图。

        参数
        ----
        normalized_dlg:
            归一化后的对话 dict，含 ``"对话历史"`` 字段
            （由 :func:`~contextmind.kb.normalizer.normalize_dialogue` 生成）。

        返回
        ----
        :class:`DiscoveryItem` 列表（可能为空）。
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

        items = self._parse_response(response)
        logger.debug(
            f"[GenericDialogueDiscoverer] 提取结果: "
            f"{sum(1 for i in items if i.extraction_class == 'slot_value')} 个槽位值，"
            f"{sum(1 for i in items if i.extraction_class == 'intent')} 个意图"
        )
        return items

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _format_dialogue(normalized_dlg: Dict[str, Any]) -> str:
        """将归一化对话 dict 格式化为可读的对话文本。"""
        history = normalized_dlg.get("对话历史", [])
        return "\n".join(str(turn) for turn in history if turn)

    @staticmethod
    def _parse_response(text: str) -> List[DiscoveryItem]:
        """从 LLM 响应中解析 :class:`DiscoveryItem` 列表。"""
        # 直接解析
        try:
            raw = json.loads(text.strip())
        except json.JSONDecodeError:
            # 去掉 markdown 代码块
            m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
            if m:
                try:
                    raw = json.loads(m.group(1))
                except json.JSONDecodeError:
                    raw = None
            else:
                raw = None
            if raw is None:
                # 提取第一个 [ ... ]
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
            if cls in ("slot_value", "intent") and label:
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
