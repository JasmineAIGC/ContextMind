"""
场景配置模块

提供不同对话场景的配置管理
"""

from scenarios.config import ScenarioConfig, ScenarioType
from scenarios.chat_scenario import get_chat_scenario
from scenarios.callcenter_scenario import get_callcenter_scenario
from scenarios.insurance_scenario import get_insurance_scenario

__all__ = [
    'ScenarioConfig',
    'ScenarioType',
    'get_chat_scenario',
    'get_callcenter_scenario',
    'get_insurance_scenario',
]

__version__ = "0.4.0"
