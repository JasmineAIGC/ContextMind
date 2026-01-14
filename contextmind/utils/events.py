"""
EventBus - 事件系统

提供发布-订阅模式的事件系统，支持解耦的组件通信。
"""

from typing import Dict, List, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
import asyncio


@dataclass
class Event:
    """事件对象"""
    name: str  # 事件名称
    data: Any  # 事件数据
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = ""  # 事件来源
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'name': self.name,
            'data': self.data,
            'timestamp': self.timestamp.isoformat(),
            'source': self.source,
        }


class EventBus:
    """
    事件总线
    
    实现发布-订阅模式，支持组件间的松耦合通信。
    
    使用示例：
        ```python
        bus = EventBus()
        
        # 订阅事件
        def on_optimize(event):
            print(f"Context optimized: {event.data}")
        
        bus.subscribe('context_optimized', on_optimize)
        
        # 发布事件
        bus.publish('context_optimized', {'length': 100})
        ```
    """
    
    def __init__(self):
        """初始化事件总线"""
        self._subscribers: Dict[str, List[Callable]] = {}
        self._event_history: List[Event] = []
        self._max_history = 1000  # 最多保留1000条历史
    
    def subscribe(self, event_name: str, callback: Callable):
        """
        订阅事件
        
        Args:
            event_name: 事件名称
            callback: 回调函数，接收Event对象作为参数
        """
        if event_name not in self._subscribers:
            self._subscribers[event_name] = []
        
        if callback not in self._subscribers[event_name]:
            self._subscribers[event_name].append(callback)
    
    def unsubscribe(self, event_name: str, callback: Callable):
        """
        取消订阅事件
        
        Args:
            event_name: 事件名称
            callback: 回调函数
        """
        if event_name in self._subscribers:
            if callback in self._subscribers[event_name]:
                self._subscribers[event_name].remove(callback)
    
    def publish(self, event_name: str, data: Any = None, source: str = ""):
        """
        发布事件（同步）
        
        Args:
            event_name: 事件名称
            data: 事件数据
            source: 事件来源
        """
        event = Event(name=event_name, data=data, source=source)
        
        # 保存到历史
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history.pop(0)
        
        # 通知订阅者
        if event_name in self._subscribers:
            for callback in self._subscribers[event_name]:
                try:
                    callback(event)
                except Exception as e:
                    # 不因单个订阅者的错误而中断
                    print(f"Error in event callback: {e}")
    
    async def publish_async(self, event_name: str, data: Any = None, source: str = ""):
        """
        发布事件（异步）
        
        Args:
            event_name: 事件名称
            data: 事件数据
            source: 事件来源
        """
        event = Event(name=event_name, data=data, source=source)
        
        # 保存到历史
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history.pop(0)
        
        # 通知订阅者（支持异步回调）
        if event_name in self._subscribers:
            tasks = []
            for callback in self._subscribers[event_name]:
                try:
                    result = callback(event)
                    if asyncio.iscoroutine(result):
                        tasks.append(result)
                except Exception as e:
                    print(f"Error in event callback: {e}")
            
            # 等待所有异步回调完成
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
    
    def get_history(self, event_name: Optional[str] = None, limit: int = 100) -> List[Event]:
        """
        获取事件历史
        
        Args:
            event_name: 事件名称，None表示所有事件
            limit: 返回的最大数量
            
        Returns:
            事件列表
        """
        if event_name:
            events = [e for e in self._event_history if e.name == event_name]
        else:
            events = self._event_history
        
        return events[-limit:]
    
    def clear_history(self):
        """清空事件历史"""
        self._event_history.clear()
    
    def get_subscribers_count(self, event_name: Optional[str] = None) -> int:
        """
        获取订阅者数量
        
        Args:
            event_name: 事件名称，None表示所有订阅者
            
        Returns:
            订阅者数量
        """
        if event_name:
            return len(self._subscribers.get(event_name, []))
        else:
            return sum(len(subs) for subs in self._subscribers.values())
