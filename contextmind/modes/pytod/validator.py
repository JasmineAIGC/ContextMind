"""
PyTOD Action 合法性校验与反馈解析

对大模型生成的 PyTOD 风格 action 代码进行**纯文本级**合法性校验，
并将结构化反馈解析为可用的数据结构。

不依赖 PyTOD 官方执行器，不执行任何代码，仅做文本分析。

校验内容:
    1. JSON 格式合法性
    2. intent 字段存在且非空
    3. slots 字段存在且为字典类型
    Schema 驱动模式（提供 schema 时额外校验）:
    4. intent 值在 schema 意图列表中
    5. 枚举类型槽位的值在 possible_values 范围内
    6. 意图对应的必填槽位是否已提供（宽松校验，缺失时给出提示）
    开放域模式（schema=None）:
    4-6 均跳过，LLM 可自由命名意图和槽位
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .schema import ServiceSchema


# --------------------------------------------------------------------------- #
# 校验结果
# --------------------------------------------------------------------------- #


@dataclass
class ValidationResult:
    """
    校验结果

    属性:
        is_valid:    整体是否通过校验（无 error 级别问题）
        intent:      解析出的 intent（如解析失败则为空字符串）
        slots:       解析出的 slots 字典
        response:    解析出的自然语言回复
        errors:      错误信息列表（阻断性问题）
        warnings:    警告信息列表（非阻断性问题，如缺少可选槽位）
        raw_text:    原始 LLM 输出文本
    """

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


# --------------------------------------------------------------------------- #
# 校验器
# --------------------------------------------------------------------------- #


class ActionValidator:
    """
    PyTOD 风格 Action 校验器

    对大模型生成的 JSON action 文本进行纯文本级校验，
    无需执行任何代码。

    支持两种模式：

    **Schema 驱动模式**（传入 ``schema``）：
        在校验 JSON 结构的基础上，还会比对预定义的意图列表、
        枚举槽位可选值、必填槽位完整性。

    **开放域模式**（``schema=None``，默认）：
        仅校验 JSON 结构（intent/slots 字段存在且类型正确），
        不对意图名称或槽位内容做任何预设约束，适合 LLM 自由
        推断意图/槽位的场景。

    使用示例::

        # Schema 驱动模式
        validator = ActionValidator(schema=schema)
        result = validator.validate(llm_output)

        # 开放域模式（无预定义 schema）
        validator = ActionValidator()
        result = validator.validate(llm_output)

        if not result.is_valid:
            print(result.to_feedback_text())
        else:
            print(f"intent={result.intent}, slots={result.slots}")

    属性:
        schema:                 ServiceSchema 实例（可选，None 则为开放域模式）
        allow_unknown_intent:   是否允许不在 schema 中的 intent（schema 模式下有效）
        strict_enum:            是否严格校验枚举值（schema 模式下有效）
        require_response_field: 是否要求输出中包含 response 字段（默认 True）
    """

    # 用于从文本中提取 JSON 块的正则
    _JSON_PATTERNS: List[str] = [
        r"```json\s*([\s\S]*?)\s*```",  # ```json ... ```
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

        校验流程:
            1. 提取 JSON
            2. 校验 intent 字段
            3. 校验 slots 字段
            4. 校验枚举值
            5. 校验必填槽位（宽松，缺失为警告）

        参数:
            text: LLM 原始输出文本

        返回:
            ValidationResult 实例，包含校验结论和详细信息
        """
        result = ValidationResult(is_valid=False, raw_text=text)

        # Step 1: 提取并解析 JSON
        parsed, parse_error = self._extract_and_parse_json(text)
        if parsed is None:
            result.errors.append(f"无法解析 JSON: {parse_error}")
            return result

        # Step 2: 校验顶层结构
        self._validate_top_level(parsed, result)
        if result.errors:
            return result

        # Step 3: 填充已解析的字段
        self._populate_fields(parsed, result)

        # Step 4: 校验 intent
        self._validate_intent(result)

        # Step 5: 校验 slots
        if isinstance(result.slots, dict):
            self._validate_slots(result)
        else:
            result.errors.append(
                f"slots 字段类型错误，期望 dict，实际 {type(result.slots).__name__}"
            )

        # Step 6: 校验 response 字段（可选要求）
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
        """
        从文本中提取 JSON 并解析。

        依次尝试:
        1. 直接解析整段文本
        2. 用正则提取 JSON 块后解析

        返回:
            (parsed_dict, error_message)
        """
        if not text or not text.strip():
            return None, "输入为空"

        # 直接解析
        try:
            parsed = json.loads(text.strip())
            if isinstance(parsed, dict):
                return parsed, ""
        except json.JSONDecodeError:
            pass

        # 正则提取
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
            # 校验槽位名称是否在 schema 中定义
            if schema_slot_names and slot_name not in schema_slot_names:
                result.warnings.append(
                    f"槽位 '{slot_name}' 未在 schema 中定义，可能是模型幻觉"
                )
                continue

            # 特殊值：? 和 dontcare 总是合法的
            if slot_value in ("?", "dontcare"):
                continue

            # 枚举类型槽位校验
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

        # 检查当前 intent 的必填槽位是否已提供
        intent_def = self.schema.get_intent(result.intent)
        if intent_def:
            for required_slot in intent_def.required_slots:
                if required_slot not in result.slots:
                    result.warnings.append(
                        f"意图 '{result.intent}' 的必填槽位 '{required_slot}' 尚未提供，"
                        "请引导用户补充"
                    )
