"""
modes.evolve.engine — 向后兼容重定向（已迁移至 modes.evolve.core.engine）

.. deprecated::
    EvolveEngine 已移至 ``contextmind.modes.evolve.core.engine``。
    此模块保留为向后兼容的重定向入口。
    推荐通过 ``contextmind.modes.evolve`` 顶层包导入：

    .. code-block:: python

        from contextmind.modes.evolve import EvolveEngine
"""

from contextmind.modes.evolve.core.engine import EvolveEngine  # noqa: F401

__all__ = ["EvolveEngine"]
