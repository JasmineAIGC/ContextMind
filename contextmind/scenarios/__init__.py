"""
ContextMind 场景定义和应用

本模块包含:
- 场景配置定义（闲聊、客服、保险）
- Evolve 模式的应用实现
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
