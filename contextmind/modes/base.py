"""
对话追踪器基础接口（Base Tracker Protocol）

定义所有对话追踪模式必须实现的公共接口。
任何新增模式只需实现此协议，即可与 ContextMind 的示例、
基准评测和上层工具无缝集成。

使用示例
--------
类型提示::

    from contextmind.modes.base import BaseTracker

    async def run_conversation(tracker: BaseTracker) -> None:
        result = await tracker.process_turn("你好")
        print(tracker.get_current_state())

实现新模式::

    from contextmind.modes.base import BaseTracker

    class MyCustomTracker:
        \"\"\"自定义追踪器，实现 BaseTracker 协议。\"\"\"

        @classmethod
        def from_scenario(cls, llm_client, scenario_config, **kwargs):
            return cls(...)

        async def process_turn(self, user_utterance: str, **kwargs):
            ...
            return {}

        def get_current_state(self):
            return {}

        def reset(self):
            pass
"""

from __future__ import annotations

from typing import Any, Dict, runtime_checkable
from typing import Protocol


@runtime_checkable
class BaseTracker(Protocol):
    """
    对话追踪器协议（结构子类型）。

    所有内置追踪器（DST、FnCTOD、PyTOD）均满足此协议。
    实现新追踪器时无需继承此类，只需提供下列四个方法即可
    通过 ``isinstance(tracker, BaseTracker)`` 检查。

    方法说明
    --------
    from_scenario : classmethod
        从场景配置创建追踪器实例的工厂方法（推荐入口）。
    process_turn : coroutine
        处理单轮用户输入，返回本轮提取的状态字典。
    get_current_state : method
        返回到目前为止累积的完整对话状态。
    reset : method
        清空对话历史和状态，开始新会话。
    """

    @classmethod
    def from_scenario(
        cls,
        llm_client: Any,
        scenario_config: Any,
        **kwargs: Any,
    ) -> "BaseTracker":
        """
        从场景配置创建追踪器实例。

        Args:
            llm_client: LLM 客户端实例（如 ``AdkLLMClient``）。
            scenario_config: 场景配置对象（``ScenarioConfig``）。
            **kwargs: 追踪器特定的额外参数。

        Returns:
            初始化完成的追踪器实例。
        """
        ...

    async def process_turn(
        self,
        user_utterance: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        处理单轮对话输入。

        Args:
            user_utterance: 用户本轮输入文本。
            **kwargs: 追踪器特定的额外参数（如 DST 的 ``system_utterance``）。

        Returns:
            本轮新增或更新的状态条目字典。
        """
        ...

    def get_current_state(self) -> Dict[str, Any]:
        """
        返回截至当前的累积对话状态。

        Returns:
            包含所有已提取槽位/字段的字典。
        """
        ...

    def reset(self) -> None:
        """清空所有对话历史和累积状态，开始新会话。"""
        ...
