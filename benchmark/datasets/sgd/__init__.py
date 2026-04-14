"""
SGD (Schema-Guided Dialogue) 数据集适配器包

参考: https://github.com/google-research-datasets/dstc8-schema-guided-dialogue
"""

from .adapter import SGDAdapter, SGDDialogueTurn, SGDDialogueInstance, SGDSlot, SGDIntent, SGDServiceSchema

__all__ = [
    "SGDAdapter",
    "SGDDialogueTurn",
    "SGDDialogueInstance",
    "SGDSlot",
    "SGDIntent",
    "SGDServiceSchema",
]
