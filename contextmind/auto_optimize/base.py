"""
Base classes and protocols for the auto-optimization module.

This module defines the core data structures and interfaces used throughout
the evolutionary algorithm implementation.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol
from uuid import uuid4


@dataclass
class FitnessScore:
    """
    Represents the fitness score of a candidate solution.
    
    Attributes:
        value: Overall fitness value (higher is better)
        objectives: Individual objective scores for multi-objective optimization
        timestamp: When this fitness was evaluated
    """
    value: float
    objectives: Dict[str, float] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    
    def __lt__(self, other: "FitnessScore") -> bool:
        """Compare fitness scores (for sorting)."""
        return self.value < other.value
    
    def __le__(self, other: "FitnessScore") -> bool:
        return self.value <= other.value
    
    def __gt__(self, other: "FitnessScore") -> bool:
        return self.value > other.value
    
    def __ge__(self, other: "FitnessScore") -> bool:
        return self.value >= other.value


@dataclass
class Candidate:
    """
    Represents a candidate solution in the evolutionary algorithm.
    
    Attributes:
        id: Unique identifier
        genome: The genetic representation (parameters/configuration)
        fitness: Fitness score (None if not evaluated)
        generation: Which generation this candidate belongs to
        metadata: Additional information about the candidate
    """
    genome: Dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid4()))
    fitness: Optional[FitnessScore] = None
    generation: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def clone(self) -> "Candidate":
        """Create a copy of this candidate with a new ID."""
        return Candidate(
            genome=self.genome.copy(),
            fitness=self.fitness,
            generation=self.generation,
            metadata=self.metadata.copy(),
        )


@dataclass
class EvolutionConfig:
    """
    Configuration for the evolutionary algorithm.
    
    Attributes:
        population_size: Number of candidates in the population
        num_generations: Number of generations to evolve
        mutation_rate: Probability of mutation (0.0 to 1.0)
        crossover_rate: Probability of crossover (0.0 to 1.0)
        elite_size: Number of top candidates to preserve each generation
        tournament_size: Size of tournament for tournament selection
        convergence_threshold: Stop if improvement is below this threshold
        max_stagnant_generations: Stop if no improvement for this many generations
    """
    population_size: int = 20
    num_generations: int = 50
    mutation_rate: float = 0.1
    crossover_rate: float = 0.7
    elite_size: int = 2
    tournament_size: int = 3
    convergence_threshold: float = 1e-6
    max_stagnant_generations: int = 10


class Evaluator(Protocol):
    """
    Protocol for fitness evaluators.
    
    Evaluators determine how good a candidate solution is.
    """
    
    async def evaluate(self, candidate: Candidate) -> FitnessScore:
        """
        Evaluate a candidate and return its fitness score.
        
        Args:
            candidate: The candidate to evaluate
            
        Returns:
            FitnessScore object
        """
        ...


class MutationOperator(Protocol):
    """
    Protocol for mutation operators.
    
    Mutation operators introduce variation into the population.
    """
    
    def mutate(self, candidate: Candidate) -> Candidate:
        """
        Apply mutation to a candidate.
        
        Args:
            candidate: The candidate to mutate
            
        Returns:
            A new mutated candidate
        """
        ...


class SelectionStrategy(Protocol):
    """
    Protocol for selection strategies.
    
    Selection strategies choose which candidates reproduce.
    """
    
    def select(
        self,
        population: List[Candidate],
        num_parents: int,
    ) -> List[Candidate]:
        """
        Select parents from the population.
        
        Args:
            population: List of candidates to select from
            num_parents: Number of parents to select
            
        Returns:
            List of selected candidates
        """
        ...
