"""
Genie Worksheets 执行模式 — contextmind.modes.genie

提供 Worksheet 驱动的声明式对话策略执行能力，作为 ContextMind 框架的第五种执行模式。

核心组件
--------
- ``PolicyExecutor`` (policy_executor.py)：无 LLM 的确定性 Worksheet 状态机。
- ``SemanticParser`` (semantic_parser.py)：LLM 驱动的意图解析器（LLM-1）。
- ``GenieTracker`` (tracker.py)：整合以上两者，实现 BaseTracker 协议。

典型用法::

    from contextmind.pipeline import ContextPipeline

    pipeline = ContextPipeline(mode="genie")
    pipeline.load_kb("schema/restaurant_schema.json",
                     worksheet_path="worksheets/restaurant.csv")
    result = await pipeline.process_turn("我想订一桌川菜")
    print(result["response"])
    print(result["worksheet_state"])    # Worksheet 当前填写状态
    print(result["is_complete"])        # Worksheet 是否已完成
"""

from contextmind.modes.genie.tracker import GenieTracker
from contextmind.modes.genie.policy_executor import PolicyExecutor, WorksheetState
from contextmind.modes.genie.semantic_parser import SemanticParser

__all__ = [
    "GenieTracker",
    "PolicyExecutor",
    "WorksheetState",
    "SemanticParser",
]
