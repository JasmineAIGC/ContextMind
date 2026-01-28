"""
Population management for evolutionary algorithms.
"""

import random
from typing import List, Optional

from contextmind.auto_optimize.base import Candidate, FitnessScore


class Population:
    """
    Manages a population of candidate solutions.
    
    Provides methods for adding candidates, retrieving best solutions,
    and sampling for diversity.
    """
    
    def __init__(self, candidates: Optional[List[Candidate]] = None):
        """
        Initialize population.
        
        Args:
            candidates: Initial list of candidates (optional)
        """
        self.candidates: List[Candidate] = candidates or []
    
    def add_candidate(self, candidate: Candidate) -> None:
        """Add a candidate to the population."""
        self.candidates.append(candidate)
    
    def add_candidates(self, candidates: List[Candidate]) -> None:
        """Add multiple candidates to the population."""
        self.candidates.extend(candidates)
    
    def get_best(self, n: int = 1) -> List[Candidate]:
        """
        Get the top n candidates by fitness.
        
        Args:
            n: Number of top candidates to return
            
        Returns:
            List of best candidates (sorted by fitness, descending)
        """
        evaluated = [c for c in self.candidates if c.fitness is not None]
        if not evaluated:
            return []
        
        sorted_candidates = sorted(
            evaluated,
            key=lambda c: c.fitness.value,
            reverse=True
        )
        return sorted_candidates[:n]
    
    def get_worst(self, n: int = 1) -> List[Candidate]:
        """
        Get the bottom n candidates by fitness.
        
        Args:
            n: Number of worst candidates to return
            
        Returns:
            List of worst candidates (sorted by fitness, ascending)
        """
        evaluated = [c for c in self.candidates if c.fitness is not None]
        if not evaluated:
            return []
        
        sorted_candidates = sorted(
            evaluated,
            key=lambda c: c.fitness.value
        )
        return sorted_candidates[:n]
    
    def get_diverse_sample(self, n: int, avoid_duplicates: bool = True) -> List[Candidate]:
        """
        Sample n candidates with diversity.
        
        Args:
            n: Number of candidates to sample
            avoid_duplicates: If True, sample without replacement
            
        Returns:
            List of sampled candidates
        """
        if avoid_duplicates:
            n = min(n, len(self.candidates))
            return random.sample(self.candidates, n)
        else:
            return random.choices(self.candidates, k=n)
    
    def update_fitness(self, candidate_id: str, fitness: FitnessScore) -> None:
        """
        Update the fitness of a specific candidate.
        
        Args:
            candidate_id: ID of the candidate to update
            fitness: New fitness score
        """
        for candidate in self.candidates:
            if candidate.id == candidate_id:
                candidate.fitness = fitness
                break
    
    def size(self) -> int:
        """Return the number of candidates in the population."""
        return len(self.candidates)
    
    def clear(self) -> None:
        """Remove all candidates from the population."""
        self.candidates.clear()
    
    def get_average_fitness(self) -> float:
        """
        Calculate average fitness of evaluated candidates.
        
        Returns:
            Average fitness value, or 0.0 if no evaluated candidates
        """
        evaluated = [c for c in self.candidates if c.fitness is not None]
        if not evaluated:
            return 0.0
        
        total = sum(c.fitness.value for c in evaluated)
        return total / len(evaluated)
    
    def get_fitness_stats(self) -> dict:
        """
        Get statistics about the population's fitness.
        
        Returns:
            Dict with min, max, avg, and std of fitness values
        """
        evaluated = [c for c in self.candidates if c.fitness is not None]
        if not evaluated:
            return {
                "min": 0.0,
                "max": 0.0,
                "avg": 0.0,
                "std": 0.0,
                "count": 0
            }
        
        fitness_values = [c.fitness.value for c in evaluated]
        avg = sum(fitness_values) / len(fitness_values)
        variance = sum((x - avg) ** 2 for x in fitness_values) / len(fitness_values)
        std = variance ** 0.5
        
        return {
            "min": min(fitness_values),
            "max": max(fitness_values),
            "avg": avg,
            "std": std,
            "count": len(evaluated)
        }
