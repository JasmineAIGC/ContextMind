"""
PyTOD Prompt Builder — 论文原版三步流程提示词构建器

基于论文 "PyTOD: Programmable Task-Oriented Dialogue with Execution Feedback"
（官方代码：https://github.com/apple/ml-pytod），实现：
    Step 1 — Action Parser (AP): LLM 根据对话历史和 Schema 生成 PyTOD 程序
    Step 2 — Execution Engine (EE): 运行程序（见 execution_engine.py）
    Step 3 — Dialogue Manager (DM): LLM 根据程序 + 执行结果生成自然语言回复

与官方实现的关键对齐点：
    - AP prompt 展示实际可调用的函数签名（来自 ExecutionEngine），而非 schema 意图名
    - Schema 意图描述作为业务上下文辅助 LLM 选择正确函数
    - say() 是 AP 和 DM 之间的信息接口；DM 以 say() 输出内容为核心生成回复
    - 支持完整 PyTOD 程序语法：Hint、say(x1.attr)、confirm、perform、分号多槽位赋值

数据结构:
    ConversationTurn: 单条对话历史记录
    PyTODPromptBuilder: 负责构建 AP 和 DM 两阶段的 LLM 消息列表
"""

from __future__ import annotations

import json
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

    与官方 PyTOD 实现的对齐：
    - AP 提示词优先展示 ``engine.to_prompt_text()`` 中的实际函数签名，
      保证 AP 输出的函数名与 ExecutionEngine 注册名完全一致。
    - Schema 意图描述作为业务上下文，帮助 LLM 理解每个函数的业务语义。
    - DM 提示词将 AP 生成的 say() 输出内容置于首位，引导 DM 准确传达
      AP 指定的关键信息（金额、数据等）。

    参数
    ----
    schema : ServiceSchema
        服务 Schema，提供意图和槽位的业务描述，辅助 AP 选择正确函数。
    api_signatures : str
        可注入 AP 提示词的实际 API 函数签名文本，通常由
        ``ExecutionEngine.to_prompt_text()`` 生成。为空时回退到 schema 意图名。
    max_history_turns : int
        构建提示词时最多包含的历史轮次数（每轮含 user + assistant 各一条）。
    response_language : str
        对话管理器生成回复时使用的语言（嵌入系统指令）。
    """

    # ------------------------------------------------------------------ #
    # AP 系统提示词
    # ------------------------------------------------------------------ #
    _AP_SYSTEM = (
        "你是一个任务型对话的动作解析器（Action Parser）。\n"
        "根据对话历史和当前用户话语，输出一段 PyTOD 程序。\n\n"
        "## 程序语法规则\n"
        "每条语句一行，格式如下：\n\n"
        "  变量绑定 API 调用：\n"
        "    x1 func_name(param='value')          # 调用注册函数，结果绑定到 x1\n\n"
        "  槽位赋值（支持同行分号分隔多个槽位）：\n"
        "    x1.slot = 'value'                    # 为 x1 的参数赋值\n"
        "    x1.a = 'v1'; x1.b = 'v2'            # 多槽位同行赋值\n\n"
        "  请求缺失信息（Hint）：\n"
        "    x2 Hint('request value: slot_name')  # 提示 DM 需要向用户询问的信息\n\n"
        "  组合输出（say）：\n"
        "    x3 say(x1, x2)                       # 传递变量整体值\n"
        "    x3 say(x1.field_name, x2)            # 传递变量的某个字段\n"
        "    x3 say('literal text')               # 直接传递字符串字面量\n"
        "    x3 say()                             # 空 say，结束对话\n\n"
        "  事务型 API（需要用户确认后再执行）：\n"
        "    x4 confirm(x1)                       # 向 DM 返回 x1 的待确认参数\n"
        "    x5 perform(x1)                       # 用 x1 的参数实际执行 API\n\n"
        "  暂停等待：\n"
        "    x6 conversation_pause()              # 暂停，等待用户下一步操作\n\n"
        "  无需调用任何 API：\n"
        "    NONE()                               # 本轮不需要任何函数调用\n\n"
        "## 输出要求\n"
        "- 只输出程序代码，不要任何解释\n"
        "- 不要加 markdown 代码块（禁止用 ``` 包裹）\n"
        "- 每条语句独占一行\n"
        "- 函数名必须与「可调用 API 函数」中列出的名称完全一致\n"
        "- 新变量编号必须严格遵守「新变量编号约束」中的起始编号，不得使用已被占用的编号\n"
        "- say() 指定「本轮 DM 应向用户传达的具体内容」\n"
        "- 若「业务背景」中已明确提供了所需数据（如用户额度、利率、账单日等），"
        "直接在 say() 中引用这些已知数据，无需再次调用查询 API\n"
    )

    # ------------------------------------------------------------------ #
    # DM 系统提示词
    # ------------------------------------------------------------------ #
    _DM_SYSTEM = (
        "你是一个任务型对话的对话管理器（Dialogue Manager）。\n"
        "根据对话历史、用户的最新话语和程序执行结果，生成一条自然语言回复。\n\n"
        "## 回复要求\n"
        "- 若执行结果中包含「AP 指定的 say 输出」，必须以该内容为核心进行回复，"
        "不得遗漏其中的关键数据（金额、利率、日期等）\n"
        "- 若执行结果包含 Hint 提示，在回复中自然地向用户询问对应信息\n"
        "- 若执行结果包含 confirm 确认请求，向用户朗读待确认的参数，请求用户确认\n"
        "- 准确引用执行结果中的数据，禁止自行估算或捏造数字\n"
        "- 若执行失败，根据错误信息给出合理的回应或引导用户重新提供信息\n"
        "- 若程序为 NONE() / conversation_pause() 或无执行结果，根据对话历史给出合理的纯语言回应\n"
        "- 直接输出回复文本，不要任何前缀或解释\n"
        "- 语气友好、专业\n"
    )

    def __init__(
        self,
        schema: ServiceSchema,
        api_signatures: str = "",
        max_history_turns: int = 10,
        response_language: str = "中文",
        compact_schema: bool = False,
    ) -> None:
        self.schema = schema
        self._api_signatures = api_signatures
        self.max_history_turns = max_history_turns
        self.response_language = response_language
        self.compact_schema = compact_schema

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #

    def _format_history(self, history: List[ConversationTurn]) -> str:
        """将历史列表格式化为多行文本。"""
        lines = []
        # max_history_turns 轮 × 2 = 每轮含 user + assistant 各一条
        for turn in history[-self.max_history_turns * 2:]:
            prefix = "用户：" if turn.role == "user" else "机器人："
            lines.append(f"{prefix}{turn.content}")
        return "\n".join(lines) if lines else "（无历史）"

    def _build_api_signatures(self) -> str:
        """构建函数签名部分（不含业务意图描述）。

        用于静态系统指令 — AP 选函数时的权威来源。
        ``compact_schema=True`` 时 ``api_signatures`` 由 tracker 传入紧凑版（仅函数名），
        因此此方法无需特殊处理，直接输出 ``api_signatures`` 即可。

        当 ``api_signatures`` 为空（未传入 engine）时，回退到展示 schema 意图名称。
        """
        lines: List[str] = []
        if self._api_signatures:
            lines.append("## 可调用 API 函数（程序中的函数名必须与此处完全一致）")
            lines.append(self._api_signatures)
        else:
            # 回退：以 schema 意图名作为函数名（准确性较低，仅作兜底）
            if self.schema.intents:
                lines.append("## 可调用 API 函数")
                for intent in self.schema.intents:
                    params = intent.required_slots + intent.optional_slots
                    lines.append(
                        f"  - {intent.name}({', '.join(params)})"
                        f"  # {intent.description[:60]}"
                    )
        return "\n".join(lines)

    def _build_intent_context(self) -> str:
        """构建业务意图描述部分，用于每轮动态注入用户消息。

        将意图描述从静态系统消息移至动态用户消息，实现「动态加载」：
        - 系统消息保持轻量（仅规则 + 函数名称），可被 ADK 高效缓存。
        - 用户消息每轮包含完整意图描述，未来可按对话状态筛选相关意图。

        ``compact_schema=True`` 时返回空字符串（省略意图描述，最小化 token）。
        """
        if not self.schema.intents or self.compact_schema:
            return ""
        lines = [f"## 业务场景说明（服务：{self.schema.service_name}）"]
        lines.append(f"服务描述：{self.schema.description}")
        lines.append("")
        for intent in self.schema.intents:
            lines.append(f"- **{intent.name}**：{intent.description}")
        return "\n".join(lines)

    def _build_api_context(self) -> str:
        """构建完整 API 上下文块（函数签名 + 意图描述）。

        保留此方法供向后兼容（非 ADK 回退路径的系统消息仍可使用）。
        ADK 路径中：函数签名在系统消息，意图描述已移至用户消息（动态加载）。
        """
        sig = self._build_api_signatures()
        intent = self._build_intent_context()
        if sig and intent:
            return sig + "\n\n" + intent
        return sig or intent

    # ------------------------------------------------------------------ #
    # Action Parser 提示词
    # ------------------------------------------------------------------ #

    def build_action_parser_prompt(
        self,
        history: List[ConversationTurn],
        user_utterance: str,
        scenario_context: str = "",
        prior_dataflow: Optional[Dict[str, Any]] = None,
        next_var_index: int = 1,
    ) -> List[Dict[str, str]]:
        """构建动作解析器（AP）的 LLM 消息列表。

        AP 提示词结构（优化版 — 静态/动态分离）：

        **系统消息（静态，跨轮不变）**：
        1. 语法规则（AP system）
        2. 业务背景（可选）
        3. 函数签名（AP 必须使用的名称，``compact_schema=True`` 时仅函数名）
        4. 语言设置

        **用户消息（动态，每轮更新）**：
        5. 对话历史
        6. 业务意图描述（从系统消息移至此处 — 动态加载；``compact_schema=True`` 时省略）
        7. 已计算变量（官方 PyTOD dataflow context）
        8. 当前用户话语

        分离设计的优势：
        - 系统消息更短，有利于 LLM 缓存（KV-cache）复用。
        - 意图描述位于用户消息，天然支持按对话状态动态筛选（未来扩展点）。

        Args:
            history:          当前对话历史（不含本轮用户话语）。
            user_utterance:   本轮用户话语。
            scenario_context: 业务场景描述（可选，嵌入系统指令）。
            prior_dataflow:   先前轮次中已计算的变量绑定字典
                              ``{var_name: result_value}``；为 None 或空时不注入。
            next_var_index:   本轮程序中第一个新变量应使用的编号（全局递增）。

        Returns:
            可直接传给 ``llm_client.chat_async(messages=...)`` 的消息列表。
        """
        # ── 系统消息：静态规则 + 函数签名（轻量，有助于 KV-cache 复用）──────────
        system_parts = [self._AP_SYSTEM]
        if scenario_context:
            system_parts.append(f"## 业务背景\n{scenario_context}")
        system_parts.append(self._build_api_signatures())   # 仅签名，不含意图描述
        if self.response_language != "英文":
            system_parts.append(
                f"\n注意：Hint 内容和 say() 字符串字面量请使用{self.response_language}。"
            )
        system_msg = "\n\n".join(system_parts)

        # ── 用户消息：每轮动态内容 ──────────────────────────────────────────
        history_text = self._format_history(history)
        dataflow_section = _format_prior_dataflow(prior_dataflow, next_var_index)

        # 意图描述：动态注入用户消息（系统消息已不再包含），
        # 未来可调用 _build_intent_context(user_utterance) 实现按轮筛选。
        intent_ctx = self._build_intent_context()

        user_msg = f"## 对话历史\n{history_text}\n\n"
        if intent_ctx:
            user_msg += intent_ctx + "\n\n"
        user_msg += dataflow_section
        user_msg += f"## 当前用户话语\n{user_utterance}\n\n请输出 PyTOD 程序："

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

        DM 提示词结构（与官方 PyTOD 对齐）：
        1. DM system（含 say() 优先原则）
        2. 业务背景（可选）
        3. 对话历史 + 用户话语 + 程序 + 执行结果（user turn）

        say() 输出优先规则：官方 PyTOD 以 say() 作为 AP 和 DM 之间的信息接口，
        AP 通过 say(x1, x2) 明确指定"本轮要传达哪些信息"，DM 必须以此为核心生成回复。

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
        # 注意：DM 系统提示词不再包含 scenario_context（业务背景/用户信息），
        # 避免每轮重复注入大体积文本造成 token 浪费和延迟上升。
        # DM 所需的全部业务数据已通过对话历史和程序执行结果传入。
        system_msg = "\n\n".join(system_parts)

        history_text = self._format_history(history)
        exec_text = _format_execution_result(execution_result)

        user_msg = (
            f"## 对话历史\n{history_text}\n\n"
            f"## 当前用户话语\n{user_utterance}\n\n"
            f"## AP 生成程序\n```\n{program}\n```\n\n"
            f"## 程序执行结果\n{exec_text}\n\n"
            "请生成机器人回复："
        )

        return [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _format_prior_dataflow(
    prior_dataflow: Optional[Dict[str, Any]],
    next_var_index: int = 1,
) -> str:
    """将先前轮次的已计算变量格式化为 AP prompt 的 dataflow context 节。

    对应官方 PyTOD 的设计：AP 在每轮都能看到本对话中已通过 API 获取的所有变量，
    从而可以直接引用 ``x1.field`` 而无需重新查询，变量编号在整个对话中全局递增。

    Args:
        prior_dataflow: 先前轮次的变量绑定字典 ``{var_name: value}``。
        next_var_index: 本轮程序中第一个新变量应使用的编号。

    Returns:
        格式化好的节文本（含末尾两个换行），若无先前变量则返回空字符串。
    """
    if not prior_dataflow:
        if next_var_index > 1:
            forbidden = next_var_index - 1
            return (
                f"## 新变量编号约束\n"
                f"【重要】本轮新变量必须从 x{next_var_index} 开始编号"
                f"（x1～x{forbidden} 已被占用，绝对禁止重复使用）。\n\n"
            )
        return ""

    _MAX_VAL_LEN = 300
    lines = ["## 已计算变量（本对话中已通过 API 获取的数据，可直接引用 xN.field）"]
    for var, val in prior_dataflow.items():
        if var.startswith("_"):  # 跳过内部元数据键
            continue
        try:
            val_str = json.dumps(val, ensure_ascii=False)
        except (TypeError, ValueError):
            val_str = str(val)
        if len(val_str) > _MAX_VAL_LEN:
            val_str = val_str[:_MAX_VAL_LEN] + "…（已截断）"
        lines.append(f"  {var} = {val_str}")
    forbidden = next_var_index - 1
    lines.append(
        f"【重要】本轮新变量必须从 x{next_var_index} 开始编号"
        f"（x1～x{forbidden} 已被占用，绝对禁止重复使用）；"
        "已有变量可直接用 xN.field 引用，无需重复调用 API"
    )
    return "\n".join(lines) + "\n\n"


def _format_execution_result(execution_result: Any) -> str:
    """将 ProgramExecutionResult 或 dict 格式化为可读文本。

    say() 输出内容置于首位，使 DM 优先关注 AP 明确指定的输出信息。
    """
    if execution_result is None:
        return "（无执行结果）"

    # 支持 ProgramExecutionResult 对象
    if hasattr(execution_result, "success"):
        if not execution_result.success:
            errors = getattr(execution_result, "errors", [])
            return f"执行失败：{'; '.join(str(e) for e in errors)}" if errors else "执行失败"

        lines: List[str] = []

        # 1. say() 输出：AP 明确指定"本轮要向用户传达的内容"，置于最前
        say_output: str = getattr(execution_result, "say_output", "")
        if say_output:
            lines.append(f"【AP 指定的 say 输出（DM 必须以此为核心回复）】\n{say_output}")

        # 2. Hint 提示
        hints: List[str] = getattr(execution_result, "hint_messages", [])
        if hints:
            lines.append("【Hint 提示（DM 需向用户询问的信息）】")
            for h in hints:
                lines.append(f"  - {h}")

        # 3. API 调用结果（过滤掉 say() 变量，避免重复）
        var_values: Dict[str, Any] = getattr(execution_result, "variable_values", {})
        say_variable_names: set = getattr(execution_result, "say_variable_names", set())
        api_vars = {
            k: v for k, v in var_values.items()
            if k not in say_variable_names and not k.startswith("_anon")
        }
        if api_vars:
            lines.append("【API 调用结果】")
            for var, val in api_vars.items():
                try:
                    val_str = json.dumps(val, ensure_ascii=False)
                except (TypeError, ValueError):
                    val_str = str(val)
                lines.append(f"  {var} = {val_str}")

        return "\n".join(lines) if lines else "（程序执行成功，无返回数据）"

    # 支持 dict
    if isinstance(execution_result, dict):
        return json.dumps(execution_result, ensure_ascii=False, indent=2)

    return str(execution_result)
