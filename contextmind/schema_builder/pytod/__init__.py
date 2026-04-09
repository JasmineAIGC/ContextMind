"""
PyTOD 算法的 schema 数据构建子包。

本子包将 ``*_schema.json`` 文件转换为 PyTOD 算法所需的 companion 文件，
代码按功能分为两类目录：

shared/ — 共享基础模块（所有生成器共用）
-----------------------------------------
- ``shared/models.py``      — 数据类：``TestCaseItem``、``FuncValidation``
- ``shared/helpers.py``     — 生成文件中嵌入的共享工具函数模板（``SHARED_HELPERS``）
- ``shared/prompts.py``     — LLM 提示词常量（公共 5 阶段流程各阶段）
- ``shared/generator.py``   — ``PyTODApiCodeGenerator``（LLM 驱动的代码生成器）
- ``shared/cleaner.py``     — LLM 输出清洗辅助函数
- ``shared/kb_loader.py``   — KB 上下文数据加载
- ``shared/validator.py``   — 函数执行验证与报告
- ``shared/test_cache.py``  — 测试用例缓存文件读写

算法生成器（各算法独立实现）
------------------------------
- ``loop/``   — 5 阶段迭代修复生成器（默认，``--generator loop``）
- ``alpha/``  — ACIA（AlphaCodium 启发）生成器（``--generator alpha``）
- ``sstar/``  — S* 生成器（``--generator sstar``）
- ``ctree/``  — CodeTree 生成器（``--generator ctree``）
"""

from contextmind.schema_builder.pytod.loop.builder import build_pytod_apis
from contextmind.schema_builder.pytod.shared.generator import PyTODApiCodeGenerator
from contextmind.schema_builder.pytod.shared.models import FuncValidation, TestCaseItem

__all__ = [
    "build_pytod_apis",
    "PyTODApiCodeGenerator",
    "TestCaseItem",
    "FuncValidation",
]
