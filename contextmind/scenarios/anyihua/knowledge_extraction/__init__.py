"""
安逸花外呼 · 知识提取（langextract 溯源版）

以 langextract 作为提取工具，从原始安逸花外呼对话中结构化提取知识，
并通过 langextract WordAligner 将每条知识回溯定位到对话原文的字符区间，
实现端到端的溯源可追踪性。

公开接口::

    from contextmind.scenarios.anyihua.knowledge_extraction import (
        AnyihuaKnowledgeExtractor,
        ExtractionResult,
        KnowledgeItem,
    )
"""

from .extractor import AnyihuaKnowledgeExtractor, ExtractionResult, KnowledgeItem

__all__ = ["AnyihuaKnowledgeExtractor", "ExtractionResult", "KnowledgeItem"]
