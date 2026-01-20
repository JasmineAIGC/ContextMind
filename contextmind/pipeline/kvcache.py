"""
KVCacheManager - KV Cache管理接口（轻量级）

重要：KV Cache管理（Step 5）属于LLM推理层优化，在EXTERNAL实现（vLLM、sglang等）。
ContextMind的核心是Step 1-4（上下文工程）+ Step 6（输出后处理）。

此模块提供轻量级接口，用于：
1. 定义KV Cache策略的标准接口
2. 与外部推理框架（vLLM、sglang）集成时的配置指引
3. 研究和实验目的

实际KV Cache管理由用户的LLM推理引擎处理：
- vLLM: 内置PagedAttention + 自定义eviction
- sglang: 内置RadixAttention + 自定义eviction  
- HuggingFace: 用户自行实现cache管理

常用KV Cache策略（供参考）：
- Eviction策略：H2O（注意力分数阈值）、SnapKV（快照关键KV）、PyramidKV
- 其他：滑动窗口fallback、Infini-attention（无限长支持）
- 底层集成：需要hook到vLLM/sglang的attention计算层

注意：此模块不改变Prompt内容，属于推理优化而非上下文工程。
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class EvictionStrategy(Enum):
    """KV Cache剔除策略"""
    H2O = "h2o"  # Heavy-Hitter Oracle
    SNAPKV = "snapkv"  # Snapshot KV
    PYRAMID = "pyramid"  # PyramidKV
    SLIDING_WINDOW = "sliding_window"  # 滑动窗口
    LRU = "lru"  # Least Recently Used


class KVCacheManagerStrategy(ABC):
    """KV Cache管理策略基类"""
    
    @abstractmethod
    def should_evict(self, cache_state: Dict[str, Any]) -> bool:
        """
        判断是否需要剔除缓存
        
        Args:
            cache_state: 当前缓存状态
            
        Returns:
            是否需要剔除
        """
        pass
    
    @abstractmethod
    def select_eviction_targets(
        self,
        cache_state: Dict[str, Any],
        num_to_evict: int
    ) -> List[int]:
        """
        选择要剔除的缓存项
        
        Args:
            cache_state: 当前缓存状态
            num_to_evict: 要剔除的数量
            
        Returns:
            要剔除的缓存项索引列表
        """
        pass


class SlidingWindowStrategy(KVCacheManagerStrategy):
    """
    滑动窗口策略
    
    保留最近N个token的KV cache，剔除最早的。
    简单高效，适合大多数场景。
    """
    
    def __init__(self, window_size: int = 2048):
        """
        初始化滑动窗口策略
        
        Args:
            window_size: 窗口大小（token数）
        """
        self.window_size = window_size
    
    def should_evict(self, cache_state: Dict[str, Any]) -> bool:
        """判断是否需要剔除"""
        cache_size = cache_state.get('size', 0)
        return cache_size > self.window_size
    
    def select_eviction_targets(
        self,
        cache_state: Dict[str, Any],
        num_to_evict: int
    ) -> List[int]:
        """选择最早的N个缓存项"""
        return list(range(num_to_evict))


class KVCacheManager:
    """
    KV Cache管理器主类
    
    协调KV cache管理策略，提供统一接口。
    
    注意：这是一个接口/占位符实现。
    实际部署需要与推理框架（vLLM, sglang等）集成。
    """
    
    def __init__(
        self,
        strategy: Optional[KVCacheManagerStrategy] = None,
        enabled: bool = False
    ):
        """
        初始化KV Cache管理器
        
        Args:
            strategy: 管理策略，默认使用SlidingWindowStrategy
            enabled: 是否启用（默认关闭，需要推理框架支持）
        """
        self.strategy = strategy or SlidingWindowStrategy()
        self.enabled = enabled
        
        if not enabled:
            logger.info("[KVCacheManager] KV Cache管理已禁用（需要推理框架集成）")
        else:
            logger.info(f"[KVCacheManager] 初始化完成 - 策略: {self.strategy.__class__.__name__}")
        
        # 缓存状态（占位符）
        self.cache_state: Dict[str, Any] = {
            'size': 0,
            'capacity': 4096,
            'tokens': []
        }
    
    def update_cache_state(self, new_tokens: List[Any]):
        """
        更新缓存状态
        
        Args:
            new_tokens: 新加入的tokens
        """
        if not self.enabled:
            return
        
        self.cache_state['tokens'].extend(new_tokens)
        self.cache_state['size'] = len(self.cache_state['tokens'])
        
        logger.debug(f"[KVCacheManager] 缓存更新: {self.cache_state['size']} tokens")
    
    def manage_cache(self):
        """管理缓存：检查是否需要剔除并执行"""
        if not self.enabled:
            return
        
        if self.strategy.should_evict(self.cache_state):
            current_size = self.cache_state['size']
            capacity = self.cache_state['capacity']
            num_to_evict = current_size - capacity
            
            logger.info(f"[KVCacheManager] 缓存已满 ({current_size}/{capacity})，准备剔除 {num_to_evict} 项")
            
            # 选择要剔除的项
            eviction_targets = self.strategy.select_eviction_targets(
                self.cache_state,
                num_to_evict
            )
            
            # 执行剔除（占位符）
            for idx in sorted(eviction_targets, reverse=True):
                if idx < len(self.cache_state['tokens']):
                    self.cache_state['tokens'].pop(idx)
            
            self.cache_state['size'] = len(self.cache_state['tokens'])
            
            logger.info(f"[KVCacheManager] ✓ 剔除完成，当前缓存: {self.cache_state['size']} tokens")
    
    def clear_cache(self):
        """清空缓存"""
        if not self.enabled:
            return
        
        logger.info("[KVCacheManager] 清空KV Cache")
        self.cache_state = {
            'size': 0,
            'capacity': self.cache_state['capacity'],
            'tokens': []
        }
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            缓存统计字典
        """
        if not self.enabled:
            return {'enabled': False}
        
        return {
            'enabled': True,
            'size': self.cache_state['size'],
            'capacity': self.cache_state['capacity'],
            'utilization': self.cache_state['size'] / self.cache_state['capacity']
        }
