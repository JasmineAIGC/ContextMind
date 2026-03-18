"""闲聊场景应用（向后兼容薄层，实现由 scenarios.app.EvolveApplication 提供）。"""
from contextmind.scenarios.app import EvolveApplication as ChatApplication
from contextmind.scenarios.prompts import CHAT_SYSTEM_PROMPT

__all__ = ["ChatApplication", "CHAT_SYSTEM_PROMPT"]
