"""
Mutation and crossover operators for evolutionary algorithms.
"""

import random
from typing import Any, Dict, List

from contextmind.auto_optimize.base import Candidate


class RandomMutation:
    """
    Randomly perturbs numeric values or replaces categorical values.
    """
    
    def __init__(self, mutation_strength: float = 0.1):
        """
        Initialize mutation operator.
        
        Args:
            mutation_strength: How much to perturb values (0.0 to 1.0)
        """
        self.mutation_strength = mutation_strength
    
    def mutate(self, candidate: Candidate) -> Candidate:
        """
        Apply random mutation to a candidate.
        
        Args:
            candidate: Candidate to mutate
            
        Returns:
            New mutated candidate
        """
        mutated = candidate.clone()
        
        for key, value in mutated.genome.items():
            if random.random() < self.mutation_strength:
                mutated.genome[key] = self._mutate_value(value)
        
        return mutated
    
    def _mutate_value(self, value: Any) -> Any:
        """Mutate a single value based on its type."""
        if isinstance(value, (int, float)):
            # Add random perturbation
            perturbation = random.gauss(0, abs(value) * 0.1 + 0.1)
            new_value = value + perturbation
            return int(new_value) if isinstance(value, int) else new_value
        elif isinstance(value, bool):
            # Flip boolean
            return not value
        elif isinstance(value, str):
            # For strings, keep as is (specialized mutators needed)
            return value
        elif isinstance(value, list):
            # Mutate random element
            if value:
                idx = random.randint(0, len(value) - 1)
                value[idx] = self._mutate_value(value[idx])
            return value
        else:
            return value


class GaussianMutation:
    """
    Applies Gaussian perturbation to numeric values.
    Better for fine-tuning numeric parameters.
    """
    
    def __init__(self, sigma: float = 0.1):
        """
        Initialize Gaussian mutation.
        
        Args:
            sigma: Standard deviation of Gaussian noise
        """
        self.sigma = sigma
    
    def mutate(self, candidate: Candidate) -> Candidate:
        """Apply Gaussian mutation to numeric parameters."""
        mutated = candidate.clone()
        
        for key, value in mutated.genome.items():
            if isinstance(value, (int, float)):
                noise = random.gauss(0, self.sigma)
                new_value = value * (1 + noise)
                mutated.genome[key] = int(new_value) if isinstance(value, int) else new_value
        
        return mutated


class UniformCrossover:
    """
    Uniform crossover: each gene has 50% chance from either parent.
    """
    
    def __init__(self, crossover_rate: float = 0.5):
        """
        Initialize uniform crossover.
        
        Args:
            crossover_rate: Probability of taking gene from first parent
        """
        self.crossover_rate = crossover_rate
    
    def crossover(self, parent1: Candidate, parent2: Candidate) -> Candidate:
        """
        Perform uniform crossover between two parents.
        
        Args:
            parent1: First parent
            parent2: Second parent
            
        Returns:
            Offspring candidate
        """
        offspring_genome: Dict[str, Any] = {}
        
        # Get all keys from both parents
        all_keys = set(parent1.genome.keys()) | set(parent2.genome.keys())
        
        for key in all_keys:
            if random.random() < self.crossover_rate:
                # Take from parent1 if it has the key
                offspring_genome[key] = parent1.genome.get(key, parent2.genome.get(key))
            else:
                # Take from parent2 if it has the key
                offspring_genome[key] = parent2.genome.get(key, parent1.genome.get(key))
        
        return Candidate(
            genome=offspring_genome,
            generation=max(parent1.generation, parent2.generation) + 1
        )


class SinglePointCrossover:
    """
    Single-point crossover: split genomes at a random point and swap.
    """
    
    def crossover(self, parent1: Candidate, parent2: Candidate) -> Candidate:
        """
        Perform single-point crossover.
        
        Args:
            parent1: First parent
            parent2: Second parent
            
        Returns:
            Offspring candidate
        """
        keys1 = list(parent1.genome.keys())
        keys2 = list(parent2.genome.keys())
        
        # Use common keys for crossover
        common_keys = list(set(keys1) & set(keys2))
        
        if not common_keys:
            # If no common keys, return clone of parent1
            return parent1.clone()
        
        # Random crossover point
        crossover_point = random.randint(0, len(common_keys))
        
        offspring_genome: Dict[str, Any] = {}
        
        # First part from parent1, second part from parent2
        for i, key in enumerate(common_keys):
            if i < crossover_point:
                offspring_genome[key] = parent1.genome[key]
            else:
                offspring_genome[key] = parent2.genome[key]
        
        # Add any unique keys from both parents
        for key in keys1:
            if key not in offspring_genome:
                offspring_genome[key] = parent1.genome[key]
        
        for key in keys2:
            if key not in offspring_genome:
                offspring_genome[key] = parent2.genome[key]
        
        return Candidate(
            genome=offspring_genome,
            generation=max(parent1.generation, parent2.generation) + 1
        )
