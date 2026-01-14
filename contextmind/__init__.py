"""
ContextMind - Universal Context Optimization Framework

A flexible, extensible framework for context optimization that supports
pluggable steps and strategies for various use cases.
"""

# New framework exports
from .core import (
    Context,
    ContextData,
    Pipeline,
    PipelineBuilder,
    BaseStep,
    BaseStrategy,
    register_step,
    register_strategy,
    get_step_registry,
    get_strategy_registry,
)

# Import steps and strategies to register them
from . import steps
from . import strategies

# Legacy exports (optional - can be removed in future)
# Commented out to avoid dependency issues
# from .client import Client, ClientConfig
# from .engine import ContextEngine, ContextTurnResult
# from .logger import get_logger, setup_logging, ContextMindLogger

__all__ = [
    # Core framework
    "Context",
    "ContextData",
    "Pipeline",
    "PipelineBuilder",
    "BaseStep",
    "BaseStrategy",
    "register_step",
    "register_strategy",
    "get_step_registry",
    "get_strategy_registry",
]

__version__ = "2.0.0"
