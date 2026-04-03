"""
PyTOD 算法的 schema 数据构建子包。

本子包包含将 ``*_schema.json`` 文件转换为 PyTOD 算法所需 companion 文件所需的全部代码：

- ``models.py``        — 数据类：``TestCaseItem``、``FuncValidation``
- ``helpers.py``       — 生成文件中嵌入的共享工具函数模板（``SHARED_HELPERS``）
- ``prompts.py``       — LLM 提示词常量（5 阶段流程各阶段）
- ``generator.py``     — ``PyTODApiCodeGenerator``（LLM 驱动的代码生成器）
- ``validator.py``     — 函数执行验证与报告（``validate_function``、``write_validation_report``）
- ``builder.py``       — ``build_pytod_apis()`` 5 阶段生成流程的具体实现
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
