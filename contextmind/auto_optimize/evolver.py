"""
Main evolutionary algorithm engine.
"""

import logging
import random
from typing import Any, Callable, Dict, List, Optional

from contextmind.auto_optimize.base import (
    Candidate,
    Evaluator,
    EvolutionConfig,
    FitnessScore,
)
from contextmind.auto_optimize.evaluator import CachedEvaluator
from contextmind.auto_optimize.operators import (
    GaussianMutation,
    UniformCrossover,
)
from contextmind.auto_optimize.population import Population
from contextmind.auto_optimize.selection import TournamentSelection

logger = logging.getLogger(__name__)


class StrategyEvolver:
    """
    Main evolution engine that orchestrates the evolutionary algorithm.
    
    Uses selection, mutation, and crossover to evolve a population of
    candidate solutions toward better fitness.
    """
    
    def __init__(
        self,
        config: EvolutionConfig,
        evaluator: Evaluator,
        initializer: Optional[Callable[[], Dict[str, Any]]] = None,
        mutation_operator: Optional[Any] = None,
        crossover_operator: Optional[Any] = None,
        selection_strategy: Optional[Any] = None,
    ):
        """
        Initialize the evolution engine.
        
        Args:
            config: Evolution configuration
            evaluator: Fitness evaluator
            initializer: Function to create initial genomes (optional)
            mutation_operator: Mutation operator (default: GaussianMutation)
            crossover_operator: Crossover operator (default: UniformCrossover)
            selection_strategy: Selection strategy (default: TournamentSelection)
        """
        self.config = config
        self.evaluator = CachedEvaluator(evaluator)
        self.initializer = initializer
        
        # Use default operators if not provided
        self.mutation_operator = mutation_operator or GaussianMutation(sigma=config.mutation_rate)
        self.crossover_operator = crossover_operator or UniformCrossover(crossover_rate=config.crossover_rate)
        self.selection_strategy = selection_strategy or TournamentSelection(tournament_size=config.tournament_size)
        
        # Evolution history
        self.history: List[Dict[str, Any]] = []
        self.best_candidate: Optional[Candidate] = None
    
    def initialize_population(self) -> Population:
        """
        Create initial population.
        
        Returns:
            Population with random candidates
        """
        population = Population()
        
        for _ in range(self.config.population_size):
            if self.initializer:
                genome = self.initializer()
            else:
                # Default: empty genome
                genome = {}
            
            candidate = Candidate(genome=genome, generation=0)
            population.add_candidate(candidate)
        
        logger.info(f"Initialized population with {population.size()} candidates")
        return population
    
    async def evaluate_generation(self, population: Population) -> None:
        """
        Evaluate all unevaluated candidates in the population.
        
        Args:
            population: Population to evaluate
        """
        unevaluated = [c for c in population.candidates if c.fitness is None]
        
        logger.info(f"Evaluating {len(unevaluated)} candidates")
        
        for candidate in unevaluated:
            fitness = await self.evaluator.evaluate(candidate)
            candidate.fitness = fitness
    
    def select_parents(self, population: Population, num_parents: int) -> List[Candidate]:
        """
        Select parents for reproduction.
        
        Args:
            population: Population to select from
            num_parents: Number of parents to select
            
        Returns:
            List of selected parents
        """
        return self.selection_strategy.select(population.candidates, num_parents)
    
    def create_offspring(self, parents: List[Candidate]) -> List[Candidate]:
        """
        Create offspring from parents using crossover and mutation.
        
        Args:
            parents: Parent candidates
            
        Returns:
            List of offspring candidates
        """
        offspring = []
        
        # Need pairs of parents for crossover
        num_offspring = self.config.population_size - self.config.elite_size
        
        for _ in range(num_offspring):
            # Select two parents randomly
            parent1, parent2 = random.sample(parents, 2)
            
            # Crossover
            if random.random() < self.config.crossover_rate:
                child = self.crossover_operator.crossover(parent1, parent2)
            else:
                # No crossover, just clone
                child = parent1.clone()
            
            # Mutation
            if random.random() < self.config.mutation_rate:
                child = self.mutation_operator.mutate(child)
            
            offspring.append(child)
        
        return offspring
    
    def update_population(
        self,
        population: Population,
        offspring: List[Candidate]
    ) -> Population:
        """
        Update population with offspring, keeping elites.
        
        Args:
            population: Current population
            offspring: New offspring candidates
            
        Returns:
            New population for next generation
        """
        # Get elites (best candidates)
        elites = population.get_best(self.config.elite_size)
        
        # Create new population
        new_population = Population()
        new_population.add_candidates(elites)
        new_population.add_candidates(offspring)
        
        return new_population
    
    async def evolve(self) -> Candidate:
        """
        Run the evolutionary algorithm.
        
        Returns:
            Best candidate found
        """
        logger.info("Starting evolution")
        logger.info(f"Config: {self.config}")
        
        # Initialize
        population = self.initialize_population()
        await self.evaluate_generation(population)
        
        best_fitness_history = []
        stagnant_generations = 0
        prev_best_fitness = float('-inf')
        
        # Evolution loop
        for generation in range(self.config.num_generations):
            # Track generation stats
            stats = population.get_fitness_stats()
            best_candidates = population.get_best(1)
            
            if best_candidates:
                current_best = best_candidates[0]
                current_best_fitness = current_best.fitness.value
                best_fitness_history.append(current_best_fitness)
                
                # Update global best
                if self.best_candidate is None or current_best_fitness > self.best_candidate.fitness.value:
                    self.best_candidate = current_best
                
                logger.info(
                    f"Generation {generation}: "
                    f"Best={current_best_fitness:.4f}, "
                    f"Avg={stats['avg']:.4f}, "
                    f"Std={stats['std']:.4f}"
                )
                
                # Check for convergence
                improvement = current_best_fitness - prev_best_fitness
                if improvement < self.config.convergence_threshold:
                    stagnant_generations += 1
                else:
                    stagnant_generations = 0
                
                prev_best_fitness = current_best_fitness
                
                # Early stopping if stagnant
                if stagnant_generations >= self.config.max_stagnant_generations:
                    logger.info(f"Converged after {generation} generations (stagnant for {stagnant_generations})")
                    break
            
            # Record history
            self.history.append({
                "generation": generation,
                "stats": stats,
                "best_fitness": best_fitness_history[-1] if best_fitness_history else 0.0,
            })
            
            # Selection
            num_parents = max(2, self.config.population_size // 2)
            parents = self.select_parents(population, num_parents)
            
            # Create offspring
            offspring = self.create_offspring(parents)
            
            # Evaluate offspring
            offspring_population = Population(offspring)
            await self.evaluate_generation(offspring_population)
            
            # Update population
            population = self.update_population(population, offspring)
        
        logger.info("Evolution complete")
        logger.info(f"Best fitness: {self.best_candidate.fitness.value:.4f}")
        logger.info(f"Cache size: {self.evaluator.get_cache_size()}")
        
        return self.best_candidate
    
    def get_history(self) -> List[Dict[str, Any]]:
        """
        Get evolution history.
        
        Returns:
            List of generation statistics
        """
        return self.history
