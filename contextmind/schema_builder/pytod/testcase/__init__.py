"""
pytod/testcase — 功能一：预生成测试数据。

本子包负责将 schema 中的意图定义转换为用于代码验证的测试用例，
并提供测试用例的持久化缓存与执行验证能力。
本子包不依赖 codegen/ 中的任何模块。

模块说明
--------
- ``models.py``    — 数据类：``TestCaseItem``、``FuncValidation``
- ``prompts.py``   — 测试用例 LLM 生成提示词
- ``generator.py`` — ``TestCaseGenerator``（LLM 驱动的测试用例生成器）
- ``kb_loader.py`` — KB 上下文数据加载（对话样本、发现数据）
- ``validator.py`` — 生成函数执行验证（``validate_function``、``write_validation_report``）
- ``cache.py``     — 测试用例 JSON 缓存读写（``save_test_cases``、``load_test_cases``）
"""

from contextmind.schema_builder.pytod.testcase.models import FuncValidation, TestCaseItem
from contextmind.schema_builder.pytod.testcase.generator import TestCaseGenerator
from contextmind.schema_builder.pytod.testcase.kb_loader import load_kb_context
from contextmind.schema_builder.pytod.testcase.cache import (
    load_test_cases,
    save_test_cases,
    test_cases_path_for_schema,
)
from contextmind.schema_builder.pytod.testcase.validator import validate_function, write_validation_report

__all__ = [
    "TestCaseItem",
    "FuncValidation",
    "TestCaseGenerator",
    "load_kb_context",
    "load_test_cases",
    "save_test_cases",
    "test_cases_path_for_schema",
    "validate_function",
    "write_validation_report",
]
