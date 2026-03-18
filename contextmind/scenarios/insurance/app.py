"""保险场景应用（向后兼容薄层，实现由 scenarios.app.EvolveApplication 提供）。"""
from contextmind.scenarios.app import EvolveApplication as InsuranceApplication
from contextmind.scenarios.prompts import INSURANCE_SYSTEM_PROMPT

__all__ = ["InsuranceApplication", "INSURANCE_SYSTEM_PROMPT"]
