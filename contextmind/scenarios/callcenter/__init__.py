"""
客服场景包

包含客服场景的配置（ScenarioConfig）和 Evolve 应用（CallCenterApplication）。
"""

from .scenario import get_callcenter_scenario
from .app import CallCenterApplication

__all__ = ["get_callcenter_scenario", "CallCenterApplication"]
