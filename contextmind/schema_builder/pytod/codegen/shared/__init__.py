"""
pytod/codegen/shared — 4种代码生成算法共享的基础设施。

模块说明
--------
- ``helpers.py``    — 生成文件中嵌入的共享工具函数模板（``SHARED_HELPERS``）
- ``generator.py``  — ``PyTODApiCodeGenerator``（LLM 驱动的代码生成器，专注 Phase 3/4）
- ``cleaner.py``    — LLM 输出清洗（``clean_llm_function_body``、``clean_llm_module``）
- ``kb_loader.py``  — 已迁移至 ``testcase/kb_loader.py``（本文件为向后兼容的转发模块）

KB 上下文数据加载（对话样本、发现数据）现在位于
:mod:`contextmind.schema_builder.pytod.testcase.kb_loader`。
"""

from contextmind.schema_builder.pytod.codegen.shared.generator import PyTODApiCodeGenerator
from contextmind.schema_builder.pytod.codegen.shared.helpers import SHARED_HELPERS

__all__ = [
    "PyTODApiCodeGenerator",
    "SHARED_HELPERS",
]
