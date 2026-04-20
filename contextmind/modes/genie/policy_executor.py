"""
PolicyExecutor — Genie Worksheets 确定性状态机执行器

仅用纯 Python 逻辑实现 Worksheet 字段填写状态机，**不调用任何 LLM**。
负责：
  - 追踪每个 Worksheet 字段的填写状态（已填 / 未填 / 待确认）
  - 确定下一个需要系统询问的字段
  - 校验字段值（类型校验 + 枚举合法值检查）
  - 判断 Worksheet 是否已全部完成

与 Genie 论文对应关系
----------------------
  PolicyExecutor ≈ Genie "Policy Executor"（无 LLM 运行时）
  WorksheetState  ≈ Genie "Worksheet 当前实例化状态"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from contextmind.schema_builder.genie_worksheets.schema_types import GenieIntent, GenieSchema
from contextmind.schema_builder.genie_worksheets.models import PolicyField

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 字段状态枚举
# ---------------------------------------------------------------------------

class FieldStatus:
    """字段填写状态常量。"""
    EMPTY = "empty"           # 尚未填写
    FILLED = "filled"         # 已填写
    PENDING_CONFIRM = "pending_confirm"  # 已填，等待用户确认
    CONFIRMED = "confirmed"   # 已确认


# ---------------------------------------------------------------------------
# WorksheetState — 单次对话的 Worksheet 实例化状态
# ---------------------------------------------------------------------------

@dataclass
class WorksheetState:
    """Worksheet 当前实例化状态（单次对话会话）。

    每次调用 ``PolicyExecutor.fill_field`` 时更新。

    Attributes:
        field_values:  已填写的字段值字典（field_name → value）。
        field_statuses: 每个字段的状态（FieldStatus 常量之一）。
        errors:        本次操作的校验错误列表。
        confirmed_fields: 已经过用户确认的字段集合。
    """

    field_values: Dict[str, Any] = field(default_factory=dict)
    field_statuses: Dict[str, str] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    confirmed_fields: set = field(default_factory=set)

    def get_value(self, name: str) -> Optional[Any]:
        """获取字段当前值；未填时返回 None。"""
        return self.field_values.get(name)

    def is_filled(self, name: str) -> bool:
        """字段是否已有值（无论是否已确认）。"""
        return name in self.field_values and self.field_values[name] is not None

    def to_dict(self) -> Dict[str, Any]:
        """导出为可序列化字典（供 API 返回值使用）。"""
        return {
            "field_values": dict(self.field_values),
            "field_statuses": dict(self.field_statuses),
            "errors": list(self.errors),
        }


# ---------------------------------------------------------------------------
# PolicyExecutor — Worksheet 策略执行器
# ---------------------------------------------------------------------------

class PolicyExecutor:
    """Genie Worksheets 策略执行器（无 LLM）。

    从 ``ServiceSchema`` 中读取 ``policy_fields`` 策略注解，驱动字段收集流程。

    参数
    ----
    schema :
        含 ``policy_fields`` 的 ``ServiceSchema``（由 ``WorksheetLoader`` 加载）。
    intent_name :
        要执行的意图名称；为 None 时使用第一个含 policy_fields 的意图。
    """

    def __init__(
        self,
        schema: GenieSchema,
        intent_name: Optional[str] = None,
    ) -> None:
        self._schema = schema
        self._intent: Optional[GenieIntent] = self._resolve_intent(intent_name)
        self._policy_fields: List[PolicyField] = (
            self._intent.policy_fields if self._intent else []
        )
        # 将 policy_fields 列表转为 {name: PolicyField} 字典，方便快速查找
        self._field_map: Dict[str, PolicyField] = {
            pf.name: pf for pf in self._policy_fields
        }
        self._state = WorksheetState()

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    @property
    def state(self) -> WorksheetState:
        """当前 Worksheet 状态（只读访问）。"""
        return self._state

    @property
    def intent(self) -> Optional[GenieIntent]:
        """当前执行的意图定义。"""
        return self._intent

    def next_required_field(self) -> Optional[PolicyField]:
        """返回下一个需要系统主动询问的字段。

        遵循以下优先级：
        1. required=True 且尚未填写 的字段（按 policy_fields 定义顺序）
        2. 依赖字段已满足的条件字段
        3. 若 required 字段都已填完，返回第一个 optional ask_by_system 字段

        Returns:
            下一个待填 ``PolicyField``，或 ``None``（全部完成）。
        """
        for pf in self._policy_fields:
            if not pf.ask_by_system:
                continue
            if self._state.is_filled(pf.name):
                continue
            # 检查条件依赖
            if pf.depends_on and not self._state.is_filled(pf.depends_on):
                continue
            return pf
        return None

    def fill_field(
        self,
        name: str,
        value: Any,
    ) -> Tuple[bool, str]:
        """填写指定字段。

        执行类型和枚举合法值校验；通过则更新状态，否则返回错误原因。

        Args:
            name:  字段名称（必须在 policy_fields 中定义）。
            value: 字段值（来自语义解析器的提取结果）。

        Returns:
            (success: bool, error_message: str) 元组。
            成功时 error_message 为空字符串。
        """
        pf = self._field_map.get(name)
        if pf is None:
            # 未在 policy_fields 中定义的字段：接受但不记录策略状态
            self._state.field_values[name] = value
            logger.debug(f"[PolicyExecutor] 填写未定义字段 {name!r}={value!r}（跳过校验）")
            return True, ""

        # 类型校验与转换
        converted, err = self._coerce_value(value, pf)
        if err:
            self._state.errors.append(err)
            return False, err

        self._state.field_values[name] = converted
        if pf.confirm:
            self._state.field_statuses[name] = FieldStatus.PENDING_CONFIRM
        else:
            self._state.field_statuses[name] = FieldStatus.FILLED
        logger.debug(f"[PolicyExecutor] 字段 {name!r} = {converted!r}")
        return True, ""

    def confirm_field(self, name: str) -> bool:
        """确认字段（由用户确认后调用）。

        Returns:
            True（字段存在且状态已更新），False（字段未填或不存在）。
        """
        if not self._state.is_filled(name):
            return False
        self._state.field_statuses[name] = FieldStatus.CONFIRMED
        self._state.confirmed_fields.add(name)
        return True

    def fill_batch(self, assignments: Dict[str, Any]) -> List[str]:
        """批量填写字段。

        Args:
            assignments: {field_name: value} 字典。

        Returns:
            填写失败的错误信息列表（成功时为空列表）。
        """
        errors: List[str] = []
        for name, value in assignments.items():
            ok, err = self.fill_field(name, value)
            if not ok:
                errors.append(err)
        return errors

    def is_complete(self) -> bool:
        """检查所有 required 字段是否已填写（或已确认）。"""
        for pf in self._policy_fields:
            if not pf.required:
                continue
            # 检查依赖条件：依赖字段未填时，本字段不参与完成判断
            if pf.depends_on and not self._state.is_filled(pf.depends_on):
                continue
            if not self._state.is_filled(pf.name):
                return False
        return True

    def get_missing_required(self) -> List[PolicyField]:
        """返回所有尚未填写的必填字段列表。"""
        return [
            pf for pf in self._policy_fields
            if pf.required
            and not self._state.is_filled(pf.name)
            and not (pf.depends_on and not self._state.is_filled(pf.depends_on))
        ]

    def reset(self) -> None:
        """清空状态，开始新会话。"""
        self._state = WorksheetState()

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _resolve_intent(self, intent_name: Optional[str]) -> Optional[GenieIntent]:
        """解析目标意图：按名称查找，或取第一个含 policy_fields 的意图。"""
        if intent_name:
            return self._schema.get_intent(intent_name)
        for intent in self._schema.intents:
            if intent.policy_fields:
                return intent
        # 退化：返回第一个意图（无 policy_fields 也可运行，只是没有约束）
        return self._schema.intents[0] if self._schema.intents else None

    def _coerce_value(self, value: Any, pf: PolicyField) -> Tuple[Any, str]:
        """将字符串值强制转换为 PolicyField 要求的类型，并校验枚举合法性。

        Returns:
            (converted_value, error_message) — 成功时 error_message 为 ""。
        """
        str_val = str(value).strip() if value is not None else ""

        if pf.field_type == "int":
            try:
                return int(str_val), ""
            except (ValueError, TypeError):
                return None, f"字段 '{pf.name}' 需要整数值，收到: {str_val!r}"

        if pf.field_type == "float":
            try:
                return float(str_val), ""
            except (ValueError, TypeError):
                return None, f"字段 '{pf.name}' 需要数值，收到: {str_val!r}"

        if pf.field_type == "bool":
            if str_val.lower() in ("true", "yes", "是", "1"):
                return True, ""
            if str_val.lower() in ("false", "no", "否", "0"):
                return False, ""
            return None, f"字段 '{pf.name}' 需要布尔值（是/否），收到: {str_val!r}"

        if pf.field_type == "enum" and pf.possible_values:
            # 宽松匹配：忽略大小写和空格
            norm_input = str_val.lower().strip()
            for pv in pf.possible_values:
                if pv.lower().strip() == norm_input:
                    return pv, ""
            # 模糊匹配：允许部分匹配
            for pv in pf.possible_values:
                if norm_input in pv.lower() or pv.lower() in norm_input:
                    logger.debug(
                        f"[PolicyExecutor] 枚举字段 {pf.name!r} 模糊匹配: "
                        f"{str_val!r} → {pv!r}"
                    )
                    return pv, ""
            valid_str = ", ".join(pf.possible_values)
            return None, (
                f"字段 '{pf.name}' 值 {str_val!r} 不在合法枚举 [{valid_str}] 中"
            )

        # str 类型或未知类型：原样返回字符串
        return str_val, ""
