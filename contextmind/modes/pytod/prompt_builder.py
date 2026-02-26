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
