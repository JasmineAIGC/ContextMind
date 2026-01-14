"""
Registry system for steps and strategies.

This module provides a centralized registry for managing pluggable components.
"""

from __future__ import annotations

from typing import Any, Dict, Type, Optional, Callable
from .exceptions import RegistryError


class Registry:
    """
    Generic registry for managing components.
    
    This class provides a thread-safe registry for storing and retrieving
    components by name.
    """
    
    def __init__(self, name: str = "Registry"):
        """
        Initialize registry.
        
        Args:
            name: Name of this registry
        """
        self.name = name
        self._items: Dict[str, Any] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
    
    def register(
        self, 
        name: str, 
        item: Any,
        *,
        metadata: Optional[Dict[str, Any]] = None,
        override: bool = False
    ) -> None:
        """
        Register an item.
        
        Args:
            name: Name to register under
            item: The item to register
            metadata: Optional metadata about the item
            override: Whether to override existing registration
            
        Raises:
            RegistryError: If name already registered and override=False
        """
        if name in self._items and not override:
            raise RegistryError(
                f"'{name}' is already registered in {self.name}. "
                f"Use override=True to replace."
            )
        
        self._items[name] = item
        if metadata:
            self._metadata[name] = metadata
    
    def get(self, name: str) -> Any:
        """
        Get a registered item.
        
        Args:
            name: Name of the item
            
        Returns:
            The registered item
            
        Raises:
            RegistryError: If name not found
        """
        if name not in self._items:
            raise RegistryError(
                f"'{name}' not found in {self.name}. "
                f"Available: {list(self._items.keys())}"
            )
        return self._items[name]
    
    def has(self, name: str) -> bool:
        """
        Check if name is registered.
        
        Args:
            name: Name to check
            
        Returns:
            True if registered, False otherwise
        """
        return name in self._items
    
    def list(self) -> list[str]:
        """
        List all registered names.
        
        Returns:
            List of registered names
        """
        return list(self._items.keys())
    
    def get_metadata(self, name: str) -> Dict[str, Any]:
        """
        Get metadata for a registered item.
        
        Args:
            name: Name of the item
            
        Returns:
            Metadata dictionary
        """
        return self._metadata.get(name, {})
    
    def unregister(self, name: str) -> None:
        """
        Unregister an item.
        
        Args:
            name: Name to unregister
        """
        self._items.pop(name, None)
        self._metadata.pop(name, None)
    
    def clear(self) -> None:
        """Clear all registrations."""
        self._items.clear()
        self._metadata.clear()


class StepRegistry(Registry):
    """Registry specifically for pipeline steps."""
    
    def __init__(self):
        super().__init__("StepRegistry")
    
    def register_step(
        self,
        name: str,
        step_class: Type,
        *,
        description: Optional[str] = None,
        override: bool = False
    ) -> None:
        """
        Register a step class.
        
        Args:
            name: Step name
            step_class: Step class to register
            description: Optional description
            override: Whether to override existing
        """
        metadata = {}
        if description:
            metadata["description"] = description
        if hasattr(step_class, "__doc__") and step_class.__doc__:
            metadata["doc"] = step_class.__doc__.strip()
        
        self.register(name, step_class, metadata=metadata, override=override)
    
    def create_step(self, name: str, **config) -> Any:
        """
        Create a step instance.
        
        Args:
            name: Name of the step
            **config: Configuration for the step
            
        Returns:
            Step instance
        """
        step_class = self.get(name)
        return step_class(**config)


class StrategyRegistry(Registry):
    """Registry for strategies within specific categories."""
    
    def __init__(self):
        super().__init__("StrategyRegistry")
        self._categories: Dict[str, Registry] = {}
    
    def register_strategy(
        self,
        category: str,
        name: str,
        strategy_class: Type,
        *,
        description: Optional[str] = None,
        override: bool = False
    ) -> None:
        """
        Register a strategy in a specific category.
        
        Args:
            category: Strategy category (e.g., 'retrieval', 'prompt')
            name: Strategy name
            strategy_class: Strategy class
            description: Optional description
            override: Whether to override existing
        """
        if category not in self._categories:
            self._categories[category] = Registry(f"{category}_strategies")
        
        metadata = {}
        if description:
            metadata["description"] = description
        if hasattr(strategy_class, "__doc__") and strategy_class.__doc__:
            metadata["doc"] = strategy_class.__doc__.strip()
        
        self._categories[category].register(
            name, strategy_class, metadata=metadata, override=override
        )
    
    def get_strategy(self, category: str, name: str) -> Type:
        """
        Get a strategy class.
        
        Args:
            category: Strategy category
            name: Strategy name
            
        Returns:
            Strategy class
        """
        if category not in self._categories:
            raise RegistryError(f"Category '{category}' not found")
        return self._categories[category].get(name)
    
    def create_strategy(self, category: str, name: str, **config) -> Any:
        """
        Create a strategy instance.
        
        Args:
            category: Strategy category
            name: Strategy name
            **config: Configuration for the strategy
            
        Returns:
            Strategy instance
        """
        strategy_class = self.get_strategy(category, name)
        return strategy_class(**config)
    
    def list_categories(self) -> list[str]:
        """List all strategy categories."""
        return list(self._categories.keys())
    
    def list_strategies(self, category: str) -> list[str]:
        """
        List strategies in a category.
        
        Args:
            category: Category name
            
        Returns:
            List of strategy names
        """
        if category not in self._categories:
            return []
        return self._categories[category].list()


# Global registries
_step_registry = StepRegistry()
_strategy_registry = StrategyRegistry()


def get_step_registry() -> StepRegistry:
    """Get the global step registry."""
    return _step_registry


def get_strategy_registry() -> StrategyRegistry:
    """Get the global strategy registry."""
    return _strategy_registry


# Decorators for easy registration
def register_step(name: str, description: Optional[str] = None):
    """
    Decorator to register a step class.
    
    Usage:
        @register_step("my_step", "Does something")
        class MyStep(BaseStep):
            pass
    """
    def decorator(cls):
        _step_registry.register_step(name, cls, description=description)
        return cls
    return decorator


def register_strategy(category: str, name: str, description: Optional[str] = None):
    """
    Decorator to register a strategy class.
    
    Usage:
        @register_strategy("retrieval", "vector", "Vector-based retrieval")
        class VectorRetrieval(BaseStrategy):
            pass
    """
    def decorator(cls):
        _strategy_registry.register_strategy(category, name, cls, description=description)
        return cls
    return decorator
