"""
Data models for the schema_builder package.

Defines the dataclasses used by the 5-phase PyTOD API generation pipeline
(Phase 2: test cases, Phase 4: validation results).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TestCaseItem:
    """一个意图函数的单条测试用例。

    Attributes:
        input_slots: 函数调用时传入的槽位值字典（slot_name → value）。
        expected_keys: 返回字典中必须包含的键名列表（默认包含 result_slots + "status"）。
        description: 测试场景的简短中文描述。
    """
    input_slots: Dict[str, Any]
    expected_keys: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class FuncValidation:
    """单个意图函数的测试验证结果（plan.md Phase 4）。

    Attributes:
        intent_name: 意图名称。
        total: 总测试用例数。
        passed: 通过的测试用例数。
        failures: 失败的用例详情列表（最多保留 5 条）。
        iterations: 达到当前结果共经历的修复迭代次数（0 = 首次生成即达标）。
        error: 编译/加载级别错误信息（非用例执行失败）。
    """
    intent_name: str
    total: int
    passed: int
    failures: List[Dict[str, Any]] = field(default_factory=list)
    iterations: int = 0
    error: Optional[str] = None

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total > 0 else 0.0
