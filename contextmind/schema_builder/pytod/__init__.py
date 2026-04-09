"""
PyTOD 算法的 schema 数据构建子包。

本子包包含将 ``*_schema.json`` 文件转换为 PyTOD 算法所需 companion 文件所需的全部代码：

共享基础模块（pytod/ 根目录）
------------------------------
- ``models.py``      — 数据类：``TestCaseItem``、``FuncValidation``
- ``helpers.py``     — 生成文件中嵌入的共享工具函数模板（``SHARED_HELPERS``）
- ``prompts.py``     — LLM 提示词常量（公共 5 阶段流程各阶段）
- ``generator.py``   — ``PyTODApiCodeGenerator``（LLM 驱动的代码生成器）
- ``cleaner.py``     — LLM 输出清洗辅助函数（``clean_llm_function_body``、``clean_llm_module``）
- ``kb_loader.py``   — KB 上下文数据加载（对话样本、发现数据、conversion_summary）
- ``validator.py``   — 函数执行验证与报告（``validate_function``、``write_validation_report``）
- ``test_cache.py``  — 测试用例缓存文件读写（``save_test_cases``、``load_test_cases``）

各算法生成器子包
----------------
- ``loop/``   — 5 阶段迭代修复生成器（默认，``--generator loop``）
- ``alpha/``  — ACIA（AlphaCodium 启发）生成器（``--generator alpha``）
- ``sstar/``  — S* 生成器（``--generator sstar``）
- ``ctree/``  — CodeTree 生成器（``--generator ctree``）
"""

from contextmind.schema_builder.pytod.loop.builder import build_pytod_apis
from contextmind.schema_builder.pytod.generator import PyTODApiCodeGenerator
from contextmind.schema_builder.pytod.models import FuncValidation, TestCaseItem

__all__ = [
    "build_pytod_apis",
    "PyTODApiCodeGenerator",
    "TestCaseItem",
    "FuncValidation",
]
