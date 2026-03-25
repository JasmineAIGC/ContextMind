"""
保险销售场景包

包含保险销售场景的配置（ScenarioConfig）。
"""

from .scenario import get_insurance_scenario
from contextmind.scenarios.app import EvolveApplication as InsuranceApplication

__all__ = ["get_insurance_scenario", "InsuranceApplication"]
