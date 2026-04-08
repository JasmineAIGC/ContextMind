"""
PyTOD 场景 API 注册表

PyTOD 不再在算法代码内部硬编码场景 API 实现。所有场景 API 均通过外部文件传入：
  1. 生成 companion 文件：``python examples/build_schema_data.py --schema schema/xxx_schema.json``
  2. 传入追踪器：``AdkPyTODTracker.from_scenario(..., schema=svc, schema_path="schema/xxx_schema.json")``

``SCENARIO_API_REGISTRY`` 保留为空字典，``get_scenario_key`` 保留以维持接口兼容性。
如需添加自定义场景 API，可在外部代码中向 ``SCENARIO_API_REGISTRY`` 注册，
或通过 ``schema_path`` 指向预生成的 ``*_pytod_apis.py`` companion 文件。
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

from .execution_engine import ExecutionEngine


# ---------------------------------------------------------------------------
# 公共注册表（不再包含内置场景实现）
# ---------------------------------------------------------------------------

#: 场景名称 → API 注册函数映射（现为空，所有场景 API 均从外部文件加载）
SCENARIO_API_REGISTRY: Dict[str, Callable[[ExecutionEngine], None]] = {}


def get_scenario_key(scenario_name: str) -> Optional[str]:
    """从场景名称（可能含中文别名）查找注册表键，找不到时返回 None。"""
    if scenario_name in SCENARIO_API_REGISTRY:
        return scenario_name
    for key in SCENARIO_API_REGISTRY:
        if key in scenario_name or scenario_name in key:
            return key
    return None
