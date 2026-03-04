"""
FnCTOD 场景函数 Schema 加载器

从 schemas.yaml 加载各场景（闲聊、客服、保险）的函数调用 Schema，
将纯数据定义与 Python 代码分离。

公开 API（向后兼容）：
    get_chat_function_schema()        — 获取闲聊场景 DomainSpec
    get_callcenter_function_schema()  — 获取客服场景 DomainSpec
    get_insurance_function_schema()   — 获取保险场景 DomainSpec
    get_function_schema_for_scenario(name) — 按场景名称获取 DomainSpec

扩展方法：在 schemas.yaml 中添加新 schema 条目，无需修改本文件。
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Optional

import yaml

from .function_manager import DomainSpec, FunctionParameter, ParameterType


_SCHEMAS_YAML = Path(__file__).parent / "schemas.yaml"


def _load_yaml() -> dict:
    """加载并缓存 schemas.yaml 文件内容。"""
    with open(_SCHEMAS_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_domain_spec(data: dict) -> DomainSpec:
    """将 YAML 字典转换为 DomainSpec 对象。"""
    schema = DomainSpec(name=data["name"], description=data["description"])
    for param in data.get("parameters", []):
        schema.add_parameter(FunctionParameter(
            name=param["name"],
            description=param.get("description", ""),
            param_type=ParameterType.STRING,  # 当前所有参数均为 string 类型
            required=param.get("required", False),
            enum_values=param.get("enum"),
        ))
    return schema


@functools.lru_cache(maxsize=None)
def _get_all_schemas() -> dict[str, DomainSpec]:
    """加载所有 schema，结果缓存以避免重复 I/O。"""
    raw = _load_yaml()
    return {name: _build_domain_spec(spec) for name, spec in raw.items()}


def get_chat_function_schema() -> DomainSpec:
    """获取闲聊场景的函数 Schema。"""
    return _get_all_schemas()["chat"]


def get_callcenter_function_schema() -> DomainSpec:
    """获取客服场景的函数 Schema。"""
    return _get_all_schemas()["callcenter"]


def get_insurance_function_schema() -> DomainSpec:
    """获取保险场景的函数 Schema。"""
    return _get_all_schemas()["insurance"]


def get_function_schema_for_scenario(scenario_name: str) -> DomainSpec:
    """
    根据场景名称获取对应的函数 Schema。

    优先从 scenarios.yaml 注册表获取；若未注册，则尝试直接从 schemas.yaml 匹配。

    Args:
        scenario_name: 场景名称（支持中英文别名）

    Returns:
        DomainSpec: 对应场景的函数规格

    Raises:
        ValueError: 场景未注册且 schemas.yaml 中没有对应条目
    """
    from contextmind.scenarios.registry import scenario_registry

    schema = scenario_registry.get_schema(scenario_name)
    if schema is not None:
        return schema

    # 回退：直接匹配 schemas.yaml 中的 key
    all_schemas = _get_all_schemas()
    if scenario_name in all_schemas:
        return all_schemas[scenario_name]

    available = list(all_schemas.keys()) + scenario_registry.list_scenarios()
    raise ValueError(
        f"场景 '{scenario_name}' 未注册且 schemas.yaml 中没有对应条目。\n"
        f"可用场景: {', '.join(sorted(set(available)))}\n"
        f"请在 schemas.yaml 中添加新 schema，或在 scenarios.yaml 中注册。"
    )
