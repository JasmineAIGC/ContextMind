"""
Context collection step.
"""

from typing import Optional, Any
from contextmind.core import BaseStep, Context, ContextData, register_step


@register_step("collection", "Collects context from multiple sources")
class CollectionStep(BaseStep):
    """
    Collects context data from various sources.
    
    This step can use different collection strategies to gather:
    - Historical conversation data
    - Long-term memory
    - User profiles
    - Business rules
    - etc.
    
    Config options:
        - sources: List of sources to collect from (default: all)
        - max_items_per_source: Maximum items per source (default: 10)
    """
    
    def __init__(self, collection_strategy: Optional[Any] = None, **config):
        """
        Initialize collection step.
        
        Args:
            collection_strategy: Optional strategy for collection
            **config: Configuration options
        """
        super().__init__(config)
        self.strategy = collection_strategy
    
    async def execute(self, context: Context) -> Context:
        """Collect context data."""
        # If a strategy is provided, use it
        if self.strategy:
            collected_data = await self.strategy.apply(context)
            
            # Add collected data to context
            if isinstance(collected_data, list):
                for item in collected_data:
                    if isinstance(item, ContextData):
                        context.add_context_data(item)
                    elif isinstance(item, dict):
                        context.add_context_data(ContextData(
                            content=item.get("content", ""),
                            source=item.get("source", "unknown"),
                            metadata=item.get("metadata", {}),
                            score=item.get("score", 1.0)
                        ))
            elif isinstance(collected_data, dict):
                # Update context with collected data
                context.update(collected_data)
        else:
            # Default: collect from context's existing data
            # This is a placeholder - in real usage, you'd integrate
            # with actual data sources
            pass
        
        # Record collection metadata
        all_data = context.get_context_data()
        context.set_metadata("collected_items", len(all_data))
        
        # Group by source
        sources = {}
        for item in all_data:
            if item.source not in sources:
                sources[item.source] = 0
            sources[item.source] += 1
        context.set_metadata("collection_sources", sources)
        
        return context
