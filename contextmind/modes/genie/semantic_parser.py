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


def _find_first_json_object(text: str) -> Optional[str]:
    """从文本中提取第一个完整的 JSON 对象字符串（支持嵌套大括号）。

    通过逐字符扫描括号深度，正确处理嵌套 JSON，如::

        '{"a": {"b": 1}, "c": 2}'   →  '{"a": {"b": 1}, "c": 2}'

    Args:
        text: 可能含 JSON 的原始文本。

    Returns:
        第一个完整 JSON 对象字符串，未找到时返回 None。
    """
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape_next = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


# ---------------------------------------------------------------------------
# 语义解析器提示词模板（Plan + Extract 两步，对齐 Genie 论文）
# ---------------------------------------------------------------------------

_SEMANTIC_PARSING_SYSTEM = """你是一个任务型对话的字段提取器（Field Extractor）。
你的任务是结合业务背景信息和对话内容，提取业务字段值，填入 Worksheet 表单。

## 输出格式（严格遵循两步结构）
先输出简短的推理分析（不超过 2 句话），再输出提取结果：

# 分析
……（简短分析：从背景信息或用户话语中识别到哪些字段值）……

# 提取结果
若成功提取到字段值，输出 JSON 对象：
{"field_name_1": "value_1", "field_name_2": "value_2"}

若无法提取任何字段值，仅输出：
NONE

## 工作规则
1. 优先从"背景信息"（业务场景与用户预知信息）中提取已知字段值
2. 对话历史或用户当前话语中明确提到的字段值也应提取
3. 字段值必须与该字段的类型和可选枚举值匹配
4. 枚举字段的值必须精确匹配给定的可选值列表之一
5. # 提取结果 之后只输出 JSON 或 NONE，不要添加其他文字
"""

_SEMANTIC_PARSING_USER_TEMPLATE = """\
## 背景信息（业务场景与用户预知信息）
{scene_description}

## 当前 Worksheet 状态
{worksheet_status}

## 待填字段说明
{field_descriptions}

## 对话历史（最近 {history_turns} 轮）
{history}

## 用户最新话语
{user_utterance}

请分析并提取字段值："""


# ---------------------------------------------------------------------------
# SemanticParser
# ---------------------------------------------------------------------------

class SemanticParser:
    """Genie Worksheets 语义解析器（LLM-1）。

    将用户输入解析为 ``{field_name: value}`` 字典或空字典（NONE）。
    采用 Plan+Extract 两步结构：先推理分析，再输出 JSON 提取结果。

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
        scene_description: str = "",
    ) -> Dict[str, Any]:
        """解析用户话语，返回字段赋值字典。

        Args:
            user_utterance:    用户本轮输入文本。
            executor:          当前 PolicyExecutor（提供字段描述和状态）。
            history:           对话历史列表 [{"role": "user"|"assistant", "content": "..."}]。
            scene_description: 业务场景描述及用户预知信息（含 user_info），供 LLM 提取已知字段。

        Returns:
            字段赋值字典 ``{field_name: value}``；无法提取时返回空字典。
        """
        prompt_user = self._build_user_prompt(user_utterance, executor, history or [], scene_description)

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
        scene_description: str = "",
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
            scene_description=scene_description or "（无背景信息）",
            worksheet_status=worksheet_status,
            field_descriptions=field_descriptions,
            history_turns=self.max_history_turns,
            history=hist_text,
            user_utterance=user_utterance,
        )

    async def _call_llm(self, system: str, user: str) -> str:
        """调用 AdkLLMClient 获取 LLM 响应文本。"""
        try:
            # AdkLLMClient 统一接口：优先使用 chat_async（接受 messages 列表）
            if hasattr(self._llm, "chat"):
                response = await self._llm.chat(system_prompt=system, user_message=user)
                return str(response)
            # 通用 messages 格式（OpenAI 标准）
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
            if hasattr(self._llm, "chat_async"):
                # AdkLLMClient.chat_async 接受 List[dict]，是正确的调用方式
                response = await self._llm.chat_async(messages)
            elif hasattr(self._llm, "generate_async"):
                # generate_async 只接受字符串 prompt，不适用于含 system 的 messages
                response = await self._llm.generate_async(user)
            elif hasattr(self._llm, "generate"):
                import asyncio
                response = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self._llm.generate(user)
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

        支持两种输出格式：
        1. Plan+Extract 两步格式（新）：
           ``# 分析\\n...\\n# 提取结果\\n{...}``
        2. 直接 JSON / NONE（旧格式兼容）

        同时支持带 markdown 代码块的 JSON（```json ... ```）。
        """
        text = raw.strip()
        if not text:
            return {}

        # 优先提取 "# 提取结果" 段落（Plan+Extract 格式）
        extract_section = self._extract_result_section(text)
        if extract_section is not None:
            text = extract_section

        if text.upper() == "NONE":
            return {}

        # 去除 markdown 代码块
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

        # 提取第一个完整的 JSON 对象（支持嵌套大括号）
        match = _find_first_json_object(text)
        if match:
            try:
                result = json.loads(match)
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

    @staticmethod
    def _extract_result_section(text: str) -> Optional[str]:
        """从 Plan+Extract 格式输出中提取 '# 提取结果' 段落内容。

        例如::

            # 分析
            用户提供了菜系（川菜）和位置（北京）。

            # 提取结果
            {"cuisine": "川菜", "location": "北京"}

        Returns:
            ``# 提取结果`` 之后的文本（strip 后），未找到时返回 None。
        """
        markers = ["# 提取结果", "# 提取结果：", "## 提取结果", "## 提取结果："]
        for marker in markers:
            idx = text.find(marker)
            if idx != -1:
                return text[idx + len(marker):].strip()
        return None
