"""
Example demonstrating the ContextMind framework.
"""

import asyncio
import sys
sys.path.insert(0, '/home/runner/work/ContextMind/ContextMind')

from contextmind.core import Context, PipelineBuilder
from contextmind.steps import PreprocessingStep, RetrievalStep, AugmentationStep, PostprocessingStep
from contextmind.strategies import KeywordRetrievalStrategy


async def main():
    """Run example pipeline."""
    print("=" * 60)
    print("ContextMind - Context Engineering Framework")
    print("=" * 60)
    
    # Create a pipeline using the builder
    pipeline = PipelineBuilder("context_engineering_pipeline") \
        .add_step("preprocessing", normalize=True, max_length=1000) \
        .add_custom_step(
            "retrieval",
            RetrievalStep(retrieval_strategy=KeywordRetrievalStrategy())
        ) \
        .add_step("augmentation", method="structured") \
        .add_custom_step(
            "postprocessing",
            PostprocessingStep()
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
        
        # Show retrieved context
        retrieved = result.get_context_data()
        if retrieved:
            print(f"\n📚 Retrieved Context ({len(retrieved)} items):")
            for item in retrieved:
                print(f"   [{item.source}] {item.content} (score: {item.score:.2f})")
        
        # Show augmented context
        augmented = result.get("augmented_context")
        if augmented:
            print(f"\n🔗 Augmented Context:")
            if len(augmented) > 200:
                print(f"   {augmented[:200]}...")
            else:
                print(f"   {augmented}")
        
        # Show output
        output = result.get("output")
        print(f"\n💬 Output:")
        print(f"   {output}")
        
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
