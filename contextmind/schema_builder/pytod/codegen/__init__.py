"""
pytod/codegen — 功能二：意图代码生成（4种算法）。

本子包包含 4 种 LLM 驱动的意图函数生成算法，以及各算法共用的基础设施。

子包说明
--------
- ``shared/``  — 4种算法共享基础设施（LLM 生成器、KB 加载、输出清洗、代码模板）
- ``loop/``    — 5 阶段迭代修复生成器（默认，``--generator loop``）
- ``alpha/``   — ACIA（AlphaCodium 启发）生成器（``--generator alpha``）
- ``sstar/``   — S* 生成器（``--generator sstar``）
- ``ctree/``   — CodeTree 生成器（``--generator ctree``）
"""

from contextmind.schema_builder.pytod.codegen.loop.builder import build_pytod_apis

__all__ = [
    "build_pytod_apis",
]
