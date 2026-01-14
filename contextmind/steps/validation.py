"""
Input validation step.
"""

from contextmind.core import BaseStep, Context, register_step
from contextmind.core.exceptions import ValidationError


@register_step("validation", "Validates and preprocesses user input")
class ValidationStep(BaseStep):
    """
    Validates and preprocesses user input.
    
    Config options:
        - min_length: Minimum input length (default: 1)
        - max_length: Maximum input length (default: 10000)
        - strip_whitespace: Whether to strip whitespace (default: True)
        - reject_empty: Whether to reject empty input (default: True)
    """
    
    def __init__(self, **config):
        """Initialize with configuration."""
        super().__init__(config)
    
    async def execute(self, context: Context) -> Context:
        """Validate and preprocess input."""
        user_input = context.user_input
        
        # Strip whitespace if configured
        if self.config.get("strip_whitespace", True):
            user_input = user_input.strip()
        
        # Check if empty
        if self.config.get("reject_empty", True) and not user_input:
            raise ValidationError("User input cannot be empty")
        
        # Check length
        min_length = self.config.get("min_length", 1)
        max_length = self.config.get("max_length", 10000)
        
        if len(user_input) < min_length:
            raise ValidationError(
                f"Input too short: {len(user_input)} < {min_length}"
            )
        
        if len(user_input) > max_length:
            user_input = user_input[:max_length]
            context.set_metadata("input_truncated", True)
        
        # Update context with cleaned input
        context.set("user_input", user_input)
        context.set("input_length", len(user_input))
        
        return context
