"""
ContextMind 场景定义和应用

本模块包含：
- 场景基础配置（ScenarioConfig、ScenarioType）
- 系统提示词（prompts）
- 场景注册表（scenario_registry）及 YAML 配置（scenarios.yaml）
- 三个内置场景包（chat / callcenter / insurance）
- 安意化（anyihua）专属场景

每个场景子包均提供：
  - ``get_<name>_scenario()`` — 返回 ScenarioConfig 配置对象
  - ``<Name>Application``    — 该场景的 Evolve 应用类
"""

from .base import ScenarioConfig, ScenarioType
from .registry import scenario_registry
from .chat import get_chat_scenario, ChatApplication
from .callcenter import get_callcenter_scenario, CallCenterApplication
from .insurance import get_insurance_scenario, InsuranceApplication

__all__ = [
    # 基础配置类
    'ScenarioConfig',
    'ScenarioType',
    # 场景注册表
    'scenario_registry',
    # 场景配置工厂函数
    'get_chat_scenario',
    'get_callcenter_scenario',
    'get_insurance_scenario',
    # Evolve 应用类
    'ChatApplication',
    'CallCenterApplication',
    'InsuranceApplication',
]

__version__ = "0.2.1"
