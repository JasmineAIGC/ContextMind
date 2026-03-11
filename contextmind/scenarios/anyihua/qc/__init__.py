"""
安逸花外呼 · 任务一：质量标签预测（QC）

使用 PyTOD ExecutionEngine 注册的 4 个事实数据 API，
对坐席回复进行离线质量分类。

设计原则（PyTOD 哲学）：
    引擎 API 只提供客观事实数据（get_*_data），
    标签判断由 LLM（classify_session_llm）或规则（predict_label_pytod）完成。

主要组件:
    schema.py     — ANYIHUA_QC_SCHEMA：QC 任务的 ServiceSchema（5 个检测意图）
    engine.py     — build_qc_engine()：4 个事实数据 API（无规则标签预测）
    predictor.py  — predict_label_pytod()：规则快速预测（应用规则阈值）
                    classify_session_llm()：LLM 全量质检（语义推理）
                    PyTODQualityChecker：批量质检器（支持 Hybrid 模式）

典型使用:
    from contextmind.scenarios.anyihua.qc import PyTODQualityChecker, ANYIHUA_QC_SCHEMA
    checker = PyTODQualityChecker()
    result = checker.check(session, llm_client=llm, use_pytod_first=True)
"""

from .engine import build_qc_engine
from .predictor import PyTODQualityChecker, classify_session_llm, predict_label_pytod
from .schema import ANYIHUA_QC_SCHEMA, ANYIHUA_QC_SCHEMA_DICT

__all__ = [
    "build_qc_engine",
    "predict_label_pytod",
    "classify_session_llm",
    "PyTODQualityChecker",
    "ANYIHUA_QC_SCHEMA",
    "ANYIHUA_QC_SCHEMA_DICT",
]
