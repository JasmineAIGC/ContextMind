"""
安逸花外呼 · 增量精准知识库

从安逸花外呼对话（SGD 格式）中提取、存储和查询结构化客户知识的完整解决方案。

架构概述（对应问题陈述中的数据流转图）：

    [历史对话数据流 / 当前实时对话]
             │
             ▼  增量摄入（IncrementalMerger.merge_dialogues）
    ┌──────────────────────┐
    │  KnowledgeStore      │  ← CRUD API（get/update/delete/query）
    │  （内存 + JSON 持久化）│
    └──────────────────────┘
             │
             ▼  读取（KnowledgeStore.get_customer / query_by_slot）
    [对话任务应用管线（意图识别 / 检索 / 上下文组装）]

知识库设计原则：
    · 精准 (Precise)：   每条知识携带完整溯源信息（session_id / char_interval）
    · 可解释 (Explainable)：SlotFact / ConflictEntry 均有明确的语义字段
    · 增量更新 (Incremental)：新批次对话只追加/覆盖，不清空历史
    · 冲突可溯 (Conflict-traceable)：ConflictEntry 记录所有冲突及消解结果
    · 数据可扩展 (Extensible)：customer_id_fn 参数允许接入其他数据源

典型使用::

    import json
    from pathlib import Path
    from contextmind.scenarios.anyihua.knowledge_base import (
        KnowledgeStore,
        IncrementalMerger,
    )

    # 初始化
    store = KnowledgeStore()
    merger = IncrementalMerger()

    # 从 SGD 管道产出的对话批量摄入
    dialogues = json.loads(
        Path("resources/anyihua_sgd/dialogues_001.json").read_text()
    )
    report = merger.merge_dialogues(store, dialogues)
    print(report)
    # → MergeReport(processed=100, skipped=0, slots_written=312, ...)

    # CRUD 查询
    record = store.get_customer("高先生::六七八")
    print(record.get_slot_value("available_credit"))  # "9999.99"
    print(record.list_known_slots())

    # 按槽位值查找客户
    results = store.query_by_slot("identity_confirmed", "true")
    print(len(results), "客户身份已核实")

    # 持久化
    store.save_to_json(Path("data/anyihua_kb.json"))
    store2 = KnowledgeStore.load_from_json(Path("data/anyihua_kb.json"))

    # 统计
    stats = store.get_stats()
    print(stats)
    # → KBStats(customers=87, sessions=100, facts=312, ...)
"""

from .merger import (
    ConfidenceFirstStrategy,
    ConflictStrategy,
    IncrementalMerger,
    MergeReport,
    NewerFirstStrategy,
    ServiceResultFirstStrategy,
)
from .schema import (
    ConflictEntry,
    CustomerRecord,
    KBStats,
    SlotEvidence,
    SlotFact,
)
from .store import KnowledgeStore, _default_customer_id_fn

__all__ = [
    # 数据模型
    "SlotEvidence",
    "SlotFact",
    "CustomerRecord",
    "ConflictEntry",
    "KBStats",
    # 存储层（CRUD）
    "KnowledgeStore",
    "_default_customer_id_fn",
    # 增量合并
    "IncrementalMerger",
    "MergeReport",
    # 冲突消解策略
    "ConflictStrategy",
    "ConfidenceFirstStrategy",
    "NewerFirstStrategy",
    "ServiceResultFirstStrategy",
]
