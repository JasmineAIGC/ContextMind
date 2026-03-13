"""
安逸花（AnyiHua）数据集适配器

将 resources/data/chat_test_100.json 中的安逸花外呼对话和
data/anyihua_sgd/schema.json 中的 SGD 格式 schema 适配为
PyTOD 评测所需的标准结构。
"""

from .adapter import AnyihuaSGDAdapter, AnyihuaDialogue, AnyihuaTurn

__all__ = [
    "AnyihuaSGDAdapter",
    "AnyihuaDialogue",
    "AnyihuaTurn",
]
