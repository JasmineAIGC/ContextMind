"""
ContextMind Plugin Registry - Centralized plugin discovery and management

This module provides a unified registry for all ContextMind plugins, making it easy
to discover, swap, and configure different algorithm implementations.

Example:
    ```python
    from contextmind import registry
    
    # List available extractors
    print(registry.list_extractors())  # ['rule_based', 'llm_entity', 'importance']
    
    # Get an extractor plugin
    extractor = registry.get_extractor('rule_based')
    
    # Swap extractors at runtime
    engine.set_extractor(registry.get_extractor('llm_entity'))
    ```
"""

from typing import Dict, Type, Optional, Any, Callable
from .models import get_logger

logger = get_logger(__name__)


class PluginRegistry:
    """
    Central registry for all ContextMind plugins
    
    Provides discovery, registration, and instantiation of plugins.
    Makes ContextMind truly modular and extensible.
    """
    
    def __init__(self):
        self._plugins: Dict[str, Dict[str, Type]] = {
            'extractors': {},
            'retrievers': {},
            'updaters': {},
            'compressors': {},
            'reorderers': {},
            'preprocessors': {},
            'postprocessors': {},
            'summarizers': {},
            'kvcache_managers': {},
        }
        self._initialized = False
    
    def _lazy_init(self):
        """Lazy initialization of default plugins"""
        if self._initialized:
            return
        
        try:
            # Import and register extractors
            from .strategies.memory.extractors import (
                RuleBasedExtractor,
                LLMEntityExtractor,
                ImportancePredictorExtractor,
            )
            self.register('extractors', 'rule_based', RuleBasedExtractor)
            self.register('extractors', 'llm_entity', LLMEntityExtractor)
            self.register('extractors', 'importance', ImportancePredictorExtractor)
            
            # Import and register retrievers
            from .strategies.memory.retrievers import (
                SemanticSearchRetriever,
                HybridRetriever,
                LocatorRetriever,
            )
            self.register('retrievers', 'semantic', SemanticSearchRetriever)
            self.register('retrievers', 'hybrid', HybridRetriever)
            self.register('retrievers', 'locator', LocatorRetriever)
            
            # Import and register updaters
            from .strategies.memory.updaters import (
                SimpleUpdater,
                ConflictResolverUpdater,
                AdaptiveEvictionUpdater,
            )
            self.register('updaters', 'simple', SimpleUpdater)
            self.register('updaters', 'conflict_resolver', ConflictResolverUpdater)
            self.register('updaters', 'adaptive', AdaptiveEvictionUpdater)
            
            # Import and register other pipeline components
            from .pipeline.compressor import ContextCompressor
            from .pipeline.reorderer import ContextReorderer
            from .pipeline.preprocessor import InputPreprocessor
            from .pipeline.postprocessor import PostProcessor, RuleBasedPostProcessor
            from .pipeline.summarizer import ConversationSummarizer, RuleBasedSummarizer
            from .pipeline.kvcache import KVCacheManager, SlidingWindowKVCache
            
            self.register('compressors', 'default', ContextCompressor)
            self.register('reorderers', 'default', ContextReorderer)
            self.register('preprocessors', 'default', InputPreprocessor)
            self.register('postprocessors', 'rule_based', RuleBasedPostProcessor)
            self.register('summarizers', 'rule_based', RuleBasedSummarizer)
            self.register('kvcache_managers', 'sliding_window', SlidingWindowKVCache)
            
            self._initialized = True
            logger.info("[PluginRegistry] ✓ Initialized with default plugins")
            
        except Exception as e:
            logger.error(f"[PluginRegistry] Failed to initialize plugins: {e}")
    
    def register(self, category: str, name: str, plugin_class: Type):
        """Register a plugin in a category"""
        if category not in self._plugins:
            self._plugins[category] = {}
        self._plugins[category][name] = plugin_class
        logger.debug(f"[PluginRegistry] Registered {category}::{name}")
    
    def get(self, category: str, name: str, **kwargs) -> Optional[Any]:
        """Get a plugin instance by category and name"""
        self._lazy_init()
        if category not in self._plugins or name not in self._plugins[category]:
            logger.warning(f"[PluginRegistry] Plugin '{category}::{name}' not found")
            return None
        try:
            return self._plugins[category][name](**kwargs)
        except Exception as e:
            logger.error(f"[PluginRegistry] Failed to instantiate {category}::{name}: {e}")
            return None
    
    def list_plugins(self, category: str) -> list:
        """List all plugins in a category"""
        self._lazy_init()
        return list(self._plugins.get(category, {}).keys())
    
    def get_all_plugins(self) -> Dict[str, list]:
        """Get all registered plugins by category"""
        self._lazy_init()
        return {cat: list(plugins.keys()) for cat, plugins in self._plugins.items()}
    
    # Convenience methods for each category
    def get_extractor(self, name: str = 'rule_based', **kwargs):
        """Get an extractor plugin (default: rule_based)"""
        return self.get('extractors', name, **kwargs)
    
    def list_extractors(self):
        """List all registered extractors"""
        return self.list_plugins('extractors')
    
    def get_retriever(self, name: str = 'semantic', **kwargs):
        """Get a retriever plugin (default: semantic)"""
        return self.get('retrievers', name, **kwargs)
    
    def list_retrievers(self):
        """List all registered retrievers"""
        return self.list_plugins('retrievers')
    
    def get_updater(self, name: str = 'simple', **kwargs):
        """Get an updater plugin (default: simple)"""
        return self.get('updaters', name, **kwargs)
    
    def list_updaters(self):
        """List all registered updaters"""
        return self.list_plugins('updaters')


# Global registry instance
registry = PluginRegistry()

__all__ = ['PluginRegistry', 'registry']
