"""
CacheManager - 缓存管理器

用于缓存计算密集型结果：
- Embedding缓存
- Summary缓存
- 计算结果缓存

提高系统性能，减少重复计算。
"""

from __future__ import annotations

from typing import Optional, Any, Dict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import OrderedDict

from ..logger import get_logger

logger = get_logger(__name__)


@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    value: Any
    created_at: datetime = field(default_factory=datetime.now)
    ttl: Optional[int] = None  # TTL in seconds
    hit_count: int = 0
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.ttl is None:
            return False
        
        expiry_time = self.created_at + timedelta(seconds=self.ttl)
        return datetime.now() > expiry_time


class CacheManager:
    """
    缓存管理器
    
    使用LRU（Least Recently Used）策略的缓存系统。
    支持TTL（Time To Live）过期。
    
    使用示例：
        ```python
        cache = CacheManager(max_size=1000, default_ttl=3600)
        
        # 存储
        cache.set("key1", "value1")
        
        # 获取
        value = cache.get("key1")
        
        # 带过期时间
        cache.set("key2", "value2", ttl=60)
        
        # 统计
        stats = cache.get_stats()
        ```
    """
    
    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: Optional[int] = None,
    ):
        """
        初始化缓存管理器
        
        Args:
            max_size: 最大缓存数量
            default_ttl: 默认过期时间（秒）
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        
        # 使用OrderedDict实现LRU
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        
        # 统计信息
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值
        
        Args:
            key: 缓存键
            
        Returns:
            缓存值，如果不存在或已过期则返回None
        """
        if key not in self._cache:
            self._misses += 1
            logger.debug(f"Cache miss: {key}")
            return None
        
        entry = self._cache[key]
        
        # 检查是否过期
        if entry.is_expired():
            del self._cache[key]
            self._misses += 1
            logger.debug(f"Cache expired: {key}")
            return None
        
        # 更新访问顺序（LRU）
        self._cache.move_to_end(key)
        entry.hit_count += 1
        self._hits += 1
        
        logger.debug(f"Cache hit: {key}")
        return entry.value
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> None:
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），覆盖默认值
        """
        # 如果已存在，先删除
        if key in self._cache:
            del self._cache[key]
        
        # 如果达到容量上限，删除最旧的项
        if len(self._cache) >= self.max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            logger.debug(f"Cache evicted (LRU): {oldest_key}")
        
        # 添加新条目
        entry = CacheEntry(
            key=key,
            value=value,
            ttl=ttl if ttl is not None else self.default_ttl
        )
        self._cache[key] = entry
        
        logger.debug(f"Cache set: {key}")
    
    def delete(self, key: str) -> bool:
        """
        删除缓存
        
        Args:
            key: 缓存键
            
        Returns:
            是否成功删除
        """
        if key in self._cache:
            del self._cache[key]
            logger.debug(f"Cache deleted: {key}")
            return True
        return False
    
    def clear(self) -> None:
        """清空所有缓存"""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        logger.debug("Cache cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            统计信息字典
        """
        total_requests = self._hits + self._misses
        hit_rate = self._hits / total_requests if total_requests > 0 else 0.0
        
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "utilization": len(self._cache) / self.max_size if self.max_size > 0 else 0.0
        }
    
    def cleanup_expired(self) -> int:
        """
        清理过期的缓存条目
        
        Returns:
            清理的条目数量
        """
        expired_keys = [
            key for key, entry in self._cache.items()
            if entry.is_expired()
        ]
        
        for key in expired_keys:
            del self._cache[key]
        
        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
        
        return len(expired_keys)
