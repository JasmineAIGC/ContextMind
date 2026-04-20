"""
SemanticParser — Genie Worksheets LLM 语义解析器（LLM-1）

将用户输入和当前 Worksheet 状态解析为：
  - 字段赋值（field_name = value）
  - 拒绝 / 无法提取（NONE）

与 Genie 论文对应关系
----------------------
  SemanticParser ≈ Genie "SUQLReActParser"（语义解析部分）

实现差异
--------
  - Genie 原版生成 SUQL 查询；本实现降级为直接字段赋值（不依赖 PostgreSQL）
  - 输出格式为 JSON（更易解析），而非 SUQL 文本
  - 在没有数据库的情况下功能等同于增强版 DST，但受 Worksheet 约束驱动

提示词设计遵循 Genie 论文思路：
  1. 告知当前 Worksheet 状态（已填 / 待填字段）
  2. 要求 LLM 识别用户提供了哪些字段值
  3. 输出 JSON 格式的字段赋值结果
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from contextmind.infra.llm_client import AdkLLMClient
    from contextmind.modes.genie.policy_executor import PolicyExecutor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 语义解析器提示词模板
# ---------------------------------------------------------------------------

_SEMANTIC_PARSING_SYSTEM = """你是一个任务型对话的字段提取器（Field Extractor）。
你的唯一任务是从用户的最新话语中提取业务字段值，填入 Worksheet 表单。

## 工作规则
1. 仅提取用户明确提到的字段值，不要猜测或推断
2. 字段值必须与该字段的类型和可选枚举值匹配
3. 若用户话语中没有任何可提取的字段值，输出 NONE
4. 不要生成与字段无关的内容

## 输出格式
若成功提取到字段值，输出 JSON 对象（不加代码块标记）：
{"field_name_1": "value_1", "field_name_2": "value_2"}

若无法提取任何字段值，仅输出：
NONE

## 重要
- 直接输出 JSON 或 NONE，不要添加任何解释文字
- 枚举字段的值必须精确匹配给定的可选值列表之一
"""

_SEMANTIC_PARSING_USER_TEMPLATE = """\
## 当前 Worksheet 状态
{worksheet_status}

## 待填字段说明
{field_descriptions}

## 对话历史（最近 {history_turns} 轮）
{history}

## 用户最新话语
{user_utterance}

请提取用户话语中的字段值："""


# ---------------------------------------------------------------------------
# SemanticParser
# ---------------------------------------------------------------------------

class SemanticParser:
    """Genie Worksheets 语义解析器（LLM-1）。

    将用户输入解析为 ``{field_name: value}`` 字典或空字典（NONE）。

    参数
    ----
    llm_client :
        ``AdkLLMClient`` 实例，用于调用 LLM。
    max_history_turns :
        构建提示词时包含的最近历史轮次数（默认 5）。
    """

    def __init__(
        self,
        llm_client: "AdkLLMClient",
        max_history_turns: int = 5,
    ) -> None:
        self._llm = llm_client
        self.max_history_turns = max_history_turns

    async def parse(
        self,
        user_utterance: str,
        executor: "PolicyExecutor",
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """解析用户话语，返回字段赋值字典。

        Args:
            user_utterance: 用户本轮输入文本。
            executor:       当前 PolicyExecutor（提供字段描述和状态）。
            history:        对话历史列表 [{"role": "user"|"assistant", "content": "..."}]。

        Returns:
            字段赋值字典 ``{field_name: value}``；无法提取时返回空字典。
        """
        prompt_user = self._build_user_prompt(user_utterance, executor, history or [])

        raw_output = await self._call_llm(
            system=_SEMANTIC_PARSING_SYSTEM,
            user=prompt_user,
        )
        return self._parse_output(raw_output)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _build_user_prompt(
        self,
        user_utterance: str,
        executor: "PolicyExecutor",
        history: List[Dict[str, str]],
    ) -> str:
        """构建语义解析的用户消息。"""
        # Worksheet 当前状态摘要
        state = executor.state
        status_lines: List[str] = []
        for pf in executor._policy_fields:
            if state.is_filled(pf.name):
                status_lines.append(f"  [已填] {pf.name}: {state.get_value(pf.name)!r}")
            else:
                mark = "必填" if pf.required else "可选"
                status_lines.append(f"  [待填/{mark}] {pf.name}")
        worksheet_status = "\n".join(status_lines) or "（无字段）"

        # 待填字段详细描述（给 LLM 参考）
        next_field = executor.next_required_field()
        pending_fields = [
            pf for pf in executor._policy_fields
            if not state.is_filled(pf.name)
        ]
        desc_lines: List[str] = []
        for pf in pending_fields[:8]:  # 最多展示 8 个待填字段
            line = f"  - {pf.name}"
            if pf.description:
                line += f"（{pf.description}）"
            if pf.field_type == "enum" and pf.possible_values:
                line += f" [可选值: {', '.join(pf.possible_values)}]"
            if pf.required:
                line += " *必填*"
            desc_lines.append(line)
        field_descriptions = "\n".join(desc_lines) or "（全部已填）"

        # 对话历史
        recent = history[-self.max_history_turns * 2:]
        hist_lines: List[str] = []
        for turn in recent:
            role = "用户" if turn.get("role") == "user" else "助手"
            hist_lines.append(f"{role}：{turn.get('content', '')}")
        hist_text = "\n".join(hist_lines) or "（无历史）"

        return _SEMANTIC_PARSING_USER_TEMPLATE.format(
            worksheet_status=worksheet_status,
            field_descriptions=field_descriptions,
            history_turns=self.max_history_turns,
            history=hist_text,
            user_utterance=user_utterance,
        )

    async def _call_llm(self, system: str, user: str) -> str:
        """调用 AdkLLMClient 获取 LLM 响应文本。"""
        try:
            # AdkLLMClient 统一接口：generate(messages) 或 chat(system, user)
            if hasattr(self._llm, "chat"):
                response = await self._llm.chat(system_prompt=system, user_message=user)
                return str(response)
            # 通用 messages 格式
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
            if hasattr(self._llm, "generate_async"):
                response = await self._llm.generate_async(messages)
            elif hasattr(self._llm, "generate"):
                import asyncio
                response = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self._llm.generate(messages)
                )
            else:
                logger.error("[SemanticParser] LLM 客户端无可用的调用方法")
                return "NONE"
            return str(response)
        except Exception as exc:
            logger.error(f"[SemanticParser] LLM 调用失败: {exc}")
            return "NONE"

    def _parse_output(self, raw: str) -> Dict[str, Any]:
        """将 LLM 输出解析为字段赋值字典。

        支持：
        - 标准 JSON 对象
        - NONE（无提取结果）
        - 带 markdown 代码块的 JSON（```json ... ```）
        """
        text = raw.strip()
        if not text or text.upper() == "NONE":
            return {}

        # 去除 markdown 代码块
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

        # 提取第一个完整的 JSON 对象
        match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
                if isinstance(result, dict):
                    # 过滤掉 None 值
                    return {k: v for k, v in result.items() if v is not None}
            except json.JSONDecodeError:
                pass

        # 尝试解析整个文本为 JSON
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return {k: v for k, v in result.items() if v is not None}
        except json.JSONDecodeError:
            pass

        logger.debug(f"[SemanticParser] 无法解析 LLM 输出为 JSON: {text[:200]!r}")
        return {}
