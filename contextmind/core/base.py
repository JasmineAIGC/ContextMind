"""
Base classes for pipeline steps and strategies.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List

from .context import Context
from .exceptions import StepError, StrategyError


class BaseStep(ABC):
    """
    Base class for all pipeline steps.
    
    A step is a unit of processing that transforms the context.
    Steps should be stateless and idempotent when possible.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize step.
        
        Args:
            config: Step configuration
        """
        self.config = config or {}
        self.name = self.__class__.__name__
    
    @abstractmethod
    async def execute(self, context: Context) -> Context:
        """
        Execute the step.
        
        Args:
            context: Input context
            
        Returns:
            Modified context
            
        Raises:
            StepError: If step execution fails
        """
        pass
    
    def validate_context(self, context: Context) -> None:
        """
        Validate context before execution.
        
        Args:
            context: Context to validate
            
        Raises:
            StepError: If validation fails
        """
        pass
    
    def get_required_keys(self) -> List[str]:
        """
        Get list of required context keys.
        
        Returns:
            List of required keys
        """
        return []
    
    def should_execute(self, context: Context) -> bool:
        """
        Determine if step should execute.
        
        Args:
            context: Current context
            
        Returns:
            True if step should execute, False to skip
        """
        return True
    
    def __repr__(self) -> str:
        """String representation."""
        return f"{self.__class__.__name__}(config={self.config})"


class BaseStrategy(ABC):
    """
    Base class for all strategies.
    
    Strategies are pluggable algorithms that can be swapped within steps.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize strategy.
        
        Args:
            config: Strategy configuration
        """
        self.config = config or {}
        self.name = self.__class__.__name__
    
    @abstractmethod
    async def apply(self, context: Context, **kwargs) -> Any:
        """
        Apply the strategy.
        
        Args:
            context: Current context
            **kwargs: Additional arguments
            
        Returns:
            Strategy result
            
        Raises:
            StrategyError: If strategy fails
        """
        pass
    
    def validate_config(self) -> None:
        """
        Validate strategy configuration.
        
        Raises:
            StrategyError: If configuration is invalid
        """
        pass
    
    def __repr__(self) -> str:
        """String representation."""
        return f"{self.__class__.__name__}(config={self.config})"


class CompositeStep(BaseStep):
    """
    A step that composes multiple sub-steps.
    
    Useful for creating reusable step groups.
    """
    
    def __init__(self, steps: List[BaseStep], **config):
        """
        Initialize composite step.
        
        Args:
            steps: List of sub-steps
            **config: Configuration
        """
        super().__init__(config)
        self.steps = steps
    
    async def execute(self, context: Context) -> Context:
        """Execute all sub-steps in sequence."""
        for step in self.steps:
            context = await step.execute(context)
        return context


class ConditionalStep(BaseStep):
    """
    A step that executes conditionally.
    
    Wraps another step and only executes it if condition is met.
    """
    
    def __init__(
        self,
        step: BaseStep,
        condition: callable,
        **config
    ):
        """
        Initialize conditional step.
        
        Args:
            step: The step to execute conditionally
            condition: Function that takes context and returns bool
            **config: Configuration
        """
        super().__init__(config)
        self.step = step
        self.condition = condition
    
    async def execute(self, context: Context) -> Context:
        """Execute step if condition is met."""
        if self.condition(context):
            return await self.step.execute(context)
        return context
