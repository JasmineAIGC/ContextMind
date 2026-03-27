"""
客服场景包

包含客服场景的配置（ScenarioConfig）。
"""

from .scenario import get_callcenter_scenario
from contextmind.modes.evolve.app import EvolveApplication as CallCenterApplication

__all__ = ["get_callcenter_scenario", "CallCenterApplication"]
