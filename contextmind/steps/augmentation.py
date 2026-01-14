"""
Augmentation step for context engineering.

Augments and enriches context with additional information.
"""

from contextmind.core import BaseStep, Context, register_step


@register_step("augmentation", "Augments context with additional information")
class AugmentationStep(BaseStep):
    """
    Augments context with additional information.
    
    This step enriches the retrieved context by:
    - Merging multiple sources
    - Adding metadata
    - Applying transformations
    - Organizing structure
    
    Config options:
        - method: Augmentation method (default: "merge")
        - max_length: Maximum total length (default: 5000)
        - include_sources: Whether to include source labels (default: True)
    """
    
    def __init__(self, **config):
        """Initialize with configuration."""
        super().__init__(config)
    
    async def execute(self, context: Context) -> Context:
        """Augment context."""
        # Get all context data
        all_data = context.get_context_data()
        
        # Sort by score
        all_data = sorted(all_data, key=lambda x: x.score, reverse=True)
        
        # Augment based on method
        method = self.config.get("method", "merge")
        max_length = self.config.get("max_length", 5000)
        include_sources = self.config.get("include_sources", True)
        
        if method == "merge":
            # Simple merge with source labels
            parts = []
            total_length = 0
            
            for item in all_data:
                if total_length >= max_length:
                    break
                
                if include_sources:
                    content = f"[{item.source}] {item.content}"
                else:
                    content = item.content
                
                parts.append(content)
                total_length += len(content)
            
            augmented = "\n\n".join(parts)
        
        elif method == "structured":
            # Group by source
            by_source = {}
            for item in all_data:
                if item.source not in by_source:
                    by_source[item.source] = []
                by_source[item.source].append(item.content)
            
            parts = []
            for source, contents in by_source.items():
                if include_sources:
                    parts.append(f"## {source}\n" + "\n".join(contents))
                else:
                    parts.extend(contents)
            
            augmented = "\n\n".join(parts)
        
        else:
            # Simple concatenation
            augmented = "\n".join(item.content for item in all_data)
        
        # Truncate if needed
        if len(augmented) > max_length:
            augmented = augmented[:max_length]
            context.set_metadata("context_truncated", True)
        
        # Store augmented context
        context.set("augmented_context", augmented)
        context.set_metadata("augmented_length", len(augmented))
        context.set_metadata("augmentation_method", method)
        
        return context
