"""
聊天场景包

包含聊天场景的配置（ScenarioConfig）和 Evolve 应用（ChatApplication）。
"""

from .scenario import get_chat_scenario
from .app import ChatApplication

__all__ = ["get_chat_scenario", "ChatApplication"]
