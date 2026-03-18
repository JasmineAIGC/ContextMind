"""客服场景应用（向后兼容薄层，实现由 scenarios.app.EvolveApplication 提供）。"""
from contextmind.scenarios.app import EvolveApplication as CallCenterApplication
from contextmind.scenarios.prompts import CALLCENTER_SYSTEM_PROMPT

__all__ = ["CallCenterApplication", "CALLCENTER_SYSTEM_PROMPT"]
