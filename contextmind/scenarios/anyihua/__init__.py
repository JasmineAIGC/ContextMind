"""
安逸花外呼促活场景 · PyTOD 实现

本场景包含四个独立任务，代码完全隔离：

任务一：离线质检（Label Prediction / QC）
    位置: contextmind/scenarios/anyihua/qc/
    入口: examples/anyihua_qc_demo.py

    使用 PyTOD ExecutionEngine 注册 5 个标签检测 API（对应 5 个质量标签），
    通过纯规则预测或 LLM 辅助分类对坐席回复进行质量标注。

    from contextmind.scenarios.anyihua.qc import (
        build_qc_engine,
        predict_label_pytod,
        classify_session_llm,
        PyTODQualityChecker,
    )

任务二：在线生成（Response Generation）
    位置: contextmind/scenarios/anyihua/generation/
    入口: examples/anyihua_generation_demo.py

    使用 PyTOD ExecutionEngine 注册 CRM 查询 API（query_account 等），
    通过 AdkPyTODAgent（ADK 原生函数调用）三步流程（动作解析器 → 执行引擎 → 对话管理器）
    生成更优质的坐席回复。

    from contextmind.scenarios.anyihua.generation import (
        build_generation_engine,
        ANYIHUA_SCHEMA,
    )

任务三：Schema 提取（Schema Extraction）
    位置: contextmind/scenarios/anyihua/schema_extraction/
    入口: examples/anyihua_schema_extraction_demo.py

    从安逸花外呼对话数据中提取部分字段 SGD Schema，并提供与
    https://github.com/google/langextract 库的互操作接口。
    格式参考 SGD，但允许部分字段缺失（因安逸花数据中字段可能无法提取）。

    from contextmind.scenarios.anyihua.schema_extraction import (
        PartialServiceSchema,
        PartialSlot,
        PartialIntent,
        dialogue_to_langextract_example,
        dialogues_to_langextract_examples,
        schema_from_sgd_file,
        extract_partial_schema_from_dialogue,
    )

任务四：增量精准知识库（Incremental Knowledge Base）
    位置: contextmind/scenarios/anyihua/knowledge_base/
    入口: KnowledgeStore + IncrementalMerger

    将 Schema 提取管线（任务三）产出的 SGD 格式对话增量摄入到结构化
    知识库，提供完整 CRUD 接口，支持精准查询和冲突可溯追踪。

    from contextmind.scenarios.anyihua.knowledge_base import (
        KnowledgeStore,
        IncrementalMerger,
        SlotEvidence, SlotFact, CustomerRecord, ConflictEntry, KBStats,
        MergeReport,
        ConfidenceFirstStrategy, NewerFirstStrategy, ServiceResultFirstStrategy,
    )

共享工具:
    from contextmind.scenarios.anyihua.utils import (
        cn2int, extract_amounts, parse_user_info,
        AGENT_PREFIX, USER_PREFIX, FAREWELL_KEYWORDS,
        USER_CONCERN_WORDS, OFFTOPIC_SIGNALS,
    )
"""

from .utils import cn2int, extract_amounts, parse_user_info
from .qc import build_qc_engine, PyTODQualityChecker, predict_label_pytod, classify_session_llm, ANYIHUA_QC_SCHEMA, ANYIHUA_QC_SCHEMA_DICT
from .generation import build_generation_engine, ANYIHUA_SCHEMA, ANYIHUA_SCHEMA_DICT
from .scenario import get_anyihua_outbound_scenario
try:
    from .schema_extraction import (
        PartialServiceSchema,
        PartialSlot,
        PartialIntent,
        dialogue_to_langextract_example,
        dialogues_to_langextract_examples,
        schema_from_sgd_file,
        extract_partial_schema_from_dialogue,
        induce_schema_with_llm,
        extract_dialogue_info,
        save_schema_as_sgd,
        align_schema_with_sgd,
        format_comparison_report,
    )
    _SCHEMA_EXTRACTION_AVAILABLE = True
except ImportError:
    _SCHEMA_EXTRACTION_AVAILABLE = False
    PartialServiceSchema = None
    PartialSlot = None
    PartialIntent = None
    dialogue_to_langextract_example = None
    dialogues_to_langextract_examples = None
    schema_from_sgd_file = None
    extract_partial_schema_from_dialogue = None
    induce_schema_with_llm = None
    extract_dialogue_info = None
    save_schema_as_sgd = None
    align_schema_with_sgd = None
    format_comparison_report = None
try:
    from .knowledge_base import (
        KnowledgeStore,
        IncrementalMerger,
        MergeReport,
        SlotEvidence,
        SlotFact,
        CustomerRecord,
        ConflictEntry,
        KBStats,
        ConfidenceFirstStrategy,
        NewerFirstStrategy,
        ServiceResultFirstStrategy,
    )
    _KNOWLEDGE_BASE_AVAILABLE = True
except ImportError:
    _KNOWLEDGE_BASE_AVAILABLE = False
    KnowledgeStore = None
    IncrementalMerger = None
    MergeReport = None
    SlotEvidence = None
    SlotFact = None
    CustomerRecord = None
    ConflictEntry = None
    KBStats = None
    ConfidenceFirstStrategy = None
    NewerFirstStrategy = None
    ServiceResultFirstStrategy = None

__all__ = [
    # 共享工具
    "cn2int",
    "extract_amounts",
    "parse_user_info",
    # 任务一：QC
    "build_qc_engine",
    "predict_label_pytod",
    "classify_session_llm",
    "PyTODQualityChecker",
    "ANYIHUA_QC_SCHEMA",
    "ANYIHUA_QC_SCHEMA_DICT",
    # 任务二：Generation
    "build_generation_engine",
    "ANYIHUA_SCHEMA",
    "ANYIHUA_SCHEMA_DICT",
    # 任务三：Schema Extraction
    "PartialServiceSchema",
    "PartialSlot",
    "PartialIntent",
    "dialogue_to_langextract_example",
    "dialogues_to_langextract_examples",
    "schema_from_sgd_file",
    "extract_partial_schema_from_dialogue",
    "induce_schema_with_llm",
    "extract_dialogue_info",
    "save_schema_as_sgd",
    "align_schema_with_sgd",
    "format_comparison_report",
    # 任务四：Incremental Knowledge Base
    "KnowledgeStore",
    "IncrementalMerger",
    "MergeReport",
    "SlotEvidence",
    "SlotFact",
    "CustomerRecord",
    "ConflictEntry",
    "KBStats",
    "ConfidenceFirstStrategy",
    "NewerFirstStrategy",
    "ServiceResultFirstStrategy",
    # 对话场景配置
    "get_anyihua_outbound_scenario",
]
