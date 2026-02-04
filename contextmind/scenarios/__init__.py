"""
Scenario definitions and applications for ContextMind

This module contains:
- Scenario configuration definitions (chat, callcenter, insurance)
- Application implementations for Evolve mode
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
