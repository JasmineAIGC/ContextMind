"""
Retrieval strategies for context collection.
"""

from typing import List, Dict, Any
from contextmind.core import BaseStrategy, Context, ContextData, register_strategy


@register_strategy("retrieval", "simple", "Simple retrieval strategy")
class SimpleRetrievalStrategy(BaseStrategy):
    """
    Simple retrieval strategy that returns mock data.
    
    This is a placeholder strategy for demonstration.
    """
    
    async def apply(self, context: Context, **kwargs) -> List[ContextData]:
        """Apply simple retrieval."""
        # Return some mock context data
        return [
            ContextData(
                content="This is historical context from previous conversation.",
                source="history",
                score=0.9
            ),
            ContextData(
                content="User prefers detailed explanations.",
                source="profile",
                score=0.8
            )
        ]


@register_strategy("retrieval", "keyword", "Keyword-based retrieval")
class KeywordRetrievalStrategy(BaseStrategy):
    """
    Keyword-based retrieval strategy.
    
    Retrieves context based on keyword matching.
    """
    
    async def apply(self, context: Context, **kwargs) -> List[ContextData]:
        """Apply keyword retrieval."""
        user_input = context.user_input.lower()
        
        # Mock knowledge base
        knowledge_base = [
            {
                "content": "Product A costs $100",
                "keywords": ["product", "price", "cost"],
                "source": "knowledge_base"
            },
            {
                "content": "We offer 24/7 customer support",
                "keywords": ["support", "help", "service"],
                "source": "knowledge_base"
            },
            {
                "content": "Shipping takes 3-5 business days",
                "keywords": ["shipping", "delivery", "time"],
                "source": "knowledge_base"
            }
        ]
        
        # Find matching items
        results = []
        for item in knowledge_base:
            score = 0.0
            for keyword in item["keywords"]:
                if keyword in user_input:
                    score += 0.3
            
            if score > 0:
                results.append(ContextData(
                    content=item["content"],
                    source=item["source"],
                    score=min(score, 1.0)
                ))
        
        return results
