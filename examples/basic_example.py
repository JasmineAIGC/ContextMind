"""
Example demonstrating the new ContextMind framework.
"""

import asyncio
import sys
sys.path.insert(0, '/home/runner/work/ContextMind/ContextMind')

from contextmind.core import Context, PipelineBuilder
from contextmind.steps import ValidationStep, CollectionStep, IntegrationStep, GenerationStep
from contextmind.strategies import KeywordRetrievalStrategy


async def main():
    """Run example pipeline."""
    print("=" * 60)
    print("ContextMind Framework Example")
    print("=" * 60)
    
    # Create a pipeline using the builder
    pipeline = PipelineBuilder("example_pipeline") \
        .add_step("validation", min_length=1, max_length=1000) \
        .add_custom_step(
            "collection",
            CollectionStep(collection_strategy=KeywordRetrievalStrategy())
        ) \
        .add_step("integration", integration_method="structured") \
        .add_custom_step(
            "generation",
            GenerationStep()
        ) \
        .set_config(strict_mode=False) \
        .build()
    
    print(f"\nPipeline: {pipeline}")
    print(f"Steps: {pipeline.list_steps()}")
    
    # Test inputs
    test_inputs = [
        "What is the price of Product A?",
        "Do you offer customer support?",
        "How long does shipping take?",
    ]
    
    for i, user_input in enumerate(test_inputs, 1):
        print(f"\n{'='*60}")
        print(f"Example {i}: {user_input}")
        print(f"{'='*60}")
        
        # Create context
        context = Context(user_input=user_input)
        
        # Execute pipeline
        result = await pipeline.execute(context)
        
        # Display results
        print(f"\n✓ Input: {result.user_input}")
        
        # Show collected context
        collected = result.get_context_data()
        if collected:
            print(f"\n📚 Collected Context ({len(collected)} items):")
            for item in collected:
                print(f"   [{item.source}] {item.content} (score: {item.score:.2f})")
        
        # Show integrated context
        integrated = result.get("integrated_context")
        if integrated:
            print(f"\n🔗 Integrated Context:")
            if len(integrated) > 200:
                print(f"   {integrated[:200]}...")
            else:
                print(f"   {integrated}")
        
        # Show response
        response = result.response
        print(f"\n💬 Response:")
        print(f"   {response}")
        
        # Show metadata
        print(f"\n📊 Metadata:")
        history = result.get_history()
        for record in history:
            step_name = record['step']
            duration = record['data'].get('duration', 0)
            print(f"   - {step_name}: {duration*1000:.2f}ms")
        
        total_duration = result.get_metadata("pipeline_duration", 0)
        print(f"   Total: {total_duration*1000:.2f}ms")
    
    print(f"\n{'='*60}")
    print("Example completed!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
