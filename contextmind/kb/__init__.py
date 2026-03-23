"""
ContextMind Knowledge Base (KB) — 通用知识库构建模块

将任意对话数据集转换为 SGD 格式 schema.json，供 PyTOD 等执行算法使用。

整体框架两步走：
    1. **建立知识库**（本模块）：针对任意数据集，通过 LLM 发现槽位和意图，
       合成标准 SGD 格式 ``schema.json``。
    2. **执行**（如 :mod:`contextmind.modes.pytod`）：使用上述 ``schema.json``
       驱动 PyTOD 等对话算法。

核心公开接口::

    from contextmind.kb import KnowledgeBaseBuilder

    builder = KnowledgeBaseBuilder(
        scene_name="银行贷款外呼",
        scene_description="银行客服主动致电老客户推介个人贷款产品",
    )
    schema_dict = builder.build(dialogues)   # 返回 SGD 格式 schema dict
    builder.save(schema_dict, "output/schema.json")

支持的输入格式（``dialogues`` 参数）：

    1. chat_test 格式（dict，含 ``对话历史`` 字段）::

           {"session_id": "xxx", "对话历史": ["坐席：你好", "用户：你好"]}

    2. SGD 格式（dict，含 ``turns`` 字段）::

           {"dialogue_id": "xxx", "turns": [{"speaker": "SYSTEM", "utterance": "..."}]}

    3. 简单列表格式（list of str，每项形如 ``"agent: ..."`` 或 ``"user: ..."``）::

           ["agent: 你好，我是客服", "user: 你好"]

    4. 平铺文本格式（单条 str，各轮以换行分隔，每行含说话人前缀）::

           "坐席：你好\\n用户：你好"
"""

from .builder import KnowledgeBaseBuilder
from .normalizer import normalize_dialogue, normalize_dialogues
from .synthesizer import SchemaSynthesizer

__all__ = [
    "KnowledgeBaseBuilder",
    "normalize_dialogue",
    "normalize_dialogues",
    "SchemaSynthesizer",
]
