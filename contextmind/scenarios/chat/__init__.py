"""
聊天场景包

包含聊天场景的配置（ScenarioConfig）。
"""

from .scenario import get_chat_scenario
from contextmind.scenarios.app import EvolveApplication as ChatApplication

__all__ = ["get_chat_scenario", "ChatApplication"]
