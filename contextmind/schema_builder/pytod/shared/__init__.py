"""
pytod/shared — 所有生成器共享的基础模块。

本子包是 pytod 四个算法生成器（loop/alpha/sstar/ctree）使用的共享基础设施，
按职责分为以下模块：

- ``models.py``      — 数据类：``TestCaseItem``、``FuncValidation``
- ``helpers.py``     — 生成文件中嵌入的共享工具函数模板（``SHARED_HELPERS``）
- ``prompts.py``     — LLM 提示词常量（公共 5 阶段流程各阶段）
- ``generator.py``   — ``PyTODApiCodeGenerator``（LLM 驱动的代码生成器）
- ``cleaner.py``     — LLM 输出清洗辅助函数（``clean_llm_function_body``、``clean_llm_module``）
- ``kb_loader.py``   — KB 上下文数据加载（对话样本、发现数据、conversion_summary）
- ``validator.py``   — 函数执行验证与报告（``validate_function``、``write_validation_report``）
- ``test_cache.py``  — 测试用例缓存文件读写（``save_test_cases``、``load_test_cases``）
"""

from contextmind.schema_builder.pytod.shared.models import FuncValidation, TestCaseItem
from contextmind.schema_builder.pytod.shared.generator import PyTODApiCodeGenerator
from contextmind.schema_builder.pytod.shared.validator import validate_function, write_validation_report
from contextmind.schema_builder.pytod.shared.test_cache import load_test_cases, save_test_cases, test_cases_path_for_schema

__all__ = [
    "TestCaseItem",
    "FuncValidation",
    "PyTODApiCodeGenerator",
    "validate_function",
    "write_validation_report",
    "load_test_cases",
    "save_test_cases",
    "test_cases_path_for_schema",
]
