"""
ContextMind 通用知识库构建模块（contextmind.knowledge）

将任意对话数据集转换为完整的 SGD 格式数据集，供 PyTOD 等执行算法使用。

本模块是**独立模块**，不依赖 ``contextmind`` 内部其他子模块（如
``contextmind.modes.pytod``）。知识提取依赖 ``langextract`` 库实现字符级溯源，
每条提取结果均携带指向原始话语的 ``provenance`` 字段。

整体框架两步走：
    1. **建立知识库**（本模块）：针对任意数据集，通过 LLM + langextract 发现
       槽位和意图，为每条知识附加原文溯源，合成标准 SGD 格式数据集。
    2. **执行**（如 :mod:`contextmind.modes.pytod`）：使用上述 schema.json
       驱动 PyTOD 等对话算法。

核心公开接口::

    from contextmind.knowledge import KnowledgeBaseBuilder

    builder = KnowledgeBaseBuilder(
        scene_name="银行贷款外呼",
        scene_description="银行客服主动致电老客户推介个人贷款产品",
    )

    # 仅生成 schema.json
    schema_dict = builder.build(dialogues)
    builder.save(schema_dict, "output/schema.json")

    # 生成完整 SGD 数据集（schema.json + dialogues_*.json）
    dataset = builder.build_dataset(dialogues)
    builder.save_dataset(dataset, "output/sgd_dataset/")

支持的输入格式（``dialogues`` 参数）：

    1. chat_test 格式（dict，含 ``对话历史`` 字段）::

           {"session_id": "xxx", "对话历史": [{"机器人": "你好", "用户": "你好"}]}

    2. SGD 格式（dict，含 ``turns`` 字段）::

           {"dialogue_id": "xxx", "turns": [{"speaker": "SYSTEM", "utterance": "..."}]}

    3. 简单列表格式（list of str，每项形如 ``"agent: ..."`` 或 ``"user: ..."``）::

           ["agent: 你好，我是客服", "user: 你好"]

    4. 平铺文本格式（单条 str，各轮以换行分隔，每行含说话人前缀）::

           "机器人：你好\\n用户：你好"

.. note::

    旧路径 ``contextmind.kb`` 保留为向后兼容的重定向入口，
    新代码应使用 ``contextmind.knowledge``。
"""

from .builder import KnowledgeBaseBuilder
from .normalizer import normalize_dialogue, normalize_dialogues
from .synthesizer import SchemaSynthesizer
from .discoverer import GenericDialogueDiscoverer, DiscoveryItem

__all__ = [
    # Phase 1：知识库构建
    "KnowledgeBaseBuilder",
    # 归一化
    "normalize_dialogue",
    "normalize_dialogues",
    # 合成器（可单独使用）
    "SchemaSynthesizer",
    # 通用发现器（可单独使用）
    "GenericDialogueDiscoverer",
    "DiscoveryItem",
]
