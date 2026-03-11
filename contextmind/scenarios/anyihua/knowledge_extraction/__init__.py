"""
安逸花外呼 · 知识提取（单轮对话 + langextract 溯源版）

以 langextract 作为提取工具，从原始安逸花外呼多轮对话中结构化提取知识。
每轮对话单独作为 langextract 的文本输入，通过 WordAligner 实现轮级字符区间溯源。

公开接口::

    from contextmind.scenarios.anyihua.knowledge_extraction import (
        AnyihuaKnowledgeExtractor,
        ExtractionResult,
        KnowledgeItem,
        extract_knowledge_with_provenance,
        save_results,
    )
"""

from .extractor import (
    AnyihuaKnowledgeExtractor,
    ExtractionResult,
    KnowledgeItem,
    extract_knowledge_with_provenance,
    save_results,
)

__all__ = [
    "AnyihuaKnowledgeExtractor",
    "ExtractionResult",
    "KnowledgeItem",
    "extract_knowledge_with_provenance",
    "save_results",
]
