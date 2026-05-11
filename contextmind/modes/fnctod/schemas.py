"""
FnCTOD Schema 加载工具

提供从外部文件加载 DomainSpec 的工具函数。
FnCTOD 不再在算法代码内部硬编码场景 Schema 数据，所有 Schema 均通过外部文件传入。

推荐使用方式：
    1. 生成 companion 文件：``python examples/step2b_build_schema_data.py --schema schema/xxx_schema.json``
    2. 加载：``domain_spec = load_domain_spec_from_file("schema/xxx_fnctod_domain.json")``
    3. 传入追踪器：``FnCTODTracker.from_scenario(..., domain_spec=domain_spec)``
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from .function_manager import DomainSpec, FunctionParameter, ParameterType


def load_domain_spec_from_file(path: Union[str, Path]) -> DomainSpec:
    """从外部 JSON 文件加载 DomainSpec。

    支持两种格式：

    1. **FnCTOD companion 格式**（由 ``build_schema_data.py`` 生成）::

           {"name": "...", "description": "...",
            "parameters": {"type": "object", "properties": {...}, "required": [...]}}

    2. **SGD 格式**（由知识库构建器生成）::

           [{"service_name": "...", "description": "...",
             "slots": [...], "intents": [...]}]

    Args:
        path: JSON 文件路径。

    Returns:
        DomainSpec，可直接传给 FunctionManager.add_domain() 或 from_scenario(domain_spec=)。
    """
    path = Path(path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    entry = data[0] if isinstance(data, list) else data

    # FnCTOD companion 格式：parameters 是带 properties 的 OpenAI JSON Schema
    params_raw = entry.get("parameters", {})
    if isinstance(params_raw, dict) and "properties" in params_raw:
        spec = DomainSpec(
            name=entry.get("name", entry.get("service_name", path.stem)),
            description=entry.get("description", ""),
        )
        required_set = set(params_raw.get("required", []))
        for slot_name, prop in params_raw.get("properties", {}).items():
            spec.add_parameter(FunctionParameter(
                name=slot_name,
                description=prop.get("description", ""),
                param_type=ParameterType.STRING,
                required=slot_name in required_set,
                enum_values=prop.get("enum") or None,
            ))
        return spec

    # FnCTOD 旧格式：parameters 是参数定义列表
    if isinstance(params_raw, list) and params_raw and isinstance(params_raw[0], dict) and "name" in params_raw[0]:
        spec = DomainSpec(
            name=entry.get("name", entry.get("service_name", path.stem)),
            description=entry.get("description", ""),
        )
        for p in params_raw:
            spec.add_parameter(FunctionParameter(
                name=p["name"],
                description=p.get("description", ""),
                param_type=ParameterType.STRING,
                required=p.get("required", False),
                enum_values=p.get("enum") or p.get("enum_values") or None,
            ))
        return spec

    # SGD / ServiceSchema 格式
    from contextmind.modes.pytod.schemas import load_schema_from_dict
    from .function_manager import FunctionManager
    svc = load_schema_from_dict(data)
    fm = FunctionManager()
    fm.add_domain_from_slots(
        domain_name=svc.service_name,
        domain_description=svc.description,
        slots={slot.name: slot.description for slot in svc.slots},
        categorical_slots={
            slot.name: slot.possible_values
            for slot in svc.slots if slot.possible_values
        } or None,
        required_slots=[slot.name for slot in svc.slots if slot.is_required] or None,
    )
    domains = fm.get_all_domains()
    if not domains:
        raise ValueError(f"Schema 文件 '{path}' 未产生任何 domain 定义")
    return domains[0]
