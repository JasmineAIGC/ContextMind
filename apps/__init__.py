"""
Apps Module - 场景应用工厂

提供统一的应用创建接口，简化Evolve模式的初始化。

使用示例：
    from apps import create_app_for_scenario
    app = create_app_for_scenario("chat", llm_client, config)
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from utils.llm_client import SimpleLLMClient
    from scenarios.scenario_config import ScenarioConfig


def create_app_for_scenario(scenario_name: str, llm_client, scenario_config, app_name_prefix: str = "demo"):
    """
    为指定场景创建应用实例的工厂方法
    
    Args:
        scenario_name: 场景名称 ("chat", "callcenter", "insurance" 等)
        llm_client: LLM客户端实例
        scenario_config: 场景配置对象
        app_name_prefix: 应用名称前缀（默认 "demo"）
        
    Returns:
        对应场景的Application实例
        
    Raises:
        ValueError: 如果场景不支持
    """
    from evolve import EvolveEngine
    from apps.chat_app import ChatApplication
    from apps.callcenter_app import CallCenterApplication
    from apps.insurance_app import InsuranceApplication
    
    # 创建引擎
    engine = EvolveEngine(
        app_name=f"{app_name_prefix}_{scenario_name}",
        user_id=f"{app_name_prefix}_user",
        llm_client=llm_client
    )
    
    # 根据场景创建对应的应用
    scenario_lower = scenario_name.lower()
    system_prompt = scenario_config.system_prompt
    
    if scenario_lower in ["chat", "闲聊"]:
        return ChatApplication(context_engine=engine, system_prompt=system_prompt)
    elif scenario_lower in ["callcenter", "客服"]:
        return CallCenterApplication(context_engine=engine, system_prompt=system_prompt)
    elif scenario_lower in ["insurance", "保险", "保险挽回"]:
        return InsuranceApplication(context_engine=engine, system_prompt=system_prompt)
    else:
        raise ValueError(f"不支持的场景: {scenario_name}。支持的场景: chat, callcenter, insurance")


__all__ = ['create_app_for_scenario']
