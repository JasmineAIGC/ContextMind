"""
保险挽回场景包

包含保险挽回场景的配置（ScenarioConfig）和 Evolve 应用（InsuranceApplication）。
"""

from .scenario import get_insurance_scenario
from .app import InsuranceApplication

__all__ = ["get_insurance_scenario", "InsuranceApplication"]
