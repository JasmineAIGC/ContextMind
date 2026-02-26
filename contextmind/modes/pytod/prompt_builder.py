"""
PyTOD Prompt 组装工具

将用户输入、对话历史、schema 与少样本示例按规则拼接，
生成适合 Qwen-3 / 其他主流 LLM 的完整 prompt。

设计原则:
- 无需依赖 PyTOD 官方执行器或解释器
- schema + prompt 驱动主流程；也支持**不预定义 schema** 的开放域模式
- 支持 zero-shot 和 few-shot 两种模式
- 输出格式为标准 messages 列表（兼容 OpenAI / Qwen API）

schema-free 开放域模式:
    当 ``schema=None`` 时，不依赖任何预定义的意图/槽位列表，
    由 LLM 根据对话上下文自由推断意图名称和需要提取的槽位，
    适合快速原型开发或意图/槽位尚未确定的早期阶段。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .schema import ServiceSchema
from .execution_engine import ExecutionResult


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #


@dataclass
class ConversationTurn:
    """
    单轮对话记录

    属性:
        role:     说话方，"user" 或 "assistant"
        content:  该轮的话语内容
        action:   助手推荐的 action（仅 assistant 轮有效，可为 None）
    """

    role: str  # "user" | "assistant"
    content: str
    action: Optional[Dict[str, Any]] = None

    def to_history_text(self) -> str:
        """
        将本轮对话转换为历史上下文文本片段。

        返回:
            格式化后的对话行，例如：
            "用户: 我想预约明天晚上的餐厅"
            "助手: [action=Reserve] 好的，请问您需要几位就餐？"
        """
        speaker = "用户" if self.role == "user" else "助手"
        action_prefix = ""
        if self.role == "assistant" and self.action:
            intent = self.action.get("intent", "")
            if intent:
                action_prefix = f"[action={intent}] "
        return f"{speaker}: {action_prefix}{self.content}"


@dataclass
class FewShotExample:
    """
    Few-shot 示例

    属性:
        user_input:  用户话语
        action:      期望的 action 字典（intent + slots）
        response:    自然语言回复
        description: 示例说明（可选，用于注释）
    """

    user_input: str
    action: Dict[str, Any]
    response: str
    description: str = ""


# --------------------------------------------------------------------------- #
# Prompt 组装器
# --------------------------------------------------------------------------- #


class PyTODPromptBuilder:
    """
    PyTOD 风格 Prompt 组装器

    根据 ServiceSchema（可选）、对话历史和用户输入，组装适合大模型
    （如 Qwen-3）进行 zero/few-shot 推理的完整 prompt。

    支持两种运行模式：

    **Schema 驱动模式**（传入 ``schema``）：
        LLM 被约束在预定义的意图列表和槽位范围内进行推理，
        适合有明确业务场景（如餐厅预约、保险咨询）的生产环境。

    **开放域模式**（``schema=None``，默认）：
        不依赖任何预定义意图或槽位，LLM 根据对话上下文自由命名
        意图并提取任意信息槽位，适合快速原型开发或意图/槽位
        尚未确定的早期阶段。

    模型输出格式（JSON）::

        {
            "intent": "意图名称",
            "slots": {
                "slot_name": "slot_value",
                ...
            },
            "response": "自然语言回复"
        }

    使用示例::

        # Schema 驱动模式
        builder = PyTODPromptBuilder(schema=schema)
        messages = builder.build_messages(user_input="我想预约明天的餐厅")

        # 开放域模式（无需预定义 schema）
        builder = PyTODPromptBuilder()
        messages = builder.build_messages(user_input="我想预约明天的餐厅")

    属性:
        schema:            ServiceSchema 实例（可选，为 None 则启用开放域模式）
        few_shot_examples: few-shot 示例列表（可选）
        max_history_turns: 保留的最大历史轮次数（默认 10）
        response_language: 期望回复语言的提示文字（默认"中文"）
    """

    # ---------------------------------------------------------------------- #
    # Schema 驱动模式：系统提示模板
    # ---------------------------------------------------------------------- #
    _SYSTEM_TEMPLATE = """\
你是一个任务型对话系统的核心模块，负责理解用户意图并推荐合适的 action。

## 服务 Schema

{schema_text}

## 输出格式

你必须严格按照以下 JSON 格式输出，不要添加任何额外文字或 Markdown 标记：

```json
{{
    "intent": "意图名称（从 Schema 意图列表中选择）",
    "slots": {{
        "槽位名": "槽位值"
    }},
    "response": "面向用户的自然语言回复（{response_language}）"
}}
```

## 规则

1. intent 必须是 Schema 中定义的意图之一；若无法判断，填 "UNKNOWN"。
2. slots 只填写用户**明确提供**的信息；未提供的槽位不要猜测。
3. 若用户询问某个槽位，对应值填 "?"；若用户表示不在乎，填 "dontcare"。
4. response 应简洁、礼貌，引导用户继续填写缺失的必填槽位。
5. 只输出合法 JSON，不要输出其他任何内容。
"""

    # ---------------------------------------------------------------------- #
    # 开放域模式：无需预定义 schema 的系统提示模板
    # ---------------------------------------------------------------------- #
    _SYSTEM_TEMPLATE_OPEN = """\
你是一个任务型对话系统的核心模块，负责理解用户意图并推荐合适的 action。

## 模式

开放域模式：无预定义 Schema。请根据对话上下文自由判断意图，
并提取用户明确提供的任意信息作为槽位，无需受限于固定意图列表或槽位名称。

## 输出格式

你必须严格按照以下 JSON 格式输出，不要添加任何额外文字或 Markdown 标记：

```json
{{
    "intent": "根据上下文自由命名的意图（英文或中文，简洁清晰）",
    "slots": {{
        "槽位名": "槽位值"
    }},
    "response": "面向用户的自然语言回复（{response_language}）"
}}
```

## 规则

1. intent 根据用户话语自由命名，语义清晰即可；若无法判断，填 "UNKNOWN"。
2. slots 只填写用户**明确提供**的信息；槽位名称可自行定义，无需预设。
3. 若用户询问某个槽位，对应值填 "?"；若用户表示不在乎，填 "dontcare"。
4. response 应简洁、礼貌，引导用户继续提供所需信息。
5. 只输出合法 JSON，不要输出其他任何内容。
"""

    _FEW_SHOT_HEADER = "\n## Few-shot 示例\n"

    _HISTORY_HEADER = "\n## 历史对话\n"

    _USER_TURN_TEMPLATE = "用户: {content}"

    # ---------------------------------------------------------------------- #
    # 步骤一：动作解析器（Action Parser）系统提示模板
    # 与 PyTOD 官方算法一致：多行程序、[HISTORY]/[CURRENT] 格式
    # ---------------------------------------------------------------------- #
    _ACTION_PARSER_TEMPLATE = """\
你是任务型对话系统的**动作解析器（Action Parser）**。

根据对话历史和当前用户输入，生成对应的 PyTOD 程序，供执行引擎执行。

{api_functions_text}

## 程序格式

每条语句占一行，支持以下四种格式：

1. API 函数调用（带变量绑定）：
   x1 service_1_api_name(param1='value1', param2='value2')

2. 槽位赋值（补充或更新已声明的 API 调用参数）：
   x1.slot_name = 'value'

3. Hint 语句（请求用户提供缺失信息）：
   x2 Hint('request value: slot_name')

4. say 语句（组合 Hint 输出给用户）：
   x3 say(x2)

## 示例

用户: I want to book a hotel in San Jose for 2 nights.
程序：
x1 hotels_1_search_hotel(city='San Jose', number_of_nights=2)
x2 Hint('request value: check_in_date')
x3 say(x2)

## 规则

1. 只能调用上方列出的 API 函数，不能创造新函数。
2. 只传入用户**明确提供**的参数；未提供的参数用 Hint 语句引导用户补充。
3. 若无法判断应调用哪个函数，输出：NONE()
4. 只输出程序语句，不要添加任何解释或额外文字。
"""

    # ---------------------------------------------------------------------- #
    # 步骤三：对话管理器（Dialogue Manager）系统提示模板
    # 根据执行结果生成自然语言回复
    # ---------------------------------------------------------------------- #
    _DIALOGUE_MANAGER_TEMPLATE = """\
你是任务型对话系统的**对话管理器（Dialogue Manager）**。

根据以下信息生成面向用户的自然语言回复：
1. 用户的输入
2. 系统执行的 API 调用及其返回结果

## 执行结果

{execution_result_text}

## 规则

1. 回复语言：{response_language}。
2. 回复应简洁、礼貌、有帮助，直接使用执行结果中的数据回答用户。
3. 如果执行失败，礼貌告知用户并引导重试。
4. 只输出面向用户的自然语言回复，不要输出 JSON 或技术细节。
"""

    def __init__(
        self,
        schema: Optional[ServiceSchema] = None,
        few_shot_examples: Optional[List[FewShotExample]] = None,
        max_history_turns: int = 10,
        response_language: str = "中文",
    ) -> None:
        """
        初始化 Prompt 组装器。

        参数:
            schema:              服务 schema 定义（可选）。
                                 传入 ServiceSchema 则启用 schema 驱动模式；
                                 传入 None（默认）则启用开放域模式，LLM 自由
                                 决定意图名称和槽位，无需预定义。
            few_shot_examples:   few-shot 示例列表（为 None 或空列表则为 zero-shot）
            max_history_turns:   保留的历史轮次上限（防止 context 过长）
            response_language:   期望回复语言（嵌入系统提示中）
        """
        self.schema = schema
        self.few_shot_examples: List[FewShotExample] = few_shot_examples or []
        self.max_history_turns = max_history_turns
        self.response_language = response_language

    @property
    def is_open_domain(self) -> bool:
        """当前是否为开放域模式（无预定义 schema）。"""
        return self.schema is None

    # ------------------------------------------------------------------ #
    # 公开接口
    # ------------------------------------------------------------------ #

    def build_messages(
        self,
        user_input: str,
        history: Optional[List[ConversationTurn]] = None,
    ) -> List[Dict[str, str]]:
        """
        组装完整的 messages 列表，可直接传入 LLM API。

        参数:
            user_input: 当前轮用户输入
            history:    历史对话轮次列表（按时间顺序）

        返回:
            OpenAI / Qwen 兼容的 messages 列表::

                [
                    {"role": "system", "content": "..."},
                    {"role": "user",   "content": "..."},  # 可选，few-shot
                    {"role": "assistant", "content": "..."},  # 可选，few-shot
                    ...
                    {"role": "user",   "content": "当前用户输入"},
                ]
        """
        messages: List[Dict[str, str]] = []

        # 1. 系统提示（包含 schema）
        messages.append({"role": "system", "content": self._build_system_prompt()})

        # 2. Few-shot 示例（可选）
        if self.few_shot_examples:
            messages.extend(self._build_few_shot_messages())

        # 3. 历史对话（可选）
        if history:
            trimmed = history[-self.max_history_turns :]
            for turn in trimmed:
                role = turn.role  # "user" | "assistant"
                messages.append({"role": role, "content": turn.content})

        # 4. 当前用户输入
        messages.append({"role": "user", "content": user_input})

        return messages

    def build_single_prompt(
        self,
        user_input: str,
        history: Optional[List[ConversationTurn]] = None,
    ) -> str:
        """
        组装为单个纯文本 prompt（适合不支持 messages 格式的模型）。

        参数:
            user_input: 当前轮用户输入
            history:    历史对话轮次列表

        返回:
            完整的单段 prompt 字符串
        """
        parts: List[str] = []

        # 系统说明
        parts.append(self._build_system_prompt())

        # Few-shot 示例
        if self.few_shot_examples:
            parts.append(self._build_few_shot_text())

        # 历史对话
        if history:
            trimmed = history[-self.max_history_turns :]
            history_lines = [t.to_history_text() for t in trimmed]
            parts.append(self._HISTORY_HEADER + "\n".join(history_lines))

        # 当前用户输入
        parts.append(f"\n{self._USER_TURN_TEMPLATE.format(content=user_input)}")
        parts.append("助手:")

        return "\n".join(parts)

    # ------------------------------------------------------------------ #
    # PyTOD 标准流程接口：步骤一 — 动作解析器（Action Parser）
    # ------------------------------------------------------------------ #

    def build_action_parser_messages(
        self,
        user_input: str,
        execution_engine: Any,
        history: Optional[List[ConversationTurn]] = None,
    ) -> List[Dict[str, str]]:
        """
        组装动作解析器（Action Parser）的 messages 列表。

        **PyTOD 算法流程第一步**：告知 LLM 当前可用的 API 函数列表，
        让其根据对话历史和当前用户输入生成 PyTOD 多行程序，供执行引擎执行。

        输入格式与 PyTOD 官方算法一致，使用 ``[HISTORY]``/``[CURRENT]`` 标签::

            [HISTORY] user: I want to book a hotel...
            [HISTORY] system: Sure, where would you like to stay?
            [CURRENT] user: In San Jose, please.

        LLM 应输出多行 PyTOD 程序，例如::

            x1 hotels_1_search_hotel(city='San Jose')
            x2 Hint('request value: check_in_date')
            x3 say(x2)

        与 ``build_messages()`` 的区别：
        - 使用 ``[HISTORY]``/``[CURRENT]`` 标签格式，符合 PyTOD 文本-文本范式
        - 期望输出为多行程序而非 JSON
        - 执行结果由执行引擎处理，回复由对话管理器生成

        参数:
            user_input:       当前轮用户输入
            execution_engine: ``ExecutionEngine`` 实例（用于获取已注册函数列表）
            history:          历史对话轮次列表（可选）

        返回:
            OpenAI / Qwen 兼容的 messages 列表
        """
        system_content = self._ACTION_PARSER_TEMPLATE.format(
            api_functions_text=execution_engine.to_prompt_text(),
        )
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_content},
        ]

        # 组装 [HISTORY]/[CURRENT] 格式的对话上下文（PyTOD 文本-文本范式）
        context_lines: List[str] = []
        if history:
            trimmed = history[-self.max_history_turns:]
            for turn in trimmed:
                speaker = "user" if turn.role == "user" else "system"
                context_lines.append(f"[HISTORY] {speaker}: {turn.content}")
        context_lines.append(f"[CURRENT] user: {user_input}")

        messages.append({"role": "user", "content": "\n".join(context_lines)})
        return messages

    # ------------------------------------------------------------------ #
    # PyTOD 标准流程接口：步骤三 — 对话管理器（Dialogue Manager）
    # ------------------------------------------------------------------ #

    def build_dialogue_manager_messages(
        self,
        user_input: str,
        execution_result: Any,
        history: Optional[List[ConversationTurn]] = None,
    ) -> List[Dict[str, str]]:
        """
        组装对话管理器（Dialogue Manager）的 messages 列表。

        **PyTOD 算法流程第三步**：将执行引擎的执行结果注入 prompt，
        让 LLM 生成面向用户的自然语言回复。

        接受两种执行结果类型：
        - ``ExecutionResult``：单语句执行结果（``ExecutionEngine.execute()``）
        - ``ProgramExecutionResult``：多语句程序执行结果（``ExecutionEngine.execute_program()``）
          两者均实现 ``to_context_text()``，可互换传入。

        参数:
            user_input:        当前轮用户输入
            execution_result:  执行引擎返回的执行结果（实现 to_context_text() 即可）
            history:           历史对话轮次列表（可选）

        返回:
            OpenAI / Qwen 兼容的 messages 列表
        """
        system_content = self._DIALOGUE_MANAGER_TEMPLATE.format(
            execution_result_text=execution_result.to_context_text(),
            response_language=self.response_language,
        )
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_content},
        ]

        # 历史对话
        if history:
            trimmed = history[-self.max_history_turns :]
            for turn in trimmed:
                messages.append({"role": turn.role, "content": turn.content})

        # 当前用户输入（对话管理器需要用户原始话语作为回复依据）
        messages.append({"role": "user", "content": user_input})
        return messages

    # ------------------------------------------------------------------ #
    # 内部构建方法
    # ------------------------------------------------------------------ #

    def _build_system_prompt(self) -> str:
        """构建系统提示。根据是否提供 schema 自动切换 schema 驱动 / 开放域模板。"""
        if self.schema is None:
            return self._SYSTEM_TEMPLATE_OPEN.format(
                response_language=self.response_language,
            )
        return self._SYSTEM_TEMPLATE.format(
            schema_text=self.schema.to_prompt_text(),
            response_language=self.response_language,
        )

    def _build_few_shot_messages(self) -> List[Dict[str, str]]:
        """将 few-shot 示例转换为 messages 格式。"""
        import json

        messages: List[Dict[str, str]] = []
        for ex in self.few_shot_examples:
            # 用户侧
            messages.append({"role": "user", "content": ex.user_input})
            # 助手侧：JSON action + response
            assistant_content = json.dumps(
                {
                    "intent": ex.action.get("intent", ""),
                    "slots": ex.action.get("slots", {}),
                    "response": ex.response,
                },
                ensure_ascii=False,
                indent=2,
            )
            messages.append({"role": "assistant", "content": assistant_content})
        return messages

    def _build_few_shot_text(self) -> str:
        """将 few-shot 示例转换为纯文本格式。"""
        import json

        lines = [self._FEW_SHOT_HEADER]
        for idx, ex in enumerate(self.few_shot_examples, 1):
            action_json = json.dumps(
                {
                    "intent": ex.action.get("intent", ""),
                    "slots": ex.action.get("slots", {}),
                    "response": ex.response,
                },
                ensure_ascii=False,
                indent=2,
            )
            desc = f"（{ex.description}）" if ex.description else ""
            lines.append(f"### 示例 {idx} {desc}")
            lines.append(f"用户: {ex.user_input}")
            lines.append(f"助手:\n{action_json}")
            lines.append("")
        return "\n".join(lines)
