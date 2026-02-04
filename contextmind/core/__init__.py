"""
Core framework components for ContextMind

This module contains:
- config: Configuration management and scenario registry
- common: Shared utilities, prompts, and UI components
"""

from contextmind.core.config.registry import scenario_registry

__all__ = ["scenario_registry"]
