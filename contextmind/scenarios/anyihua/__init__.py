"""
安逸花外呼促活服务 · PyTOD 场景实现

基于 docs/analysis/pytod-on-chat-test-100.md 的分析与代码指导，
在 chat_test_100.json（100 条安逸花外呼对话数据集）上实现 PyTOD 的两种应用方式：

方式 A：离线质检（Offline QC）
    输入: (用户信息, 对话历史, 坐席回复)
    → LLM 五分类质检（detect_session_llm）
    → 预测标签 vs 人工校验标签 → F1 评估

方式 B：在线生成（Online Generation）
    输入: (用户信息, 对话历史, 最后用户发言)
    → [步骤1] 动作解析器 (LLM) → PyTOD 程序
    → [步骤2] ExecutionEngine.execute_program()
    → [步骤3] 对话管理器 (LLM) → 基于真实数据生成回复

目录结构:
    utils.py          - 中文数字解析、用户信息解析
    engine.py         - ExecutionEngine 构建（mock CRM API 注册）
    schema.py         - ServiceSchema 定义
    detectors.py      - 质量问题检测函数（规则版保留供参考；主流水线使用 detect_session_llm）
    quality_checker.py - PyTODQualityChecker 批量质检器（LLM 全量分类）
"""

from .utils import cn2int, extract_amounts, parse_user_info
from .engine import build_anyihua_engine
from .schema import ANYIHUA_SCHEMA_DICT, ANYIHUA_SCHEMA
from .detectors import (
    detect_data_error,
    detect_data_error_recent_history,
    detect_repetition,
    detect_improper_farewell,
    detect_off_topic_rule,
    detect_off_topic_llm,
    detect_session_llm,
    FAREWELL_KEYWORDS,
    USER_CONCERN_WORDS,
    OFFTOPIC_SIGNALS,
)
from .quality_checker import PyTODQualityChecker

__all__ = [
    # utils
    "cn2int",
    "extract_amounts",
    "parse_user_info",
    # engine
    "build_anyihua_engine",
    # schema
    "ANYIHUA_SCHEMA_DICT",
    "ANYIHUA_SCHEMA",
    # detectors — rule-based (kept for reference / debugging)
    "detect_data_error",
    "detect_data_error_recent_history",
    "detect_repetition",
    "detect_improper_farewell",
    "detect_off_topic_rule",
    "detect_off_topic_llm",
    # detectors — LLM-based (main pipeline)
    "detect_session_llm",
    # constants
    "FAREWELL_KEYWORDS",
    "USER_CONCERN_WORDS",
    "OFFTOPIC_SIGNALS",
    # quality checker
    "PyTODQualityChecker",
]
