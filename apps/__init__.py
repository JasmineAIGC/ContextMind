"""
Apps Module - 场景应用（已弃用）

警告：此模块已弃用！

从 v0.2.1 开始，create_app_for_scenario() 已移至 evolve 模块。
请使用以下导入方式：

    from evolve import create_app_for_scenario

此模块保留是为了向后兼容，将在未来版本中移除。
"""

import warnings
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from utils.llm_client import SimpleLLMClient
    from scenarios.scenario_config import ScenarioConfig


def create_app_for_scenario(scenario_name: str, llm_client, scenario_config, app_name_prefix: str = "demo"):
    """
    为指定场景创建应用实例的工厂方法（已弃用）
    
    警告：此函数已移至 evolve 模块，请使用：
        from evolve import create_app_for_scenario
    
    Args:
        scenario_name: 场景名称 ("chat", "callcenter", "insurance" 等)
        llm_client: LLM客户端实例
        scenario_config: 场景配置对象
        app_name_prefix: 应用名称前缀（默认 "demo"）
        
    Returns:
        对应场景的Application实例
    """
    warnings.warn(
        "apps.create_app_for_scenario 已弃用，请使用 evolve.create_app_for_scenario",
        DeprecationWarning,
        stacklevel=2
    )
    
    # 重定向到evolve模块
    from evolve import create_app_for_scenario as evolve_factory
    return evolve_factory(scenario_name, llm_client, scenario_config, app_name_prefix)


__all__ = ['create_app_for_scenario']

