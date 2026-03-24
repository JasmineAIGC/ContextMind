"""
安逸花外呼场景包

包含安逸花外呼场景的配置（ScenarioConfig）。
"""

from .scenario import get_anyihua_scenario
from contextmind.scenarios.app import EvolveApplication as AnyihuaApplication

__all__ = ["get_anyihua_scenario", "AnyihuaApplication"]
