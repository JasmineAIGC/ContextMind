"""
Optimization step for context engineering.

Optimizes context for specific downstream tasks (e.g., LLM prompting).
"""

from typing import Optional, Any
from contextmind.core import BaseStep, Context, register_step


@register_step("optimization", "Optimizes context for downstream tasks")
class OptimizationStep(BaseStep):
    """
    Optimizes context for specific tasks.
    
    This step can apply various optimization strategies:
    - Compression
    - Reranking
    - Formatting
    - Prompt engineering
    
    Config options:
        - strategy: Optimization strategy to use
        - target_length: Target context length (default: None)
    """
    
    def __init__(self, optimization_strategy: Optional[Any] = None, **config):
        """
        Initialize optimization step.
        
        Args:
            optimization_strategy: Strategy for optimization
            **config: Configuration options
        """
        super().__init__(config)
        self.strategy = optimization_strategy
    
    async def execute(self, context: Context) -> Context:
        """Optimize context."""
        # Get augmented context
        augmented = context.get("augmented_context", "")
        
        # Apply optimization strategy if provided
        if self.strategy:
            optimized = await self.strategy.apply(context, content=augmented)
        else:
            # Default: pass through
            optimized = augmented
        
        # Apply length constraint if specified
        target_length = self.config.get("target_length")
        if target_length and len(optimized) > target_length:
            # Simple truncation (can be overridden by strategy)
            optimized = optimized[:target_length]
            context.set_metadata("optimization_truncated", True)
        
        # Store optimized context
        context.set("optimized_context", optimized)
        context.set_metadata("optimized_length", len(optimized))
        
        return context
