"""
安逸花外呼 · 任务三：Schema 提取（Schema Extraction）

从安逸花外呼对话数据中提取部分字段 SGD Schema，
并提供与 https://github.com/google/langextract 库的互操作接口。

设计说明:
    · 格式参考 SGD（Schema-Guided Dialogue），但允许部分字段缺失：
      PartialSlot / PartialIntent / PartialServiceSchema 的非核心字段均为可选。
    · 提供 to_langextract_* 系列接口，可将标注对话转换为 langextract
      ExampleData 列表，直接传入 lx.extract()。
    · 3 步管道（pipeline.py）直接使用 langextract.data 与 langextract.resolver，
      每个意图/槽位提取结果通过 WordAligner 溯源到对话原文的字符区间。

主要组件:
    schema.py    — PartialSlot / PartialIntent / PartialServiceSchema
    extractor.py — dialogue_to_langextract_example / dialogues_to_langextract_examples
                   schema_from_sgd_file / extract_partial_schema_from_dialogue
    pipeline.py  — 3 步 SGD 管道（discover_schema_step1 / merge_schemas_step2 /
                   build_sgd_dialogue_step3 / run_pipeline）

典型使用（3 步管道）::

    import langextract as lx
    from pathlib import Path
    from contextmind.infra.llm_client import AdkLLMClient
    from contextmind.scenarios.anyihua.schema_extraction import run_pipeline

    llm = AdkLLMClient()
    summary = run_pipeline(
        input_path=Path("resources/data/chat_test_100.json"),
        predefined_schema_path=Path("resources/anyihua_sgd/schema.json"),
        output_dir=Path("data/anyihua_sgd_pipeline"),
        llm_client=llm,
    )

典型使用（langextract 与现有标注数据互操作）::

    import langextract as lx
    from contextmind.scenarios.anyihua.schema_extraction import (
        dialogues_to_langextract_examples,
        schema_from_sgd_file,
    )

    schema = schema_from_sgd_file(Path("resources/anyihua_sgd/schema.json"))
    examples_dicts = dialogues_to_langextract_examples(dialogues, schema)

    lx_examples = [
        lx.data.ExampleData(
            text=ex["text"],
            extractions=[
                lx.data.Extraction(
                    extraction_class=e["extraction_class"],
                    extraction_text=e["extraction_text"],
                    attributes=e.get("attributes"),
                )
                for e in ex["extractions"]
            ],
        )
        for ex in examples_dicts
    ]
    result = lx.extract(
        text_or_documents="<新对话文本>",
        prompt_description="从安逸花外呼对话中提取槽位值和意图",
        examples=lx_examples,
        model_id="gemini-2.5-flash",
    )
"""

from langextract.data import AlignmentStatus

from .data_cleaner import clean_dialogues, CleanConfig, CleanReport
from .extractor import (
    dialogue_to_langextract_example,
    dialogues_to_langextract_examples,
    extract_partial_schema_from_dialogue,
    schema_from_sgd_file,
)
from .llm_induction import extract_dialogue_info, induce_schema_with_llm
from .pipeline import (
    MATCH_EXACT,
    MATCH_FUZZY,
    MATCH_LESSER,
    build_sgd_dialogue_step3,
    discover_schema_step1,
    merge_schemas_step2,
    run_pipeline,
)
from .schema import PartialIntent, PartialServiceSchema, PartialSlot
from .schema_io import (
    align_schema_with_sgd,
    format_comparison_report,
    save_schema_as_sgd,
)

__all__ = [
    # Schema 数据类
    "PartialSlot",
    "PartialIntent",
    "PartialServiceSchema",
    # 转换工具（规则 / 标注数据）
    "dialogue_to_langextract_example",
    "dialogues_to_langextract_examples",
    "schema_from_sgd_file",
    "extract_partial_schema_from_dialogue",
    # LLM 驱动的 Schema 归纳与信息提取
    "induce_schema_with_llm",
    "extract_dialogue_info",
    # 3 步管道（docs/analysis/dialogue-to-knowledge-pipeline.md）
    "discover_schema_step1",
    "merge_schemas_step2",
    "build_sgd_dialogue_step3",
    "run_pipeline",
    # langextract 对齐状态（直接使用 langextract.data.AlignmentStatus 枚举）
    "AlignmentStatus",
    # 向后兼容别名（与旧版 MATCH_* 字符串常量兼容）
    "MATCH_EXACT",
    "MATCH_LESSER",
    "MATCH_FUZZY",
    # 1.1 数据清洗（data_cleaner.py）
    "clean_dialogues",
    "CleanConfig",
    "CleanReport",
    # Schema 持久化与格式对比
    "save_schema_as_sgd",
    "align_schema_with_sgd",
    "format_comparison_report",
]
