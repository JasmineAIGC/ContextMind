"""
Prompt generation strategies.
"""

from contextmind.core import BaseStrategy, Context, register_strategy


@register_strategy("prompt", "simple", "Simple prompt generation")
class SimplePromptStrategy(BaseStrategy):
    """
    Simple prompt generation strategy.
    
    Creates a basic prompt from the integrated context.
    """
    
    async def apply(self, context: Context, **kwargs) -> str:
        """Generate simple prompt."""
        parts = []
        
        # Add system prompt if configured
        system_prompt = self.config.get("system_prompt", "You are a helpful assistant.")
        parts.append(system_prompt)
        
        # Add integrated context
        integrated = context.get("integrated_context")
        if integrated:
            parts.append(f"\nContext:\n{integrated}")
        
        # Add user input
        parts.append(f"\nUser: {context.user_input}")
        parts.append("\nAssistant:")
        
        return "\n".join(parts)


@register_strategy("prompt", "template", "Template-based prompt generation")
class TemplatePromptStrategy(BaseStrategy):
    """
    Template-based prompt generation.
    
    Uses a template with placeholders.
    """
    
    async def apply(self, context: Context, **kwargs) -> str:
        """Generate prompt from template."""
        template = self.config.get("template", """
{system_prompt}

{context}

User: {user_input}
Assistant:
        """.strip())
        
        # Prepare template variables
        variables = {
            "system_prompt": self.config.get("system_prompt", "You are a helpful assistant."),
            "user_input": context.user_input,
            "context": context.get("integrated_context", ""),
        }
        
        # Add any additional variables from context
        for key in ["history", "profile", "rules"]:
            if context.has(key):
                variables[key] = context.get(key)
        
        # Format template
        try:
            prompt = template.format(**variables)
        except KeyError as e:
            # Missing variable, use simple format
            prompt = f"{variables['system_prompt']}\n\nUser: {variables['user_input']}\nAssistant:"
        
        return prompt
