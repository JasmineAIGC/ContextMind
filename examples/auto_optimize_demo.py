"""
Example: Auto-Optimization Demo

This script demonstrates how to use the auto-optimization module to
evolve and optimize strategies.
"""

import asyncio
import random
from typing import Dict, Any

from contextmind.auto_optimize import (
    Candidate,
    FitnessScore,
    EvolutionConfig,
    StrategyEvolver,
    BaseEvaluator,
)


class SimpleEvaluator(BaseEvaluator):
    """
    Example evaluator that optimizes a simple mathematical function.
    
    Goal: Find x, y such that f(x, y) = -(x-5)^2 - (y-3)^2 is maximized
    Optimal solution: x=5, y=3, f(5,3)=0
    """
    
    async def evaluate(self, candidate: Candidate) -> FitnessScore:
        """Evaluate candidate fitness."""
        x = candidate.genome.get("x", 0.0)
        y = candidate.genome.get("y", 0.0)
        
        # Objective function (we want to maximize this)
        value = -((x - 5.0) ** 2) - ((y - 3.0) ** 2)
        
        return FitnessScore(
            value=value,
            objectives={
                "x_distance": -abs(x - 5.0),
                "y_distance": -abs(y - 3.0),
            }
        )


def create_random_genome() -> Dict[str, Any]:
    """Create a random initial genome."""
    return {
        "x": random.uniform(-10, 10),
        "y": random.uniform(-10, 10),
    }


async def main():
    """Run the optimization example."""
    print("=" * 60)
    print("Auto-Optimization Demo: Finding Optimal (x, y)")
    print("=" * 60)
    print()
    print("Goal: Maximize f(x, y) = -(x-5)^2 - (y-3)^2")
    print("Expected optimal solution: x=5, y=3, f(5,3)=0")
    print()
    
    # Configure evolution
    config = EvolutionConfig(
        population_size=20,
        num_generations=50,
        mutation_rate=0.2,
        crossover_rate=0.7,
        elite_size=2,
        tournament_size=3,
        convergence_threshold=1e-6,
        max_stagnant_generations=10,
    )
    
    # Create evaluator
    evaluator = SimpleEvaluator()
    
    # Create evolver
    evolver = StrategyEvolver(
        config=config,
        evaluator=evaluator,
        initializer=create_random_genome,
    )
    
    # Run evolution
    print("Starting evolution...")
    print()
    
    best_candidate = await evolver.evolve()
    
    # Print results
    print()
    print("=" * 60)
    print("Evolution Complete!")
    print("=" * 60)
    print()
    print(f"Best fitness: {best_candidate.fitness.value:.6f}")
    print(f"Best genome: {best_candidate.genome}")
    print(f"Objectives: {best_candidate.fitness.objectives}")
    print(f"Generation: {best_candidate.generation}")
    print()
    
    # Print evolution history summary
    history = evolver.get_history()
    if history:
        print("Evolution Progress:")
        print("-" * 60)
        for i in range(0, len(history), max(1, len(history) // 10)):
            gen_info = history[i]
            print(
                f"Gen {gen_info['generation']:3d}: "
                f"Best={gen_info['best_fitness']:8.4f}, "
                f"Avg={gen_info['stats']['avg']:8.4f}, "
                f"Std={gen_info['stats']['std']:8.4f}"
            )
        
        # Final generation
        if len(history) > 1:
            gen_info = history[-1]
            print(
                f"Gen {gen_info['generation']:3d}: "
                f"Best={gen_info['best_fitness']:8.4f}, "
                f"Avg={gen_info['stats']['avg']:8.4f}, "
                f"Std={gen_info['stats']['std']:8.4f}"
            )
    
    print()
    print("Cache statistics:")
    print(f"  Cached evaluations: {evolver.evaluator.get_cache_size()}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
