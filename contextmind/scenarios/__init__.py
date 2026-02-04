"""
Scenario definitions and applications for ContextMind

This module contains:
- config: Scenario configuration definitions (chat, callcenter, insurance)
- apps: Application implementations for Evolve mode
"""

# Import scenario configurations
from contextmind.scenarios.config import (
    get_chat_scenario,
    get_callcenter_scenario,
    get_insurance_scenario,
)

__all__ = [
    "get_chat_scenario",
    "get_callcenter_scenario",
    "get_insurance_scenario",
]
