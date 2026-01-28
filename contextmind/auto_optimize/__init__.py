"""
Auto-Optimization Module for ContextMind

This module provides evolutionary algorithms and self-optimization capabilities
for automatically tuning strategies, prompts, and configurations.

Key Components:
- Population: Manages candidate solutions
- Evolver: Main evolution engine with selection, mutation, and crossover
- Evaluator: Framework for fitness evaluation
- Operators: Mutation and crossover operators
- Selection: Selection strategies (tournament, roulette, elitist)

Usage:
    from contextmind.auto_optimize import StrategyEvolver, EvolutionConfig
    
    config = EvolutionConfig(population_size=20, num_generations=50)
    evolver = StrategyEvolver(config=config, evaluator=my_evaluator)
    best_solution = await evolver.evolve()
"""

from contextmind.auto_optimize.base import (
    Candidate,
    FitnessScore,
    EvolutionConfig,
    Evaluator,
    MutationOperator,
    SelectionStrategy,
)
from contextmind.auto_optimize.population import Population
from contextmind.auto_optimize.operators import (
    RandomMutation,
    GaussianMutation,
    UniformCrossover,
    SinglePointCrossover,
)
from contextmind.auto_optimize.selection import (
    TournamentSelection,
    RouletteSelection,
    ElitistSelection,
    RankSelection,
)
from contextmind.auto_optimize.evaluator import (
    BaseEvaluator,
    CachedEvaluator,
    CompositeEvaluator,
)
from contextmind.auto_optimize.evolver import StrategyEvolver

__all__ = [
    # Base types
    "Candidate",
    "FitnessScore",
    "EvolutionConfig",
    "Evaluator",
    "MutationOperator",
    "SelectionStrategy",
    # Population
    "Population",
    # Operators
    "RandomMutation",
    "GaussianMutation",
    "UniformCrossover",
    "SinglePointCrossover",
    # Selection
    "TournamentSelection",
    "RouletteSelection",
    "ElitistSelection",
    "RankSelection",
    # Evaluator
    "BaseEvaluator",
    "CachedEvaluator",
    "CompositeEvaluator",
    # Evolver
    "StrategyEvolver",
]
