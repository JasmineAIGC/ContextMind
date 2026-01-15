"""
CircuitBreaker - 熔断器

防止算法超时或失败影响整体系统，提供：
- 超时保护
- 失败计数
- 自动降级
- 状态恢复
"""

from __future__ import annotations

from typing import Optional, Callable, Any, TypeVar, Awaitable
from enum import Enum
from datetime import datetime, timedelta
import asyncio

from ..logger import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"  # 正常状态
    OPEN = "open"  # 熔断状态
    HALF_OPEN = "half_open"  # 半开状态（尝试恢复）


class CircuitBreaker:
    """
    熔断器
    
    保护系统免受慢速或失败的算法影响。
    
    工作原理：
    1. CLOSED状态：正常执行
    2. 失败次数超过阈值 → OPEN状态
    3. OPEN状态：直接返回fallback结果
    4. 一段时间后 → HALF_OPEN状态
    5. HALF_OPEN状态：尝试执行，成功则恢复CLOSED，失败则回到OPEN
    
    使用示例：
        ```python
        breaker = CircuitBreaker(
            failure_threshold=5,
            timeout_seconds=10.0,
            reset_timeout=60
        )
        
        async def risky_operation():
            # 可能超时或失败的操作
            result = await expensive_algorithm()
            return result
        
        async def fallback():
            # 降级方案
            return simple_algorithm()
        
        result = await breaker.call(risky_operation, fallback)
        ```
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_seconds: float = 10.0,
        reset_timeout: int = 60,
    ):
        """
        初始化熔断器
        
        Args:
            failure_threshold: 失败阈值（连续失败多少次后熔断）
            timeout_seconds: 超时时间（秒）
            reset_timeout: 重置超时（秒，OPEN状态持续多久后尝试恢复）
        """
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.reset_timeout = reset_timeout
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.last_success_time: Optional[datetime] = None
    
    def _should_attempt_reset(self) -> bool:
        """判断是否应该尝试重置"""
        if self.state != CircuitState.OPEN:
            return False
        
        if self.last_failure_time is None:
            return True
        
        elapsed = (datetime.now() - self.last_failure_time).total_seconds()
        return elapsed >= self.reset_timeout
    
    async def call(
        self,
        func: Callable[[], Awaitable[T]],
        fallback: Optional[Callable[[], Awaitable[T]]] = None,
    ) -> T:
        """
        通过熔断器调用函数
        
        Args:
            func: 要执行的异步函数
            fallback: 降级函数（可选）
            
        Returns:
            函数执行结果或fallback结果
            
        Raises:
            Exception: 如果没有fallback且执行失败
        """
        # 检查是否应该尝试重置
        if self._should_attempt_reset():
            self.state = CircuitState.HALF_OPEN
            logger.info("Circuit breaker entering HALF_OPEN state")
        
        # OPEN状态：直接返回fallback
        if self.state == CircuitState.OPEN:
            logger.warning("Circuit breaker is OPEN, using fallback")
            if fallback:
                return await fallback()
            else:
                raise Exception("Circuit breaker is OPEN and no fallback provided")
        
        # CLOSED或HALF_OPEN状态：尝试执行
        try:
            # 使用asyncio.wait_for实现超时
            result = await asyncio.wait_for(
                func(),
                timeout=self.timeout_seconds
            )
            
            # 成功
            self._on_success()
            return result
        
        except asyncio.TimeoutError:
            logger.error(f"Function execution timed out after {self.timeout_seconds}s")
            self._on_failure()
            
            if fallback:
                logger.info("Using fallback due to timeout")
                return await fallback()
            else:
                raise
        
        except Exception as e:
            logger.error(f"Function execution failed: {e}")
            self._on_failure()
            
            if fallback:
                logger.info("Using fallback due to failure")
                return await fallback()
            else:
                raise
    
    def _on_success(self) -> None:
        """处理成功情况"""
        self.failure_count = 0
        self.last_success_time = datetime.now()
        
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            logger.info("Circuit breaker recovered to CLOSED state")
    
    def _on_failure(self) -> None:
        """处理失败情况"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(
                f"Circuit breaker opened after {self.failure_count} failures"
            )
    
    def reset(self) -> None:
        """手动重置熔断器"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        logger.info("Circuit breaker manually reset")
    
    def get_state(self) -> Dict[str, Any]:
        """获取熔断器状态"""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "last_success_time": self.last_success_time.isoformat() if self.last_success_time else None,
        }
