"""
安逸花外呼 · 知识提取（单轮对话 + langextract 溯源版）+ SGD 格式转换

以 langextract 作为提取工具，从原始安逸花外呼多轮对话中结构化提取知识。
每轮对话单独作为 langextract 的文本输入，通过 WordAligner 实现轮级字符区间溯源。
提取结果可进一步转换为 SGD（Schema-Guided Dialogue）格式，用于任务型对话评测。

公开接口::

    from contextmind.scenarios.anyihua.knowledge_extraction import (
        AnyihuaKnowledgeExtractor,
        ExtractionResult,
        ExtractionSchema,
        SlotDefinition,
        IntentDefinition,
        DEFAULT_SCHEMA,
        STATS_FIELD_DESCRIPTIONS,
        KnowledgeItem,
        ValueUpdate,
        extract_knowledge_with_provenance,
        save_results,
        to_sgd_dialogue,
        save_as_sgd,
    )

    # 官方 lx.extract(model=...) 模式（含历史上下文 + 跨轮去重）
    from contextmind.scenarios.anyihua.knowledge_extraction import (
        SimpleLLMClientAdapter,
        build_langextract_schema_prompt,
        build_langextract_examples,
        extract_with_per_turn_annotator,
    )
"""

from .extractor import (
    AnyihuaKnowledgeExtractor,
    DEFAULT_SCHEMA,
    ExtractionResult,
    ExtractionSchema,
    IntentDefinition,
    KnowledgeItem,
    SlotDefinition,
    STATS_FIELD_DESCRIPTIONS,
    ValueUpdate,
    extract_knowledge_with_provenance,
    save_results,
)
from .langextract_bridge import (
    SimpleLLMClientAdapter,
    build_langextract_examples,
    build_langextract_schema_prompt,
    extract_with_per_turn_annotator,
)
from .sgd_converter import (
    save_as_sgd,
    to_sgd_dialogue,
)

__all__ = [
    "AnyihuaKnowledgeExtractor",
    "DEFAULT_SCHEMA",
    "ExtractionResult",
    "ExtractionSchema",
    "IntentDefinition",
    "KnowledgeItem",
    "SlotDefinition",
    "STATS_FIELD_DESCRIPTIONS",
    "ValueUpdate",
    "extract_knowledge_with_provenance",
    "save_results",
    "to_sgd_dialogue",
    "save_as_sgd",
    # langextract 深度集成（官方 lx.extract(model=...) 模式）
    "SimpleLLMClientAdapter",
    "build_langextract_examples",
    "build_langextract_schema_prompt",
    "extract_with_per_turn_annotator",
]
