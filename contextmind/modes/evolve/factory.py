"""
Evolve 场景工厂

``create_app_for_scenario()`` 根据场景名称创建对应的 EvolveApplication，
将 EvolveEngine 初始化逻辑与 ``__init__.py`` 解耦。
"""

from __future__ import annotations

from .core.engine import EvolveEngine
from .app import EvolveApplication


def create_app_for_scenario(
    scenario_name: str,
    llm_client,
    scenario_config,
    app_name_prefix: str = "demo",
):
    """为指定场景创建 EvolveApplication 实例。

    Args:
        scenario_name:   场景名称（支持中英文别名，如 "chat"、"闲聊"）。
        llm_client:      LLM 客户端（AdkLLMClient）。
        scenario_config: ScenarioConfig 场景配置对象。
        app_name_prefix: ADK app_name 前缀。

    Returns:
        EvolveApplication 实例。

    Raises:
        ValueError: 场景未注册。
    """
    from contextmind.scenarios.registry import scenario_registry

    engine = EvolveEngine(
        app_name=f"{app_name_prefix}_{scenario_name}",
        user_id=f"{app_name_prefix}_user",
        llm_client=llm_client,
    )

    # 尝试从注册表获取 app_class（仍支持自定义子类场景）
    app_class = scenario_registry.get_app_class(scenario_name)
    if app_class is None:
        available = scenario_registry.list_scenarios()
        raise ValueError(
            f"场景 '{scenario_name}' 未注册。可用场景: {', '.join(available)}"
        )

    # 所有内置场景的 app_class 指向 EvolveApplication（或其子类）
    return app_class(
        evolve_engine=engine,
        system_prompt=scenario_config.system_prompt,
        llm_client=llm_client,
    )
