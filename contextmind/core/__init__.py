"""
ContextMind Core Module

This module provides the foundational components for the context optimization framework.
"""

from .context import Context, ContextData
from .pipeline import Pipeline, PipelineBuilder
from .registry import (
    Registry,
    StepRegistry,
    StrategyRegistry,
    get_step_registry,
    get_strategy_registry,
    register_step,
    register_strategy,
)
from .exceptions import (
    ContextMindError,
    PipelineError,
    StepError,
    StrategyError,
    ConfigError,
    ValidationError,
    RegistryError,
)
from .base import BaseStep, BaseStrategy, CompositeStep, ConditionalStep

__all__ = [
    # Context
    "Context",
    "ContextData",
    # Pipeline
    "Pipeline",
    "PipelineBuilder",
    # Registry
    "Registry",
    "StepRegistry",
    "StrategyRegistry",
    "get_step_registry",
    "get_strategy_registry",
    "register_step",
    "register_strategy",
    # Base classes
    "BaseStep",
    "BaseStrategy",
    "CompositeStep",
    "ConditionalStep",
    # Exceptions
    "ContextMindError",
    "PipelineError",
    "StepError",
    "StrategyError",
    "ConfigError",
    "ValidationError",
    "RegistryError",
]
