"""
Context integration step.
"""

from contextmind.core import BaseStep, Context, register_step


@register_step("integration", "Integrates collected context into structured knowledge")
class IntegrationStep(BaseStep):
    """
    Integrates collected context data into structured knowledge.
    
    This step combines context from various sources and creates
    a unified representation that can be used for prompt generation.
    
    Config options:
        - integration_method: Method to use (default: "concat")
        - max_total_length: Maximum total context length (default: 5000)
        - prioritize_by_score: Whether to prioritize by score (default: True)
    """
    
    def __init__(self, **config):
        """Initialize with configuration."""
        super().__init__(config)
    
    async def execute(self, context: Context) -> Context:
        """Integrate context data."""
        # Get all collected context data
        all_data = context.get_context_data()
        
        # Sort by score if configured
        if self.config.get("prioritize_by_score", True):
            all_data = sorted(all_data, key=lambda x: x.score, reverse=True)
        
        # Integrate based on method
        method = self.config.get("integration_method", "concat")
        max_length = self.config.get("max_total_length", 5000)
        
        if method == "concat":
            # Simple concatenation
            integrated_parts = []
            total_length = 0
            
            for item in all_data:
                content_length = len(item.content)
                if total_length + content_length > max_length:
                    break
                integrated_parts.append(f"[{item.source}] {item.content}")
                total_length += content_length
            
            integrated_context = "\n\n".join(integrated_parts)
        
        elif method == "structured":
            # Structured by source
            by_source = {}
            for item in all_data:
                if item.source not in by_source:
                    by_source[item.source] = []
                by_source[item.source].append(item.content)
            
            integrated_parts = []
            for source, contents in by_source.items():
                integrated_parts.append(f"## {source}\n" + "\n".join(contents))
            
            integrated_context = "\n\n".join(integrated_parts)
        
        else:
            integrated_context = ""
        
        # Store integrated context
        context.set("integrated_context", integrated_context)
        context.set("integration_method", method)
        context.set_metadata("integrated_length", len(integrated_context))
        
        return context
