"""
Postprocessing step for context engineering.

Final processing and formatting of context/output.
"""

from typing import Optional, Any
from contextmind.core import BaseStep, Context, register_step


@register_step("postprocessing", "Postprocesses and formats output")
class PostprocessingStep(BaseStep):
    """
    Postprocesses context or generated output.
    
    This step handles final transformations:
    - Output formatting
    - Response generation (if using LLM)
    - Quality checks
    - Final cleanup
    
    Config options:
        - format: Output format (default: "text")
        - include_metadata: Include metadata in output (default: False)
    """
    
    def __init__(self, processor: Optional[Any] = None, **config):
        """
        Initialize postprocessing step.
        
        Args:
            processor: Optional processor/generator
            **config: Configuration options
        """
        super().__init__(config)
        self.processor = processor
    
    async def execute(self, context: Context) -> Context:
        """Postprocess context."""
        # Get optimized context
        optimized = context.get("optimized_context", "")
        
        # Apply processor if provided (e.g., LLM for generation)
        if self.processor:
            if hasattr(self.processor, "process"):
                output = await self.processor.process(context, optimized)
            elif callable(self.processor):
                output = await self.processor(optimized)
            else:
                output = optimized
        else:
            # No processor - just format the context
            output = optimized
        
        # Format output based on config
        output_format = self.config.get("format", "text")
        
        if output_format == "json":
            import json
            output = json.dumps({
                "input": context.user_input,
                "context": optimized,
                "output": output,
                "metadata": context._metadata if self.config.get("include_metadata") else {}
            })
        elif output_format == "markdown":
            output = f"# Input\n{context.user_input}\n\n# Context\n{optimized}\n\n# Output\n{output}"
        
        # Store final output
        context.set("output", output)
        context.set_metadata("output_length", len(str(output)))
        context.set_metadata("output_format", output_format)
        
        return context
