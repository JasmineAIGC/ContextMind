"""
PerformanceMonitor - 性能监控工具

提供上下文优化过程的性能追踪和分析。
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import time


@dataclass
class ContextMetrics:
    """上下文优化指标"""
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 时间指标
    total_time: float = 0.0  # 总耗时（秒）
    optimize_time: float = 0.0  # 优化耗时
    retrieve_time: float = 0.0  # 检索耗时
    generate_time: float = 0.0  # 生成耗时
    
    # 上下文指标
    context_length: int = 0  # 上下文长度（字符）
    history_count: int = 0  # 历史消息数
    memory_count: int = 0  # 记忆条目数
    knowledge_count: int = 0  # 知识条目数
    
    # 质量指标
    relevance_score: float = 0.0  # 相关性分数
    compression_ratio: float = 0.0  # 压缩比
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'total_time': self.total_time,
            'optimize_time': self.optimize_time,
            'retrieve_time': self.retrieve_time,
            'generate_time': self.generate_time,
            'context_length': self.context_length,
            'history_count': self.history_count,
            'memory_count': self.memory_count,
            'knowledge_count': self.knowledge_count,
            'relevance_score': self.relevance_score,
            'compression_ratio': self.compression_ratio,
        }


class PerformanceMonitor:
    """
    性能监控器
    
    追踪和分析上下文优化的性能指标。
    """
    
    def __init__(self):
        """初始化监控器"""
        self.metrics_history: List[ContextMetrics] = []
        self._current_metrics: Optional[ContextMetrics] = None
        self._start_times: Dict[str, float] = {}
    
    def start_operation(self, operation: str):
        """
        开始记录操作时间
        
        Args:
            operation: 操作名称（optimize, retrieve, generate等）
        """
        self._start_times[operation] = time.time()
    
    def end_operation(self, operation: str) -> float:
        """
        结束记录操作时间
        
        Args:
            operation: 操作名称
            
        Returns:
            操作耗时（秒）
        """
        if operation not in self._start_times:
            return 0.0
        
        elapsed = time.time() - self._start_times[operation]
        del self._start_times[operation]
        
        # 更新当前指标
        if self._current_metrics:
            if operation == 'optimize':
                self._current_metrics.optimize_time = elapsed
            elif operation == 'retrieve':
                self._current_metrics.retrieve_time = elapsed
            elif operation == 'generate':
                self._current_metrics.generate_time = elapsed
            elif operation == 'total':
                self._current_metrics.total_time = elapsed
        
        return elapsed
    
    def start_turn(self):
        """开始新的对话轮次"""
        self._current_metrics = ContextMetrics()
        self.start_operation('total')
    
    def end_turn(self) -> ContextMetrics:
        """
        结束当前对话轮次
        
        Returns:
            当前轮次的指标
        """
        if self._current_metrics:
            self.end_operation('total')
            self.metrics_history.append(self._current_metrics)
            metrics = self._current_metrics
            self._current_metrics = None
            return metrics
        return ContextMetrics()
    
    def record_context_info(
        self,
        context_length: int = 0,
        history_count: int = 0,
        memory_count: int = 0,
        knowledge_count: int = 0,
    ):
        """
        记录上下文信息
        
        Args:
            context_length: 上下文长度
            history_count: 历史消息数
            memory_count: 记忆条目数
            knowledge_count: 知识条目数
        """
        if self._current_metrics:
            self._current_metrics.context_length = context_length
            self._current_metrics.history_count = history_count
            self._current_metrics.memory_count = memory_count
            self._current_metrics.knowledge_count = knowledge_count
    
    def get_average_metrics(self, last_n: Optional[int] = None) -> Dict[str, float]:
        """
        获取平均指标
        
        Args:
            last_n: 计算最近n次的平均值，None表示全部
            
        Returns:
            平均指标字典
        """
        if not self.metrics_history:
            return {}
        
        metrics_to_average = self.metrics_history[-last_n:] if last_n else self.metrics_history
        
        total_count = len(metrics_to_average)
        avg_metrics = {
            'total_time': sum(m.total_time for m in metrics_to_average) / total_count,
            'optimize_time': sum(m.optimize_time for m in metrics_to_average) / total_count,
            'retrieve_time': sum(m.retrieve_time for m in metrics_to_average) / total_count,
            'generate_time': sum(m.generate_time for m in metrics_to_average) / total_count,
            'context_length': sum(m.context_length for m in metrics_to_average) / total_count,
            'history_count': sum(m.history_count for m in metrics_to_average) / total_count,
            'memory_count': sum(m.memory_count for m in metrics_to_average) / total_count,
        }
        
        return avg_metrics
    
    def get_summary(self) -> str:
        """
        获取性能摘要
        
        Returns:
            性能摘要字符串
        """
        if not self.metrics_history:
            return "No metrics recorded yet."
        
        avg = self.get_average_metrics()
        latest = self.metrics_history[-1]
        
        summary = f"""
Performance Summary:
  Total Turns: {len(self.metrics_history)}
  
  Average Metrics:
    - Total Time: {avg['total_time']:.3f}s
    - Optimize Time: {avg['optimize_time']:.3f}s
    - Retrieve Time: {avg['retrieve_time']:.3f}s
    - Generate Time: {avg['generate_time']:.3f}s
    - Context Length: {avg['context_length']:.0f} chars
    - History Count: {avg['history_count']:.1f}
    - Memory Count: {avg['memory_count']:.1f}
  
  Latest Turn:
    - Total Time: {latest.total_time:.3f}s
    - Context Length: {latest.context_length} chars
"""
        return summary
