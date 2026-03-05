"""
安逸花外呼数据集 SGD 转换包

将 resources/data/chat_test_100.json 转换为 Google SGD 格式，
以适配 PyTOD 算法的训练和评估流程。
"""

from .adapter import ChatTestToSGDConverter

__all__ = ["ChatTestToSGDConverter"]
