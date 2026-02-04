"""
Configuration management for ContextMind

This module handles:
- Scenario registry: Manages scenario definitions and their associated components
- Scenario configuration: Loads and validates scenario configurations from YAML
"""

from contextmind.config.registry import scenario_registry

__all__ = ["scenario_registry"]
