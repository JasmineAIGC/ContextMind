"""
PyTOD 算法的 schema 数据构建子包。

本子包将 ``*_schema.json`` 文件转换为 PyTOD 算法所需的 companion 文件，
代码按两大功能分组：

testcase/ — 功能一：预生成测试数据
-------------------------------------
预先为每个意图生成覆盖多种场景的测试用例，供后续代码生成阶段验证使用。
本子包完全自包含，不依赖 codegen/ 中的任何模块。

- ``testcase/models.py``    — 数据类：``TestCaseItem``、``FuncValidation``
- ``testcase/prompts.py``   — 测试用例 LLM 生成提示词
- ``testcase/generator.py`` — ``TestCaseGenerator``（LLM 驱动的测试用例生成器）
- ``testcase/kb_loader.py`` — KB 上下文数据加载（对话样本、发现数据）
- ``testcase/validator.py`` — 生成函数执行验证与报告
- ``testcase/cache.py``     — 测试用例 JSON 缓存读写

codegen/ — 功能二：意图代码生成（4种算法）
--------------------------------------------
使用 4 种不同的 LLM 驱动算法，为每个意图生成可执行的 Python 函数。
codegen/ 依赖 testcase/ 提供的测试数据和 models（单向依赖）。

- ``codegen/shared/``  — 4种算法共享基础设施（PyTODApiCodeGenerator、SHARED_HELPERS、cleaner）
- ``codegen/loop/``    — 5 阶段迭代修复生成器（默认，``--generator loop``）
- ``codegen/alpha/``   — ACIA（AlphaCodium 启发）生成器（``--generator alpha``）
- ``codegen/sstar/``   — S* 生成器（``--generator sstar``）
- ``codegen/ctree/``   — CodeTree 生成器（``--generator ctree``）
"""

from contextmind.schema_builder.pytod.codegen.loop.builder import build_pytod_apis
from contextmind.schema_builder.pytod.codegen.shared.generator import PyTODApiCodeGenerator
from contextmind.schema_builder.pytod.testcase.models import FuncValidation, TestCaseItem

__all__ = [
    "build_pytod_apis",
    "PyTODApiCodeGenerator",
    "TestCaseItem",
    "FuncValidation",
]
