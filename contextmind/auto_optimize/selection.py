"""
Selection strategies for evolutionary algorithms.
"""

import random
from typing import List

from contextmind.auto_optimize.base import Candidate


class TournamentSelection:
    """
    Tournament selection: randomly sample k candidates and pick the best.
    """
    
    def __init__(self, tournament_size: int = 3):
        """
        Initialize tournament selection.
        
        Args:
            tournament_size: Number of candidates in each tournament
        """
        self.tournament_size = tournament_size
    
    def select(self, population: List[Candidate], num_parents: int) -> List[Candidate]:
        """
        Select parents using tournament selection.
        
        Args:
            population: Population to select from
            num_parents: Number of parents to select
            
        Returns:
            List of selected parents
        """
        # Filter to evaluated candidates only
        evaluated = [c for c in population if c.fitness is not None]
        if not evaluated:
            return []
        
        parents = []
        for _ in range(num_parents):
            # Run tournament
            tournament_size = min(self.tournament_size, len(evaluated))
            tournament = random.sample(evaluated, tournament_size)
            winner = max(tournament, key=lambda c: c.fitness.value)
            parents.append(winner)
        
        return parents


class RouletteSelection:
    """
    Roulette wheel selection: probability proportional to fitness.
    """
    
    def select(self, population: List[Candidate], num_parents: int) -> List[Candidate]:
        """
        Select parents using roulette wheel selection.
        
        Args:
            population: Population to select from
            num_parents: Number of parents to select
            
        Returns:
            List of selected parents
        """
        # Filter to evaluated candidates
        evaluated = [c for c in population if c.fitness is not None]
        if not evaluated:
            return []
        
        # Get fitness values and handle negative fitness
        fitness_values = [c.fitness.value for c in evaluated]
        min_fitness = min(fitness_values)
        
        # Shift to make all fitness values positive
        if min_fitness < 0:
            fitness_values = [f - min_fitness + 1 for f in fitness_values]
        
        total_fitness = sum(fitness_values)
        
        if total_fitness == 0:
            # All fitness equal, use uniform selection
            return random.choices(evaluated, k=num_parents)
        
        # Calculate selection probabilities
        probabilities = [f / total_fitness for f in fitness_values]
        
        # Select parents
        parents = random.choices(evaluated, weights=probabilities, k=num_parents)
        return parents


class ElitistSelection:
    """
    Elitist selection: always select the top candidates.
    """
    
    def select(self, population: List[Candidate], num_parents: int) -> List[Candidate]:
        """
        Select the top candidates by fitness.
        
        Args:
            population: Population to select from
            num_parents: Number of parents to select
            
        Returns:
            List of top candidates
        """
        # Filter to evaluated candidates
        evaluated = [c for c in population if c.fitness is not None]
        if not evaluated:
            return []
        
        # Sort by fitness (descending)
        sorted_candidates = sorted(
            evaluated,
            key=lambda c: c.fitness.value,
            reverse=True
        )
        
        # Return top n
        return sorted_candidates[:num_parents]


class RankSelection:
    """
    Rank-based selection: probability based on rank rather than raw fitness.
    This is more robust to fitness scaling issues.
    """
    
    def select(self, population: List[Candidate], num_parents: int) -> List[Candidate]:
        """
        Select parents using rank-based selection.
        
        Args:
            population: Population to select from
            num_parents: Number of parents to select
            
        Returns:
            List of selected parents
        """
        # Filter to evaluated candidates
        evaluated = [c for c in population if c.fitness is not None]
        if not evaluated:
            return []
        
        # Sort by fitness (ascending, so worst has rank 1)
        sorted_candidates = sorted(
            evaluated,
            key=lambda c: c.fitness.value
        )
        
        # Assign ranks (1 to n)
        n = len(sorted_candidates)
        ranks = list(range(1, n + 1))
        
        # Selection probability proportional to rank
        total_rank = sum(ranks)
        probabilities = [r / total_rank for r in ranks]
        
        # Select parents
        parents = random.choices(sorted_candidates, weights=probabilities, k=num_parents)
        return parents
