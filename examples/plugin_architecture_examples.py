"""
Plugin Architecture Examples

This file demonstrates how to use the ContextMind plugin architecture
for customizing memory extraction, retrieval, and update strategies.
"""

import asyncio
from contextmind import ContextEngine
from contextmind.core import Message, MessageRole


# ============================================================================
# Example 1: Basic Usage (Default Plugins)
# ============================================================================

async def example_basic_usage():
    """
    Basic usage with default plugins.
    No configuration needed - works out of the box.
    """
    print("=" * 80)
    print("Example 1: Basic Usage (Default Plugins)")
    print("=" * 80)
    
    # Create engine with default settings
    engine = ContextEngine(
        app_name="plugin-demo",
        user_id="demo-user"
    )
    
    # Use as normal - plugins work transparently
    await engine.update(
        user_input="我喜欢吃辣",
        assistant_response="好的，我记住了您喜欢吃辣的食物。"
    )
    
    # Extract knowledge (uses RuleBasedExtractor by default)
    knowledge = await engine.extract_knowledge()
    print(f"\n✓ Extracted {len(knowledge)} knowledge items")
    
    # Optimize context (uses SemanticSearchRetriever by default)
    context = await engine.optimize("推荐一些食物", include_memory=True)
    print(f"✓ Retrieved {len(context.long_term_memory)} memories")
    
    print("\n" + "=" * 80 + "\n")


# ============================================================================
# Example 2: Using Optional Components
# ============================================================================

async def example_optional_components():
    """
    Enable optional PostProcessor and Summarizer components.
    """
    print("=" * 80)
    print("Example 2: Using Optional Components")
    print("=" * 80)
    
    # Create engine with optional components enabled
    engine = ContextEngine(
        app_name="plugin-demo",
        user_id="demo-user",
        use_postprocessor=True,  # Enable output post-processing
        use_summarizer=True      # Enable conversation summarization
    )
    
    # Add some conversation
    await engine.update("你好", "你好！有什么可以帮你的？")
    await engine.update("我想了解Python", "当然，Python是一门很强大的编程语言。")
    
    # Generate summary (if summarizer is available)
    if engine.summarizer:
        messages = await engine.session_manager.get_recent_history()
        summary = await engine.summarizer.generate_summary(messages)
        print(f"\n✓ Generated summary:\n{summary}")
    
    print("\n" + "=" * 80 + "\n")


# ============================================================================
# Example 3: Custom Retriever Plugin
# ============================================================================

async def example_custom_retriever():
    """
    Demonstrate using a custom retriever plugin.
    """
    print("=" * 80)
    print("Example 3: Custom Retriever Plugin")
    print("=" * 80)
    
    from contextmind.strategies.memory import HybridRetriever
    from contextmind.pipeline import MemoryBank
    
    # Create custom memory bank with HybridRetriever
    memory_bank = MemoryBank(
        app_name="plugin-demo",
        user_id="demo-user",
        retriever=HybridRetriever(
            semantic_weight=0.7,    # 70% weight on semantic similarity
            keyword_weight=0.3       # 30% weight on keyword matching
        )
    )
    
    # Store some memories
    from contextmind.core import Knowledge, KnowledgeType
    
    test_knowledge = [
        Knowledge(
            content="用户喜欢Python编程",
            type=KnowledgeType.PREFERENCE,
            confidence=0.9
        ),
        Knowledge(
            content="用户是软件工程师",
            type=KnowledgeType.FACT,
            confidence=0.85
        )
    ]
    
    await memory_bank.store(test_knowledge)
    
    # Retrieve using hybrid retriever
    results = await memory_bank.retrieve("Python", limit=5)
    print(f"\n✓ HybridRetriever found {len(results)} relevant memories")
    for i, item in enumerate(results, 1):
        print(f"  {i}. {item.content} (score: {item.score:.2f})")
    
    print("\n" + "=" * 80 + "\n")


# ============================================================================
# Example 4: Custom Extractor Plugin
# ============================================================================

async def example_custom_extractor():
    """
    Demonstrate creating a simple custom extractor.
    """
    print("=" * 80)
    print("Example 4: Custom Extractor Plugin")
    print("=" * 80)
    
    from contextmind.strategies.memory import BaseExtractor
    from contextmind.core import Knowledge, KnowledgeType, Message
    from typing import List
    
    class SimpleKeywordExtractor(BaseExtractor):
        """
        Custom extractor that looks for specific keywords.
        """
        def __init__(self, keywords=None):
            self.keywords = keywords or ['喜欢', '讨厌', '想要']
        
        async def extract(self, messages: List[Message]) -> List[Knowledge]:
            knowledge = []
            
            for msg in messages:
                if msg.role.value != 'user':
                    continue
                
                # Check for keywords
                for keyword in self.keywords:
                    if keyword in msg.content:
                        knowledge.append(Knowledge(
                            content=msg.content,
                            type=KnowledgeType.PREFERENCE,
                            confidence=0.8,
                            metadata={'keyword': keyword}
                        ))
                        break
            
            return knowledge
    
    # Use custom extractor
    extractor = SimpleKeywordExtractor(keywords=['喜欢', '想要'])
    
    test_messages = [
        Message(role=MessageRole.USER, content="我喜欢编程"),
        Message(role=MessageRole.ASSISTANT, content="很好"),
        Message(role=MessageRole.USER, content="我想要学习AI"),
    ]
    
    knowledge = await extractor.extract(test_messages)
    print(f"\n✓ CustomExtractor extracted {len(knowledge)} items:")
    for i, k in enumerate(knowledge, 1):
        print(f"  {i}. {k.content} (confidence: {k.confidence:.2f})")
    
    print("\n" + "=" * 80 + "\n")


# ============================================================================
# Example 5: Custom Updater Plugin
# ============================================================================

async def example_custom_updater():
    """
    Demonstrate creating a simple custom updater with capacity limit.
    """
    print("=" * 80)
    print("Example 5: Custom Updater Plugin")
    print("=" * 80)
    
    from contextmind.strategies.memory import BaseUpdater
    from contextmind.core import ContextItem, ContextSource, Knowledge, KnowledgeType
    from typing import List
    
    class CapacityLimitedUpdater(BaseUpdater):
        """
        Custom updater that limits cache size and evicts oldest items.
        """
        def __init__(self, max_size=10):
            self.max_size = max_size
        
        async def update(
            self,
            memory_cache: List[ContextItem],
            new_knowledge: List[Knowledge]
        ) -> List[ContextItem]:
            # Add new items
            for k in new_knowledge:
                if k.confidence >= 0.7:  # Quality filter
                    memory_cache.append(ContextItem(
                        content=f"[{k.type.value}] {k.content}",
                        source=ContextSource.MEMORY,
                        score=k.confidence
                    ))
            
            # Evict oldest if over capacity
            if len(memory_cache) > self.max_size:
                # Keep most recent items
                memory_cache = memory_cache[-self.max_size:]
                print(f"  ⚠️  Evicted oldest items (keeping {self.max_size} most recent)")
            
            return memory_cache
    
    # Use custom updater
    from contextmind.pipeline import MemoryBank
    
    memory_bank = MemoryBank(
        app_name="plugin-demo",
        user_id="demo-user",
        updater=CapacityLimitedUpdater(max_size=5)
    )
    
    # Add knowledge items
    test_knowledge = [
        Knowledge(content=f"Memory {i}", type=KnowledgeType.FACT, confidence=0.8)
        for i in range(10)
    ]
    
    await memory_bank.store(test_knowledge)
    cache = memory_bank.get_memory_cache()
    
    print(f"\n✓ CustomUpdater maintained cache size: {len(cache)} items (max: 5)")
    
    print("\n" + "=" * 80 + "\n")


# ============================================================================
# Main: Run All Examples
# ============================================================================

async def main():
    """Run all examples."""
    print("\n" + "=" * 80)
    print("ContextMind Plugin Architecture Examples")
    print("=" * 80 + "\n")
    
    await example_basic_usage()
    await example_optional_components()
    await example_custom_retriever()
    await example_custom_extractor()
    await example_custom_updater()
    
    print("=" * 80)
    print("All examples completed!")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
