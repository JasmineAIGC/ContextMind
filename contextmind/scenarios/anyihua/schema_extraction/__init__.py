"""
安逸花外呼 · 任务三：Schema 提取（Schema Extraction）

从安逸花外呼对话数据中提取部分字段 SGD Schema，
并提供与 https://github.com/google/langextract 库的互操作接口。

设计说明:
    · 格式参考 SGD（Schema-Guided Dialogue），但允许部分字段缺失：
      PartialSlot / PartialIntent / PartialServiceSchema 的非核心字段均为可选。
    · 提供 to_langextract_* 系列接口，可将标注对话转换为 langextract
      ExampleData-兼容字典列表，直接传入 lx.extract()。

主要组件:
    schema.py    — PartialSlot / PartialIntent / PartialServiceSchema
    extractor.py — dialogue_to_langextract_example / dialogues_to_langextract_examples
                   schema_from_sgd_file / extract_partial_schema_from_dialogue

典型使用（无需安装 langextract）::

    from contextmind.scenarios.anyihua.schema_extraction import (
        PartialServiceSchema,
        PartialSlot,
        PartialIntent,
        dialogue_to_langextract_example,
        dialogues_to_langextract_examples,
        schema_from_sgd_file,
        extract_partial_schema_from_dialogue,
    )

典型使用（安装 langextract 后）::

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

from .extractor import (
    dialogue_to_langextract_example,
    dialogues_to_langextract_examples,
    extract_partial_schema_from_dialogue,
    schema_from_sgd_file,
)
from .schema import PartialIntent, PartialServiceSchema, PartialSlot

__all__ = [
    # Schema 数据类
    "PartialSlot",
    "PartialIntent",
    "PartialServiceSchema",
    # 转换工具
    "dialogue_to_langextract_example",
    "dialogues_to_langextract_examples",
    "schema_from_sgd_file",
    "extract_partial_schema_from_dialogue",
]
