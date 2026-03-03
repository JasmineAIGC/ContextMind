"""
PyTOD Action 合法性校验与反馈解析

对大模型生成的 PyTOD 风格 action 进行纯文本级合法性校验。
Schema 驱动模式（传入 schema）校验意图列表、枚举值、必填槽位；
开放域模式（schema=None）仅校验 JSON 结构。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .schema import ServiceSchema


@dataclass
class ValidationResult:
    """校验结果，包含 intent/slots/response 解析值及错误/警告列表。"""

    is_valid: bool
    intent: str = ""
    slots: Dict[str, Any] = field(default_factory=dict)
    response: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    raw_text: str = ""

    def to_feedback_text(self) -> str:
        """
        将校验结果格式化为可回传给 LLM 的反馈文本。

        当校验失败时，可以将此文本追加到对话历史，
        让 LLM 修正输出。

        返回:
            格式化的反馈说明，例如：

            [校验结果: 失败]
            错误:
              - intent "Book" 不在 schema 定义的意图列表中
            建议:
              - 请从以下意图中选择: Reserve, Cancel, Query
        """
        status = "通过" if self.is_valid else "失败"
        lines = [f"[校验结果: {status}]"]

        if self.errors:
            lines.append("错误:")
            for err in self.errors:
                lines.append(f"  - {err}")

        if self.warnings:
            lines.append("警告 (不阻断流程):")
            for warn in self.warnings:
                lines.append(f"  - {warn}")

        if self.is_valid and not self.warnings:
            lines.append("action 格式正确，可继续处理。")

        return "\n".join(lines)

    def summary(self) -> str:
        """返回简短的单行摘要。"""
        if self.is_valid:
            warn_part = f"，{len(self.warnings)} 个警告" if self.warnings else ""
            return f"✓ 校验通过（intent={self.intent}）{warn_part}"
        return f"✗ 校验失败（{len(self.errors)} 个错误）: {'; '.join(self.errors[:2])}"


class ActionValidator:
    """
    PyTOD 风格 Action 校验器

    对大模型生成的 JSON action 文本进行纯文本级校验，无需执行任何代码。
    传入 ``schema`` 启用 schema 驱动模式；``schema=None``（默认）启用开放域模式。
    """

    # 按顺序尝试各种模式：围栏代码块最明确（优先），最后尝试裸 JSON 对象。
    # 围栏代码块因有明确分隔符而更可靠；裸对象匹配为最终后备方案。
    _JSON_PATTERNS: List[str] = [
        r"```json\s*([\s\S]*?)\s*```",  # ```json ... ``` 格式
        r"```\s*([\s\S]*?)\s*```",       # ``` ... ```
        r"\{[\s\S]*\}",                  # 裸 JSON 对象
    ]

    def __init__(
        self,
        schema: Optional[ServiceSchema] = None,
        allow_unknown_intent: bool = False,
        strict_enum: bool = True,
        require_response_field: bool = True,
    ) -> None:
        """
        初始化校验器。

        参数:
            schema:                 服务 schema 定义（可选）。
                                    传入 ServiceSchema 则启用 schema 驱动模式；
                                    传入 None（默认）则启用开放域模式，跳过
                                    意图列表、枚举值、必填槽位等 schema 相关校验。
            allow_unknown_intent:   schema 模式下是否允许不在 schema 中的 intent
            strict_enum:            schema 模式下枚举槽位是否严格匹配（否则仅警告）
            require_response_field: 是否要求 response 字段存在
        """
        self.schema = schema
        self.allow_unknown_intent = allow_unknown_intent
        self.strict_enum = strict_enum
        self.require_response_field = require_response_field

    @property
    def is_open_domain(self) -> bool:
        """当前是否为开放域模式（无预定义 schema）。"""
        return self.schema is None

    # ------------------------------------------------------------------ #
    # 公开接口
    # ------------------------------------------------------------------ #

    def validate(self, text: str) -> ValidationResult:
        """
        校验 LLM 生成的 action 文本。

        Args:
            text: LLM 原始输出文本

        Returns:
            ValidationResult 实例，包含校验结论和详细信息
        """
        result = ValidationResult(is_valid=False, raw_text=text)

        parsed, parse_error = self._extract_and_parse_json(text)
        if parsed is None:
            result.errors.append(f"无法解析 JSON: {parse_error}")
            return result

        self._validate_top_level(parsed, result)
        if result.errors:
            return result

        self._populate_fields(parsed, result)
        self._validate_intent(result)

        if isinstance(result.slots, dict):
            self._validate_slots(result)
        else:
            result.errors.append(
                f"slots 字段类型错误，期望 dict，实际 {type(result.slots).__name__}"
            )

        if self.require_response_field and not result.response.strip():
            result.warnings.append("response 字段为空，建议提供面向用户的自然语言回复")

        result.is_valid = len(result.errors) == 0
        return result

    def parse_feedback(self, text: str) -> Tuple[bool, Dict[str, Any]]:
        """
        快速解析反馈（轻量版，不做 schema 校验）。

        适用于只需提取 intent + slots 而不关心校验细节的场景。

        参数:
            text: LLM 输出文本

        返回:
            (success, action_dict) 元组:
            - success: 是否成功解析
            - action_dict: 解析出的 action 字典（失败时为空 dict）
        """
        parsed, _ = self._extract_and_parse_json(text)
        if parsed is None or not isinstance(parsed, dict):
            return False, {}
        result = ValidationResult(is_valid=True)
        self._populate_fields(parsed, result)
        return True, {
            "intent": result.intent,
            "slots": result.slots,
            "response": result.response,
        }

    # ------------------------------------------------------------------ #
    # 内部校验方法
    # ------------------------------------------------------------------ #

    def _populate_fields(
        self, parsed: Dict[str, Any], result: ValidationResult
    ) -> None:
        """从解析后的字典填充 ValidationResult 的字段。"""
        raw_intent = parsed.get("intent")
        result.intent = str(raw_intent) if raw_intent is not None else ""
        result.slots = parsed.get("slots", {}) or {}
        raw_response = parsed.get("response")
        result.response = str(raw_response) if raw_response is not None else ""

    def _extract_and_parse_json(
        self, text: str
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """从文本中提取 JSON 并解析，依次尝试直接解析和正则提取。"""
        if not text or not text.strip():
            return None, "输入为空"

        try:
            parsed = json.loads(text.strip())
            if isinstance(parsed, dict):
                return parsed, ""
        except json.JSONDecodeError:
            pass

        for pattern in self._JSON_PATTERNS:
            for match in re.finditer(pattern, text, re.DOTALL):
                candidate = match.group(1) if match.lastindex else match.group(0)
                try:
                    parsed = json.loads(candidate.strip())
                    if isinstance(parsed, dict):
                        return parsed, ""
                except json.JSONDecodeError:
                    continue

        return None, "未找到合法的 JSON 结构"

    def _validate_top_level(
        self, parsed: Dict[str, Any], result: ValidationResult
    ) -> None:
        """校验顶层必要字段（intent、slots）。"""
        if "intent" not in parsed:
            result.errors.append("缺少必要字段 'intent'")
        if "slots" not in parsed:
            result.errors.append("缺少必要字段 'slots'")

    def _validate_intent(self, result: ValidationResult) -> None:
        """校验 intent 值是否合法。"""
        intent = result.intent
        if not intent:
            result.errors.append("intent 字段为空")
            return

        if intent == "UNKNOWN":
            # UNKNOWN 是保留哨兵值，表示模型无法确定意图；
            # 这不是错误，而是给对话管理器的信号，提示其向用户寻求澄清。
            result.warnings.append(
                "intent 为 UNKNOWN，表示模型未能识别用户意图，"
                "建议追问用户或提供更多上下文"
            )
            return

        # 开放域模式：无预定义 schema，任意非空 intent 均合法
        if self.schema is None:
            return

        valid_intents = self.schema.get_intent_names()
        if intent not in valid_intents:
            msg = (
                f"intent \"{intent}\" 不在 schema 定义的意图列表中。"
                f"有效意图: {', '.join(valid_intents) if valid_intents else '(空)'}"
            )
            if self.allow_unknown_intent:
                result.warnings.append(msg)
            else:
                result.errors.append(msg)

    def _validate_slots(self, result: ValidationResult) -> None:
        """校验 slots 中各槽位的合法性。"""
        # 开放域模式：无预定义 schema，槽位名称和值均不受限制，跳过所有 schema 校验
        if self.schema is None:
            return

        schema_slot_names = set(self.schema.get_slot_names())

        for slot_name, slot_value in result.slots.items():
            if schema_slot_names and slot_name not in schema_slot_names:
                result.warnings.append(
                    f"槽位 '{slot_name}' 未在 schema 中定义，可能是模型幻觉"
                )
                continue

            # "?" 和 "dontcare" 是 DST 惯例的哨兵值，可绕过枚举验证——
            # 无论 possible_values 为何值，它们始终合法。
            if slot_value in ("?", "dontcare"):
                continue

            slot_def = self.schema.get_slot(slot_name)
            if slot_def and slot_def.is_categorical and slot_def.possible_values:
                value_str = str(slot_value)
                if value_str not in slot_def.possible_values:
                    msg = (
                        f"槽位 '{slot_name}' 的值 \"{value_str}\" 不在可选值列表中。"
                        f"可选值: {', '.join(slot_def.possible_values)}"
                    )
                    if self.strict_enum:
                        result.errors.append(msg)
                    else:
                        result.warnings.append(msg)

        intent_def = self.schema.get_intent(result.intent)
        if intent_def:
            for required_slot in intent_def.required_slots:
                if required_slot not in result.slots:
                    # 警告而非报错：槽位填充是跨轮次递增进行的，
                    # 单轮缺失槽位属于正常情况。
                    result.warnings.append(
                        f"意图 '{result.intent}' 的必填槽位 '{required_slot}' 尚未提供，"
                        "请引导用户补充"
                    )
