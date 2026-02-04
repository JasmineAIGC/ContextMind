"""
场景配置模块

提供不同对话场景的配置管理
"""

from .config import ScenarioConfig, ScenarioType
from .chat_scenario import get_chat_scenario
from .callcenter_scenario import get_callcenter_scenario
from .insurance_scenario import get_insurance_scenario

__all__ = [
    'ScenarioConfig',
    'ScenarioType',
    'get_chat_scenario',
    'get_callcenter_scenario',
    'get_insurance_scenario',
]

__version__ = "0.2.1"
