"""
Response generation step.
"""

from typing import Optional, Any
from contextmind.core import BaseStep, Context, register_step


@register_step("generation", "Generates response using LLM")
class GenerationStep(BaseStep):
    """
    Generates response using a language model.
    
    This step takes the prompt and uses an LLM to generate a response.
    
    Config options:
        - max_retries: Maximum retry attempts (default: 3)
        - timeout: Timeout in seconds (default: 30)
    """
    
    def __init__(self, generator: Optional[Any] = None, **config):
        """
        Initialize generation step.
        
        Args:
            generator: Optional LLM generator/client
            **config: Configuration options
        """
        super().__init__(config)
        self.generator = generator
    
    async def execute(self, context: Context) -> Context:
        """Generate response."""
        # Get the prompt from context
        prompt = context.get("prompt")
        
        if not prompt:
            # If no prompt, create a simple one
            prompt = self._create_default_prompt(context)
        
        # Generate response
        if self.generator:
            max_retries = self.config.get("max_retries", 3)
            
            for attempt in range(max_retries):
                try:
                    # Call generator
                    if hasattr(self.generator, "generate"):
                        response = await self._call_generator(prompt)
                    else:
                        # Assume it's a callable
                        response = await self.generator(prompt)
                    
                    # Validate response
                    if response and len(response.strip()) > 0:
                        break
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    # Retry
                    continue
        else:
            # No generator provided - return placeholder
            response = f"[Generated response for: {context.user_input}]"
        
        # Store response
        context.set("response", response)
        context.set_metadata("response_length", len(response))
        
        return context
    
    async def _call_generator(self, prompt: str) -> str:
        """Call the generator."""
        import asyncio
        
        # Check if it's async
        if asyncio.iscoroutinefunction(self.generator.generate):
            result = await self.generator.generate(prompt)
        else:
            result = self.generator.generate(prompt)
        
        # Handle different return formats
        if isinstance(result, tuple):
            # (reasoning, response) format
            return result[1] if len(result) > 1 else result[0]
        else:
            return str(result)
    
    def _create_default_prompt(self, context: Context) -> str:
        """Create a default prompt if none provided."""
        parts = []
        
        # Add integrated context if available
        integrated = context.get("integrated_context")
        if integrated:
            parts.append(f"Context:\n{integrated}\n")
        
        # Add user input
        parts.append(f"User: {context.user_input}\n")
        parts.append("Assistant:")
        
        return "\n".join(parts)
