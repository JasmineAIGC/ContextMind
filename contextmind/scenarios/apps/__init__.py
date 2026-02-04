"""
Application implementations for scenarios (Evolve mode)

Contains application classes for different scenarios:
- ChatApplication: Chat scenario application
- CallCenterApplication: Customer service scenario application
- InsuranceApplication: Insurance retention scenario application
"""

from contextmind.scenarios.apps.chat_app import ChatApplication
from contextmind.scenarios.apps.callcenter_app import CallCenterApplication
from contextmind.scenarios.apps.insurance_app import InsuranceApplication

__all__ = [
    "ChatApplication",
    "CallCenterApplication",
    "InsuranceApplication",
]
