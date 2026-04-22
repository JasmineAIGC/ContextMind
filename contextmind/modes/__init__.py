"""
ContextMind 对话处理模式

提供五种对话处理模式（全部基于 ADK）：
- dst:    对话状态追踪
- fnctod: ADK 原生函数调用对话状态追踪
- pytod:  ADK 原生可编程任务型对话
- evolve: 演化式上下文优化
- genie:  Genie Worksheets 声明式策略对话
"""

from __future__ import annotations

from typing import Any, Optional

from contextmind.modes.base import BaseTracker
try:
    from contextmind.modes.dst import DialogueStateTracker
    from contextmind.modes.fnctod import FnCTODTracker
    from contextmind.modes.pytod import AdkPyTODTracker
    from contextmind.modes.evolve import create_app_for_scenario, EvolveEngine
except ImportError:
    pass

_SUPPORTED_ALGORITHMS = ("dst", "fnctod", "pytod", "evolve", "genie")


def build_tracker(algorithm: str, model: Optional[str] = None, **kwargs: Any) -> Any:
    """为指定算法创建对话追踪器实例。

    适用于 benchmark 批量评测等无需完整场景配置的场景。
    LLM 配置从 ``.env`` 文件自动加载，可通过 ``model`` 参数覆盖默认模型。

    Args:
        algorithm: 算法名称，可选 ``"dst"`` | ``"fnctod"`` | ``"pytod"`` | ``"evolve"`` | ``"genie"``。
        model: 可选的 LLM 模型名称（覆盖 ``.env`` 默认配置）。
        **kwargs: 传递给追踪器构造函数的额外参数。

    Returns:
        对应算法的追踪器实例，具备 ``process_turn`` / ``reset`` / ``get_current_state`` 接口。

    Raises:
        ValueError: ``algorithm`` 不在支持列表中。
    """
    from contextmind.infra.llm_client import AdkLLMClient, LLMConfig

    llm_cfg = LLMConfig(model=model) if model else None
    llm_client = AdkLLMClient(config=llm_cfg)

    if algorithm == "dst":
        return DialogueStateTracker(llm_client=llm_client, **kwargs)

    if algorithm == "fnctod":
        from contextmind.modes.fnctod.function_manager import FunctionManager
        fm = FunctionManager()
        return FnCTODTracker(function_manager=fm, config=llm_cfg, **kwargs)

    if algorithm == "pytod":
        from contextmind.modes.pytod.execution_engine import ExecutionEngine
        engine = ExecutionEngine()
        return AdkPyTODTracker(llm_client=llm_client, engine=engine, **kwargs)

    if algorithm == "evolve":
        from contextmind.modes.evolve import EvolveApplication, EvolveEngine
        engine = EvolveEngine(
            app_name="benchmark_evolve",
            user_id="benchmark_user",
            llm_client=llm_client,
        )
        return EvolveApplication(evolve_engine=engine, llm_client=llm_client)

    if algorithm == "genie":
        from contextmind.modes.genie import GenieTracker
        schema = kwargs.pop("schema", None)
        worksheet_path = kwargs.pop("worksheet_path", None)
        scene_description = kwargs.pop("scene_description", "")
        intent_name = kwargs.pop("intent_name", None)
        if schema is None and worksheet_path is None:
            raise ValueError(
                "genie 模式需要提供 schema 或 worksheet_path 参数"
            )
        if schema is None:
            from contextmind.schema_builder.genie_worksheets import WorksheetLoader
            from pathlib import Path
            ws_path = Path(worksheet_path)
            if ws_path.suffix.lower() == ".csv":
                schema = WorksheetLoader.from_csv(ws_path, service_description=scene_description)
            else:
                schema = WorksheetLoader.from_json(ws_path)
        return GenieTracker(
            llm_client=llm_client,
            schema=schema,
            scene_description=scene_description,
            intent_name=intent_name,
            **kwargs,
        )

    raise ValueError(
        f"未知算法: {algorithm!r}，可选: {' | '.join(_SUPPORTED_ALGORITHMS)}"
    )


__all__ = [
    "BaseTracker",
    "DialogueStateTracker",
    "FnCTODTracker",
    "AdkPyTODTracker",
    "EvolveEngine",
    "create_app_for_scenario",
    "build_tracker",
]
