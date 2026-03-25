"""
scenarios.app — 向后兼容重定向（EvolveApplication 已迁移至 modes.evolve.app）

.. deprecated::
    ``contextmind.scenarios.app.EvolveApplication`` 已迁移至
    ``contextmind.modes.evolve.app.EvolveApplication``。
    此模块保留为向后兼容的重定向入口。

    推荐通过顶层包或新路径导入：

    .. code-block:: python

        # 新路径（推荐）
        from contextmind.modes.evolve.app import EvolveApplication

        # 顶层包（推荐）
        from contextmind.modes.evolve import EvolveApplication

        # 旧路径（仍可用，但已废弃）
        from contextmind.scenarios.app import EvolveApplication
"""

from contextmind.modes.evolve.app import EvolveApplication  # noqa: F401

# 向后兼容别名
ChatApplication = EvolveApplication
CallCenterApplication = EvolveApplication
InsuranceApplication = EvolveApplication

__all__ = [
    "EvolveApplication",
    "ChatApplication",
    "CallCenterApplication",
    "InsuranceApplication",
]
