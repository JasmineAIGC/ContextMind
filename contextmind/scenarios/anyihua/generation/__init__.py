"""
安逸花外呼 · 任务二：坐席回复生成（Generation）

使用 PyTOD ExecutionEngine 注册的 CRM 查询 API，
通过 AdkPyTODAgent（ADK 原生函数调用）生成更优质的坐席回复。

主要组件:
    engine.py  — build_generation_engine()：CRM 查询 API（query_account 等）
    schema.py  — ANYIHUA_SCHEMA：ServiceSchema，约束动作解析器意图范围

典型使用:
    from contextmind.scenarios.anyihua.generation import build_generation_engine
    from contextmind.modes.pytod.adk_bridge import AdkPyTODAgent

    engine = build_generation_engine(session)
    agent = AdkPyTODAgent(engine=engine, scenario_context="安逸花外呼场景")
    result = await agent.process_turn(user_utterance="我的额度是多少？")
"""

from .engine import build_generation_engine
from .schema import ANYIHUA_SCHEMA, ANYIHUA_SCHEMA_DICT

__all__ = [
    "build_generation_engine",
    "ANYIHUA_SCHEMA",
    "ANYIHUA_SCHEMA_DICT",
]
