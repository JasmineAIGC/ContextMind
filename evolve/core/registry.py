"""
Evolve 插件注册中心 - 集中式插件发现和管理

本模块为所有 Evolve 插件提供统一的注册中心，便于发现、替换和配置不同的算法实现。

使用示例:
    ```python
    from evolve import registry
    
    # 列出可用的提取器
    print(registry.list_extractors())  # ['rule_based', 'llm_entity', 'importance']
    
    # 获取提取器插件
    extractor = registry.get_extractor('rule_based')
    
    # 运行时切换提取器
    engine.set_extractor(registry.get_extractor('llm_entity'))
    ```
"""

from typing import Dict, Type, Optional, Any, Callable
from utils.logger import get_logger

logger = get_logger(__name__)


class PluginRegistry:
    """
    所有 ContextMind 插件的集中注册中心
    
    提供插件的发现、注册和实例化功能。
    使 ContextMind 真正模块化和可扩展。
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
        """延迟初始化默认插件"""
        if self._initialized:
            return
        
        try:
            # 导入并注册提取器 (v0.2.1: 仅支持基于大语言模型的提取)
            from ..memory.extractor import (
                LLMBasedExtractor,
                ImportancePredictorExtractor,
            )
            self.register('extractors', 'llm_based', LLMBasedExtractor)  # 推荐使用
            self.register('extractors', 'importance', ImportancePredictorExtractor)
            
            # 导入并注册检索器
            from ..memory.retriever import (
                SemanticSearchRetriever,
                HybridRetriever,
                LocatorRetriever,
            )
            self.register('retrievers', 'semantic', SemanticSearchRetriever)
            self.register('retrievers', 'hybrid', HybridRetriever)
            self.register('retrievers', 'locator', LocatorRetriever)
            
            # 导入并注册更新器
            from ..memory.updater import (
                SimpleUpdater,
                ConflictResolverUpdater,
                AdaptiveEvictionUpdater,
            )
            self.register('updaters', 'simple', SimpleUpdater)
            self.register('updaters', 'conflict_resolver', ConflictResolverUpdater)
            self.register('updaters', 'adaptive', AdaptiveEvictionUpdater)
            
            # 导入并注册其他 Pipeline 组件 (v0.2.1: 移除已废弃组件)
            from ..pipeline.compressor import ContextCompressor
            from ..pipeline.reorderer import ContextReorderer
            from ..pipeline.preprocessor import InputPreprocessor
            from ..pipeline.response_handler import ResponseHandler
            from ..pipeline.summarizer import LLMBasedSummarizer
            
            self.register('compressors', 'default', ContextCompressor)
            self.register('reorderers', 'default', ContextReorderer)
            self.register('preprocessors', 'default', InputPreprocessor)
            self.register('response_handlers', 'default', ResponseHandler)
            self.register('summarizers', 'llm_based', LLMBasedSummarizer)
            
            self._initialized = True
            logger.info("[PluginRegistry] ✓ 默认插件初始化完成")
            
        except Exception as e:
            logger.error(f"[PluginRegistry] 插件初始化失败: {e}")
    
    def register(self, category: str, name: str, plugin_class: Type):
        """在类别中注册插件"""
        if category not in self._plugins:
            self._plugins[category] = {}
        self._plugins[category][name] = plugin_class
        logger.debug(f"[PluginRegistry] 已注册 {category}::{name}")
    
    def get(self, category: str, name: str, **kwargs) -> Optional[Any]:
        """根据类别和名称获取插件实例"""
        self._lazy_init()
        if category not in self._plugins or name not in self._plugins[category]:
            logger.warning(f"[PluginRegistry] 未找到插件 '{category}::{name}'")
            return None
        try:
            return self._plugins[category][name](**kwargs)
        except Exception as e:
            logger.error(f"[PluginRegistry] 实例化插件 {category}::{name} 失败: {e}")
            return None
    
    def list_plugins(self, category: str) -> list:
        """列出类别中的所有插件"""
        self._lazy_init()
        return list(self._plugins.get(category, {}).keys())
    
    def get_all_plugins(self) -> Dict[str, list]:
        """按类别获取所有已注册的插件"""
        self._lazy_init()
        return {cat: list(plugins.keys()) for cat, plugins in self._plugins.items()}
    
    # 每个类别的便捷方法
    def get_extractor(self, name: str = 'rule_based', **kwargs):
        """获取提取器插件 (默认: rule_based)"""
        return self.get('extractors', name, **kwargs)
    
    def list_extractors(self):
        """列出所有已注册的提取器"""
        return self.list_plugins('extractors')
    
    def get_retriever(self, name: str = 'semantic', **kwargs):
        """获取检索器插件 (默认: semantic)"""
        return self.get('retrievers', name, **kwargs)
    
    def list_retrievers(self):
        """列出所有已注册的检索器"""
        return self.list_plugins('retrievers')
    
    def get_updater(self, name: str = 'simple', **kwargs):
        """获取更新器插件 (默认: simple)"""
        return self.get('updaters', name, **kwargs)
    
    def list_updaters(self):
        """列出所有已注册的更新器"""
        return self.list_plugins('updaters')


# 全局注册中心实例
registry = PluginRegistry()

__all__ = ['PluginRegistry', 'registry']
