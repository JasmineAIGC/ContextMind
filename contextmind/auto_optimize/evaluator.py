"""
Evaluator framework for fitness evaluation.
"""

from abc import ABC, abstractmethod
from typing import Dict, List

from contextmind.auto_optimize.base import Candidate, FitnessScore


class BaseEvaluator(ABC):
    """
    Abstract base class for evaluators.
    
    Subclasses must implement the evaluate method.
    """
    
    @abstractmethod
    async def evaluate(self, candidate: Candidate) -> FitnessScore:
        """
        Evaluate a candidate and return its fitness.
        
        Args:
            candidate: Candidate to evaluate
            
        Returns:
            FitnessScore object
        """
        pass


class CachedEvaluator(BaseEvaluator):
    """
    Evaluator wrapper that caches results to avoid re-evaluation.
    
    Useful when evaluation is expensive and candidates may be re-evaluated.
    """
    
    def __init__(self, base_evaluator: BaseEvaluator):
        """
        Initialize cached evaluator.
        
        Args:
            base_evaluator: The underlying evaluator to wrap
        """
        self.base_evaluator = base_evaluator
        self.cache: Dict[str, FitnessScore] = {}
    
    def _get_cache_key(self, candidate: Candidate) -> str:
        """
        Generate a cache key for a candidate.
        
        Uses sorted genome items to ensure consistent keys.
        """
        genome_str = str(sorted(candidate.genome.items()))
        return genome_str
    
    async def evaluate(self, candidate: Candidate) -> FitnessScore:
        """
        Evaluate with caching.
        
        Args:
            candidate: Candidate to evaluate
            
        Returns:
            FitnessScore (from cache if available)
        """
        cache_key = self._get_cache_key(candidate)
        
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        # Evaluate and cache
        fitness = await self.base_evaluator.evaluate(candidate)
        self.cache[cache_key] = fitness
        
        return fitness
    
    def clear_cache(self) -> None:
        """Clear the evaluation cache."""
        self.cache.clear()
    
    def get_cache_size(self) -> int:
        """Return the number of cached evaluations."""
        return len(self.cache)


class CompositeEvaluator(BaseEvaluator):
    """
    Combines multiple evaluators for multi-objective optimization.
    
    The overall fitness is a weighted sum of individual objectives.
    """
    
    def __init__(
        self,
        evaluators: Dict[str, BaseEvaluator],
        weights: Dict[str, float] = None
    ):
        """
        Initialize composite evaluator.
        
        Args:
            evaluators: Dict of objective_name -> evaluator
            weights: Dict of objective_name -> weight (default: equal weights)
        """
        self.evaluators = evaluators
        
        if weights is None:
            # Equal weights
            n = len(evaluators)
            self.weights = {name: 1.0 / n for name in evaluators.keys()}
        else:
            self.weights = weights
    
    async def evaluate(self, candidate: Candidate) -> FitnessScore:
        """
        Evaluate using all sub-evaluators.
        
        Args:
            candidate: Candidate to evaluate
            
        Returns:
            FitnessScore with combined value and individual objectives
        """
        objectives: Dict[str, float] = {}
        
        # Evaluate each objective
        for name, evaluator in self.evaluators.items():
            fitness = await evaluator.evaluate(candidate)
            objectives[name] = fitness.value
        
        # Compute weighted sum
        total_value = sum(
            objectives[name] * self.weights[name]
            for name in objectives.keys()
        )
        
        return FitnessScore(
            value=total_value,
            objectives=objectives
        )
