"""
Preprocessing step for context engineering.

Handles input normalization, validation, and initial transformations.
"""

from contextmind.core import BaseStep, Context, register_step
from contextmind.core.exceptions import ValidationError


@register_step("preprocessing", "Preprocesses and normalizes input")
class PreprocessingStep(BaseStep):
    """
    Preprocesses input for context engineering pipeline.
    
    This is a general preprocessing step that can handle various
    input types and transformations.
    
    Config options:
        - normalize: Whether to normalize text (default: True)
        - min_length: Minimum input length (default: 0)
        - max_length: Maximum input length (default: None)
        - encoding: Text encoding (default: "utf-8")
    """
    
    def __init__(self, **config):
        """Initialize with configuration."""
        super().__init__(config)
    
    async def execute(self, context: Context) -> Context:
        """Preprocess input."""
        user_input = context.user_input
        
        # Normalize if configured
        if self.config.get("normalize", True):
            user_input = user_input.strip()
            # Remove multiple spaces
            import re
            user_input = re.sub(r'\s+', ' ', user_input)
        
        # Validate length
        min_length = self.config.get("min_length", 0)
        max_length = self.config.get("max_length")
        
        if min_length > 0 and len(user_input) < min_length:
            raise ValidationError(
                f"Input too short: {len(user_input)} < {min_length}"
            )
        
        if max_length and len(user_input) > max_length:
            user_input = user_input[:max_length]
            context.set_metadata("input_truncated", True)
        
        # Store processed input
        context.set("processed_input", user_input)
        context.set("input_length", len(user_input))
        
        return context
