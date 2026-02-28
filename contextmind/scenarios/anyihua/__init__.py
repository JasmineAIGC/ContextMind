"""
安逸花外呼促活场景 · PyTOD 实现

本场景包含两个独立任务，代码完全隔离：

任务一：离线质检（Label Prediction / QC）
    位置: contextmind/scenarios/anyihua/qc/
    入口: examples/anyihua_qc_demo.py

    使用 PyTOD ExecutionEngine 注册 5 个标签检测 API（对应 5 个质量标签），
    通过纯规则预测或 LLM 辅助分类对坐席回复进行质量标注。

    from contextmind.scenarios.anyihua.qc import (
        build_qc_engine,
        predict_label_pytod,
        classify_session_llm,
        PyTODQualityChecker,
    )

任务二：在线生成（Response Generation）
    位置: contextmind/scenarios/anyihua/generation/
    入口: examples/anyihua_generation_demo.py

    使用 PyTOD ExecutionEngine 注册 CRM 查询 API（query_account 等），
    通过 PyTODTracker 三步流程（动作解析器 → 执行引擎 → 对话管理器）
    生成更优质的坐席回复。

    from contextmind.scenarios.anyihua.generation import (
        build_generation_engine,
        ANYIHUA_SCHEMA,
    )

共享工具:
    from contextmind.scenarios.anyihua.utils import (
        cn2int, extract_amounts, parse_user_info,
        AGENT_PREFIX, USER_PREFIX, FAREWELL_KEYWORDS,
        USER_CONCERN_WORDS, OFFTOPIC_SIGNALS,
    )
"""

from .utils import cn2int, extract_amounts, parse_user_info
from .qc import build_qc_engine, PyTODQualityChecker, predict_label_pytod, classify_session_llm
from .generation import build_generation_engine, ANYIHUA_SCHEMA, ANYIHUA_SCHEMA_DICT

__all__ = [
    # 共享工具
    "cn2int",
    "extract_amounts",
    "parse_user_info",
    # 任务一：QC
    "build_qc_engine",
    "predict_label_pytod",
    "classify_session_llm",
    "PyTODQualityChecker",
    # 任务二：Generation
    "build_generation_engine",
    "ANYIHUA_SCHEMA",
    "ANYIHUA_SCHEMA_DICT",
]
