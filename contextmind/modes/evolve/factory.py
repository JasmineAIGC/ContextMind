"""
Evolve 场景工厂

提供 ``create_app_for_scenario()`` 工厂函数，根据场景名称创建对应的
Application 实例，将 EvolveEngine 初始化逻辑与包的 ``__init__.py`` 解耦。
"""

from __future__ import annotations

from .engine import EvolveEngine


def create_app_for_scenario(
    scenario_name: str,
    llm_client,
    scenario_config,
    app_name_prefix: str = "demo",
):
    """
    为指定场景创建应用实例的工厂方法。

    Args:
        scenario_name:   场景名称（支持中英文别名）
        llm_client:      LLM 客户端实例
        scenario_config: 场景配置对象
        app_name_prefix: 应用名称前缀

    Returns:
        对应场景的 Application 实例

    Raises:
        ValueError: 如果场景未注册

    Example:
        app = create_app_for_scenario("chat", llm_client, config)
    """
    from contextmind.config.registry import scenario_registry

    engine = EvolveEngine(
        app_name=f"{app_name_prefix}_{scenario_name}",
        user_id=f"{app_name_prefix}_user",
        llm_client=llm_client,
    )

    app_class = scenario_registry.get_app_class(scenario_name)

    if app_class is None:
        available_scenarios = scenario_registry.list_scenarios()
        raise ValueError(
            f"场景 '{scenario_name}' 未注册。\n"
            f"可用场景: {', '.join(available_scenarios)}\n"
            f"提示: 使用 scenario_registry.register() 注册新场景"
        )

    system_prompt = scenario_config.system_prompt
    return app_class(evolve_engine=engine, system_prompt=system_prompt, llm_client=llm_client)
