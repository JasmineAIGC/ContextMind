"""
contextmind.kb — 向后兼容入口（已迁移至 contextmind.knowledge）

.. deprecated::
    ``contextmind.kb`` 已重命名为 ``contextmind.knowledge``。
    此模块保留为向后兼容的重定向入口，将在未来版本中移除。
    请更新导入语句：

    .. code-block:: python

        # 旧写法（仍可用，但已废弃）
        from contextmind.kb import KnowledgeBaseBuilder

        # 新写法（推荐）
        from contextmind.knowledge import KnowledgeBaseBuilder
"""

import warnings

warnings.warn(
    "contextmind.kb 已迁移至 contextmind.knowledge，"
    "请将 'from contextmind.kb import ...' 更新为 'from contextmind.knowledge import ...'。"
    "contextmind.kb 将在未来版本中移除。",
    DeprecationWarning,
    stacklevel=2,
)

from contextmind.knowledge import (  # noqa: F401, E402
    KnowledgeBaseBuilder,
    normalize_dialogue,
    normalize_dialogues,
    SchemaSynthesizer,
    GenericDialogueDiscoverer,
    DiscoveryItem,
)

__all__ = [
    "KnowledgeBaseBuilder",
    "normalize_dialogue",
    "normalize_dialogues",
    "SchemaSynthesizer",
    "GenericDialogueDiscoverer",
    "DiscoveryItem",
]
