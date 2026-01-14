"""
Custom exceptions for ContextMind framework.
"""


class ContextMindError(Exception):
    """Base exception for all ContextMind errors."""
    pass


class PipelineError(ContextMindError):
    """Raised when pipeline execution fails."""
    pass


class StepError(ContextMindError):
    """Raised when a step execution fails."""
    pass


class StrategyError(ContextMindError):
    """Raised when a strategy fails."""
    pass


class ConfigError(ContextMindError):
    """Raised when configuration is invalid."""
    pass


class ValidationError(ContextMindError):
    """Raised when validation fails."""
    pass


class RegistryError(ContextMindError):
    """Raised when registry operations fail."""
    pass
