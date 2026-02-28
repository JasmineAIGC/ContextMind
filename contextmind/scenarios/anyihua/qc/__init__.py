"""
安逸花外呼 · 任务一：质量标签预测（QC）

使用 PyTOD ExecutionEngine 注册的 5 个标签检测 API，
对坐席回复进行离线质量分类。

主要组件:
    engine.py     — build_qc_engine()：5 个标签检测 API（纯规则，无 LLM）
    predictor.py  — predict_label_pytod()：纯规则预测
                    detect_session_llm()：LLM 全量质检
                    PyTODQualityChecker：批量质检器（支持 Hybrid 模式）

典型使用:
    from contextmind.scenarios.anyihua.qc import PyTODQualityChecker
    checker = PyTODQualityChecker()
    result = checker.check(session, llm_client=llm, use_pytod_first=True)
"""

from .engine import build_qc_engine
from .predictor import PyTODQualityChecker, detect_session_llm, predict_label_pytod

__all__ = [
    "build_qc_engine",
    "predict_label_pytod",
    "detect_session_llm",
    "PyTODQualityChecker",
]
