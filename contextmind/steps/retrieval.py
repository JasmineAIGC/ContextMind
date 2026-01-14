"""
Retrieval step for context engineering.

Retrieves relevant context from various sources using pluggable strategies.
"""

from typing import Optional, Any
from contextmind.core import BaseStep, Context, ContextData, register_step


@register_step("retrieval", "Retrieves relevant context from sources")
class RetrievalStep(BaseStep):
    """
    Retrieves context data from various sources.
    
    This is a general retrieval step that uses pluggable strategies
    to fetch relevant information from:
    - Knowledge bases
    - Databases
    - Vector stores
    - APIs
    - etc.
    
    Config options:
        - max_results: Maximum number of results (default: 10)
        - min_score: Minimum relevance score (default: 0.0)
    """
    
    def __init__(self, retrieval_strategy: Optional[Any] = None, **config):
        """
        Initialize retrieval step.
        
        Args:
            retrieval_strategy: Strategy for retrieval
            **config: Configuration options
        """
        super().__init__(config)
        self.strategy = retrieval_strategy
    
    async def execute(self, context: Context) -> Context:
        """Retrieve relevant context."""
        # Use strategy if provided
        if self.strategy:
            # Get query from context (could be processed_input or user_input)
            query = context.get("processed_input", context.user_input)
            
            # Apply retrieval strategy
            retrieved_data = await self.strategy.apply(context, query=query)
            
            # Add to context
            if isinstance(retrieved_data, list):
                for item in retrieved_data:
                    if isinstance(item, ContextData):
                        context.add_context_data(item)
                    elif isinstance(item, dict):
                        context.add_context_data(ContextData(
                            content=item.get("content", ""),
                            source=item.get("source", "retrieval"),
                            metadata=item.get("metadata", {}),
                            score=item.get("score", 1.0)
                        ))
        
        # Filter by score if configured
        min_score = self.config.get("min_score", 0.0)
        max_results = self.config.get("max_results", 10)
        
        all_data = context.get_context_data()
        filtered_data = [d for d in all_data if d.score >= min_score]
        filtered_data = sorted(filtered_data, key=lambda x: x.score, reverse=True)[:max_results]
        
        # Store metadata
        context.set_metadata("retrieved_count", len(filtered_data))
        context.set_metadata("retrieval_sources", list(set(d.source for d in filtered_data)))
        
        return context
