"""
Genie Worksheets AgentActs 层

移植并适配自 stanford-oval/genie-worksheets 的 agent_acts.py，
去除了 GenieField 依赖和 loguru，改用标准 logging。

AgentAct 是 Genie Runtime 在每轮对话结束后生成的"动作指令"，
供 ResponseGenerator（LLM-2）逐条 verbalize 为自然语言回复。

动作类型：
- ``AskAgentAct``                 — 主动询问用户某字段的值
- ``AskForConfirmationAgentAct``  — 请求用户对某字段值进行 yes/no 确认
- ``ReportAgentAct``              — 报告 API 执行结果（on_success 调用结果）
- ``AgentActs``                   — 动作容器，含互斥规则（与 Genie 论文一致）

用法示例::

    from contextmind.modes.genie.agent_acts import (
        AskAgentAct, AskForConfirmationAgentAct, ReportAgentAct, AgentActs
    )
    from contextmind.schema_builder.genie_worksheets.models import PolicyField

    acts = AgentActs()
    pf = PolicyField(name="cuisine", description="菜系", field_type="enum",
                     possible_values=["川菜", "粤菜"], required=True)

    acts.add(AskAgentAct(field=pf))
    acts.add(ReportAgentAct(api_name="search_restaurant",
                            result={"status": "success", "results": []}))
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from contextmind.schema_builder.genie_worksheets.models import PolicyField

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 基类
# ---------------------------------------------------------------------------

class AgentAct:
    """所有 AgentAct 的抽象基类。"""

    def to_prompt_text(self) -> str:
        """返回适合注入 ResponseGenerator 提示词的可读字符串。"""
        return repr(self)


# ---------------------------------------------------------------------------
# AskAgentAct — 主动询问字段
# ---------------------------------------------------------------------------

class AskAgentAct(AgentAct):
    """请求用户提供某字段值的动作。

    Attributes:
        field:       对应的 PolicyField 对象。
        intent_name: 所属意图名称（可选，用于日志）。
    """

    def __init__(
        self,
        field: "PolicyField",
        intent_name: str = "",
    ) -> None:
        self.field = field
        self.intent_name = intent_name

    def __repr__(self) -> str:
        desc = self.field.description or self.field.name
        if self.field.field_type == "enum" and self.field.possible_values:
            opts = ", ".join(self.field.possible_values)
            desc += f"（可选值：{opts}）"
        ws = self.intent_name or "Worksheet"
        return f"AskField({ws}, {self.field.name}, '{desc}')"

    def to_prompt_text(self) -> str:
        return repr(self)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, AskAgentAct):
            return self.field.name == other.field.name
        return False


# ---------------------------------------------------------------------------
# AskForConfirmationAgentAct — 请求确认字段值
# ---------------------------------------------------------------------------

class AskForConfirmationAgentAct(AgentAct):
    """请求用户对已填字段的值进行 yes/no 确认的动作。

    Attributes:
        field:       需要确认的 PolicyField。
        value:       待确认的当前值。
        intent_name: 所属意图名称（可选）。
    """

    def __init__(
        self,
        field: "PolicyField",
        value: Any,
        intent_name: str = "",
    ) -> None:
        self.field = field
        self.value = value
        self.intent_name = intent_name

    def __repr__(self) -> str:
        ws = self.intent_name or "Worksheet"
        return (
            f"AskForFieldConfirmation({ws}, {self.field.name}, {self.value!r})"
        )

    def to_prompt_text(self) -> str:
        return repr(self)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, AskForConfirmationAgentAct):
            return (
                self.field.name == other.field.name
                and self.value == other.value
            )
        return False


# ---------------------------------------------------------------------------
# ReportAgentAct — 报告 API 执行结果
# ---------------------------------------------------------------------------

class ReportAgentAct(AgentAct):
    """报告某次 API 调用结果的动作。

    Attributes:
        api_name:  被调用的 API / on_success 函数名。
        result:    API 返回值（任意可序列化对象）。
        field_name: 触发此次调用的字段名（可选，用于上下文）。
    """

    def __init__(
        self,
        api_name: str,
        result: Any,
        field_name: str = "",
    ) -> None:
        self.api_name = api_name
        self.result = result
        self.field_name = field_name

    def __repr__(self) -> str:
        return f"Report({self.api_name}, {self.result!r})"

    def to_prompt_text(self) -> str:
        return repr(self)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, ReportAgentAct):
            return (
                self.api_name == other.api_name
                and self.result == other.result
            )
        return False


# ---------------------------------------------------------------------------
# AgentActs — 动作容器（含互斥规则，对齐 Genie 论文）
# ---------------------------------------------------------------------------

class AgentActs:
    """动作队列容器，保证每轮只包含语义相容的动作。

    互斥规则（与 Genie 论文对齐）：
    - 一旦队列中有 ``AskAgentAct`` 或 ``AskForConfirmationAgentAct``，
      不再添加其他 Ask 类动作（每轮只问一个字段）。
    - ``ReportAgentAct`` 可以与 Ask 类动作共存（先报告再问）。
    - 同一字段的 Ask 不重复添加。
    """

    def __init__(self) -> None:
        self._actions: List[AgentAct] = []

    def add(self, action: AgentAct) -> bool:
        """尝试添加动作。

        Returns:
            True = 添加成功；False = 因互斥规则拒绝。
        """
        if not self._should_add(action):
            logger.debug(f"[AgentActs] 拒绝添加（互斥规则）: {action!r}")
            return False
        self._actions.append(action)
        return True

    def _should_add(self, incoming: AgentAct) -> bool:
        """检查是否可以添加。"""
        if isinstance(incoming, (AskAgentAct, AskForConfirmationAgentAct)):
            # 已有 Ask 类动作时，不再添加
            for act in self._actions:
                if isinstance(act, (AskAgentAct, AskForConfirmationAgentAct)):
                    return False
        # ReportAgentAct：避免重复报告同一 API
        if isinstance(incoming, ReportAgentAct):
            for act in self._actions:
                if isinstance(act, ReportAgentAct) and act.api_name == incoming.api_name:
                    return False
        return True

    def extend(self, actions: List[AgentAct]) -> None:
        """批量添加动作（遵循互斥规则）。"""
        for action in actions:
            self.add(action)

    def can_ask(self) -> bool:
        """当前队列是否允许继续添加 Ask 类动作。"""
        return not any(
            isinstance(a, (AskAgentAct, AskForConfirmationAgentAct))
            for a in self._actions
        )

    def to_prompt_lines(self) -> List[str]:
        """生成供 ResponseGenerator 提示词使用的动作字符串列表。"""
        return [act.to_prompt_text() for act in self._actions]

    def __iter__(self):
        return iter(self._actions)

    def __len__(self) -> int:
        return len(self._actions)

    def __repr__(self) -> str:
        return f"AgentActs({self._actions!r})"

    @property
    def actions(self) -> List[AgentAct]:
        """只读动作列表。"""
        return list(self._actions)


__all__ = [
    "AgentAct",
    "AskAgentAct",
    "AskForConfirmationAgentAct",
    "ReportAgentAct",
    "AgentActs",
]
