"""
PyTOD Prompt Builder — 论文原版三步流程提示词构建器

基于 "Task-Oriented Dialogue as Dataflow Synthesis" 和 PyTOD 系列论文，
实现：
    Step 1 — Action Parser (AP): LLM 根据对话历史和 Schema 生成 Python-like 程序
    Step 2 — Execution Engine (EE): 运行程序（见 execution_engine.py）
    Step 3 — Dialogue Manager (DM): LLM 根据执行结果生成自然语言回复

数据结构:
    ConversationTurn: 单条对话历史记录
    PyTODPromptBuilder: 负责构建 AP 和 DM 两阶段的 LLM 消息列表
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from contextmind.modes.pytod.schemas import ServiceSchema


# ---------------------------------------------------------------------------
# ConversationTurn
# ---------------------------------------------------------------------------

@dataclass
class ConversationTurn:
    """单条对话历史记录。

    Attributes:
        role:    说话者角色，``"user"`` 或 ``"assistant"``。
        content: 话语文本。
    """
    role: str    # "user" | "assistant"
    content: str


# ---------------------------------------------------------------------------
# PyTODPromptBuilder
# ---------------------------------------------------------------------------

class PyTODPromptBuilder:
    """PyTOD 两阶段提示词构建器（Action Parser + Dialogue Manager）。

    参数
    ----
    schema : ServiceSchema
        服务 Schema，定义了可用的意图和槽位，约束动作解析器的输出范围。
    max_history_turns : int
        构建提示词时最多包含的历史轮次数（每轮含 user + assistant 各一条）。
    response_language : str
        对话管理器生成回复时使用的语言（嵌入系统指令）。
    """

    _AP_SYSTEM = (
        "你是一个任务型对话的动作解析器（Action Parser）。\n"
        "根据对话历史和当前用户话语，输出一段 PyTOD 程序（Program）。\n\n"
        "## 程序语法规则\n"
        "- 每行格式：`<变量名> <函数调用>`，例如：`x1 query_account()`\n"
        "- 变量名以 x 开头，后接数字，例如 x1、x2\n"
        "- 函数调用可带命名参数，例如：`x2 calculate_repayment(amount=20000, months=12)`\n"
        "- 如需生成系统话术，使用：`say(<变量名>)` 或 `say(<字符串>)`\n"
        "- 如无需调用任何函数，输出：`NONE()`\n\n"
        "## 输出要求\n"
        "- 只输出程序代码，不要解释\n"
        "- 不要加 markdown 代码块（不要用 ``` 包裹）\n"
        "- 每条语句占一行\n"
    )

    _DM_SYSTEM = (
        "你是一个任务型对话的对话管理器（Dialogue Manager）。\n"
        "根据对话历史、用户的最新话语和程序执行结果，生成一条自然语言回复。\n\n"
        "## 回复要求\n"
        "- 直接输出回复文本，不要解释\n"
        "- 准确引用执行结果中的数据（金额、利率等）\n"
        "- 语气友好、专业\n"
        "- 若执行结果为空或 NONE，根据对话情境给出合理回应\n"
    )

    def __init__(
        self,
        schema: ServiceSchema,
        max_history_turns: int = 10,
        response_language: str = "中文",
    ) -> None:
        self.schema = schema
        self.max_history_turns = max_history_turns
        self.response_language = response_language

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #

    def _format_history(self, history: List[ConversationTurn]) -> str:
        """将历史列表格式化为多行文本。"""
        lines = []
        for turn in history[-self.max_history_turns * 2:]:  # 每轮含两条
            prefix = "用户：" if turn.role == "user" else "坐席："
            lines.append(f"{prefix}{turn.content}")
        return "\n".join(lines) if lines else "（无历史）"

    def _schema_summary(self) -> str:
        """生成简洁的 Schema 摘要供 AP 参考。"""
        lines = [f"## 服务：{self.schema.service_name}", ""]
        lines.append("### 可用 API（函数）")
        for intent in self.schema.intents:
            req = ", ".join(intent.required_slots) if intent.required_slots else "无"
            opt = ", ".join(intent.optional_slots) if intent.optional_slots else "无"
            lines.append(f"- {intent.name}({', '.join(intent.required_slots + intent.optional_slots)})")
            lines.append(f"  描述：{intent.description}")
            if intent.required_slots:
                lines.append(f"  必填参数：{req}")
            if intent.optional_slots:
                lines.append(f"  可选参数：{opt}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Action Parser 提示词
    # ------------------------------------------------------------------ #

    def build_action_parser_prompt(
        self,
        history: List[ConversationTurn],
        user_utterance: str,
        scenario_context: str = "",
    ) -> List[Dict[str, str]]:
        """构建动作解析器（AP）的 LLM 消息列表。

        Args:
            history:          当前对话历史（不含本轮用户话语）。
            user_utterance:   本轮用户话语。
            scenario_context: 业务场景描述（可选，嵌入系统指令）。

        Returns:
            可直接传给 ``llm_client.chat_async(messages=...)`` 的消息列表。
        """
        system_parts = [self._AP_SYSTEM]
        if scenario_context:
            system_parts.append(f"## 业务背景\n{scenario_context}")
        system_parts.append(self._schema_summary())
        if self.response_language != "英文":
            system_parts.append(f"\n注意：程序注释和 say() 内容请使用{self.response_language}。")
        system_msg = "\n\n".join(system_parts)

        history_text = self._format_history(history)
        user_msg = (
            f"## 对话历史\n{history_text}\n\n"
            f"## 当前用户话语\n{user_utterance}\n\n"
            "请输出 PyTOD 程序："
        )

        return [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

    # ------------------------------------------------------------------ #
    # Dialogue Manager 提示词
    # ------------------------------------------------------------------ #

    def build_dm_prompt(
        self,
        history: List[ConversationTurn],
        user_utterance: str,
        program: str,
        execution_result: Any,
        scenario_context: str = "",
    ) -> List[Dict[str, str]]:
        """构建对话管理器（DM）的 LLM 消息列表。

        Args:
            history:          当前对话历史（不含本轮用户话语）。
            user_utterance:   本轮用户话语。
            program:          动作解析器生成的 PyTOD 程序文本。
            execution_result: ``ExecutionEngine.execute_program()`` 的返回值
                              （``ProgramExecutionResult`` 或 dict）。
            scenario_context: 业务场景描述（可选，嵌入系统指令）。

        Returns:
            可直接传给 ``llm_client.chat_async(messages=...)`` 的消息列表。
        """
        system_parts = [
            self._DM_SYSTEM,
            f"回复语言：{self.response_language}",
        ]
        if scenario_context:
            system_parts.append(f"\n## 业务背景\n{scenario_context}")
        system_msg = "\n\n".join(system_parts)

        history_text = self._format_history(history)

        # 格式化执行结果
        exec_text = _format_execution_result(execution_result)

        user_msg = (
            f"## 对话历史\n{history_text}\n\n"
            f"## 当前用户话语\n{user_utterance}\n\n"
            f"## PyTOD 程序\n```\n{program}\n```\n\n"
            f"## 程序执行结果\n{exec_text}\n\n"
            "请生成坐席回复："
        )

        return [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _format_execution_result(execution_result: Any) -> str:
    """将 ProgramExecutionResult 或 dict 格式化为可读文本。"""
    if execution_result is None:
        return "（无执行结果）"

    # 支持 ProgramExecutionResult 对象
    if hasattr(execution_result, "success"):
        if not execution_result.success:
            errors = getattr(execution_result, "errors", [])
            return f"执行失败：{'; '.join(str(e) for e in errors)}" if errors else "执行失败"
        var_values = getattr(execution_result, "variable_values", {})
        if not var_values:
            return "（程序执行成功，无变量绑定）"
        import json
        lines = []
        for var, val in var_values.items():
            val_str = json.dumps(val, ensure_ascii=False) if isinstance(val, dict) else str(val)
            lines.append(f"  {var} = {val_str}")
        return "\n".join(lines)

    # 支持 dict
    if isinstance(execution_result, dict):
        import json
        return json.dumps(execution_result, ensure_ascii=False, indent=2)

    return str(execution_result)
