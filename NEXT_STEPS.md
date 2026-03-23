# 安逸花外呼 · 知识提取后续任务规划

> **当前进度（Phase 1 已完成）**
>
> 知识提取闭环已可以稳定运行：`AnyihuaKnowledgeExtractor` → SGD 转换 → `IncrementalMerger` → `KnowledgeStore`（含跨轮去重、幂等摄入、Confidence-First 冲突消解）。
> 本文档基于 `guide.md` 梳理后续需要完成的事项。

---

## 一、任务总览

| # | 任务 | 所属阶段 | 优先级 | 估算工作量 |
|---|------|----------|--------|------------|
| T1 | 槽位值合法性校验层（Validator） | Phase 2 | 🔴 高 | 1–2 天 |
| T2 | 对齐质量分层过滤与待审队列 | Phase 2 | 🔴 高 | 1 天 |
| T3 | 知识库覆盖率报告脚本 | Phase 2 | 🟡 中 | 1 天 |
| T4 | 新增冲突消解策略（Timestamp / Voting） | Phase 2 | 🟡 中 | 1–2 天 |
| T5 | 冲突统计报告与审计导出 | Phase 2 | 🟡 中 | 1 天 |
| T6 | 知识库版本快照与增量摄入元数据日志 | Phase 2 | 🟡 中 | 1 天 |
| T7 | SlotFact TTL 降权（知识老化） | Phase 2 | 🟢 低 | 1 天 |
| T8 | 黄金标准数据集 + Precision/Recall 评测 | Phase 2 | 🔴 高 | 2–3 天 |
| T9 | 跨 session 一致性检测 | Phase 2 | 🟡 中 | 1 天 |
| T10 | 知识库查询 REST 接口（轻量服务化） | Phase 3 | 🟡 中 | 2 天 |
| T11 | PyTOD 风格知识辅助对话 demo | Phase 3 | 🟡 中 | 2–3 天 |

---

## 二、各任务详细说明

---

### T1 — 槽位值合法性校验层（Validator）

**背景**

LLM 偶尔会生成格式异常的槽位值（如把金额写成"五万多"而非数字、把姓名写成坐席话术片段）。
这些值在进入 `KnowledgeStore` 之前应被拦截，避免污染知识库。

**开展方式**

1. 在 `contextmind/scenarios/anyihua/knowledge_base/` 下新建 `validator.py`，定义 `SlotValidator` 类。
2. 每个槽位对应一条校验规则（正则或范围检查），规则表配置在类常量里，方便扩展。
3. 在 `IncrementalMerger.merge_single_dialogue` 调用 `store.upsert_slot_evidence` 之前，先过滤不合规的 `SlotEvidence`。

**关键规则（初始版本）**

| 槽位名 | 校验规则 |
|--------|----------|
| `customer_name` | 2–4 个汉字，不含数字 |
| `phone_suffix` | 3–4 位纯数字 |
| `available_credit` | 可解析为 float，范围 0–500000 |
| `annual_rate_pct` | 可解析为 float，范围 0–100 |
| `identity_confirmed` | 枚举：`true` / `false` |
| `loan_count` | 可解析为正整数 |

**交付物**

- `contextmind/scenarios/anyihua/knowledge_base/validator.py`
- 集成到 `IncrementalMerger`（`merge_single_dialogue` 中增加校验调用）
- 单元测试：`tests/scenarios/anyihua/test_validator.py`（覆盖合规和违规各类槽位）
- `MergeReport` 新增字段 `validation_rejected`（被校验拦截的槽位条数）

---

### T2 — 对齐质量分层过滤与待审队列

**背景**

`langextract` 已在 `SlotEvidence.alignment_status` 中提供四级对齐质量信号：
`match_exact`（1.0）/ `match_lesser`（0.85）/ `match_fuzzy`（0.70）/ `None`（0.50）。
目前所有结果不加区分地进入知识库，应建立分层策略。

**开展方式**

1. 在 `IncrementalMerger` 中根据 `confidence` 阈值分三档处理：
   - `>= 0.85`：直接写入知识库（`upsert_slot_evidence`）
   - `0.70–0.85`：写入知识库但在 `SlotFact` 上打 `needs_review=True` 标记
   - `< 0.70`：写入待审 JSON 文件（rejection log），不进主库
2. 在 `SlotFact`（`schema.py`）上增加 `needs_review: bool = False` 字段。
3. `KnowledgeStore` 新增 `list_pending_review()` 方法，返回所有待复核的 `(customer_id, slot_name)` 列表。

**交付物**

- `schema.py` 中 `SlotFact` 新增 `needs_review` 字段
- `merger.py` 中分层写入逻辑
- `store.py` 中 `list_pending_review()` 方法
- 待审日志路径：`resources/anyihua_kb/pending_review_<timestamp>.jsonl`
- 集成测试：验证三档阈值的分流行为

---

### T3 — 知识库覆盖率报告脚本

**背景**

需要定期评估知识库的整体健康度：哪些槽位被频繁提取、哪些几乎为空（可能是 prompt 引导不足或业务上本就少见）。

**开展方式**

1. 新建脚本 `examples/anyihua_kb_coverage_report.py`（离线，无需 LLM）。
2. 加载 `KnowledgeStore`，遍历所有 `CustomerRecord`，按槽位统计：
   - `filled_count`：有该槽位值的客户数
   - `total_customers`：客户总数
   - `fill_rate`：`filled_count / total_customers`
   - `avg_confidence`：该槽位所有 `SlotEvidence.confidence` 的均值
3. 输出 Markdown 表格到 stdout，同时写 JSON 到指定路径。

**交付物**

- `examples/anyihua_kb_coverage_report.py`
- 示例输出格式：

```
| 槽位名           | 填充率  | 平均置信度 | 客户数 |
|-----------------|--------|-----------|--------|
| customer_name   | 98.2%  | 0.97      | 1250   |
| available_credit| 76.4%  | 0.88      | 955    |
| annual_rate_pct | 45.1%  | 0.82      | 564    |
...
```

---

### T4 — 新增冲突消解策略（Timestamp First / Frequency Voting）

**背景**

`guide.md` 第 4.2 节指出，现有的 `ConfidenceFirstStrategy` 只适合置信度差距明显的场景，需要补充两种策略。`ConflictStrategy` 协议接口已在 `merger.py` 中定义。

**开展方式**

**T4a — TimestampFirstStrategy**

在 `merger.py` 中新增类，`resolve` 方法比较 `existing.extracted_at` 与 `new.extracted_at`，时间更新的证据优先。相同时间戳时回退到 Confidence First。

**T4b — FrequencyVotingStrategy**

需要在 `SlotFact` 上维护 `value_counts: Dict[str, int]`（历史所有出现值及其次数）。
`resolve` 方法更新 `value_counts` 后，将 `current_evidence.value` 设为出现次数最多的值。

**交付物**

- `merger.py` 中 `TimestampFirstStrategy` 和 `FrequencyVotingStrategy` 两个新类
- `schema.py` 中 `SlotFact` 新增 `value_counts` 字段（FrequencyVoting 需要）
- `IncrementalMerger.__init__` 支持通过 `strategy` 参数选择策略
- 单元测试：覆盖三种策略在值相同 / 置信度相近 / 时间戳不同场景下的行为
- `examples/anyihua_knowledge_extraction_demo.py` CLI 新增 `--conflict-strategy` 参数

---

### T5 — 冲突统计报告与审计导出

**背景**

`KnowledgeStore` 的每个 `SlotFact.conflict_history` 已保存 `ConflictEntry`，但目前没有汇总统计途径。冲突率高的槽位往往是数据噪声的集中反映。

**开展方式**

1. 在 `KnowledgeStore` 上新增 `conflict_report()` 方法，按 `slot_name` 聚合：
   - `total_conflicts`：冲突总次数
   - `conflict_rate`：冲突次数 / 总更新次数
   - `auto_resolved`：自动消解数
   - `unresolved`：`resolution="keep_both"` 的数量（需人工干预）
2. 新建 `examples/anyihua_kb_conflict_report.py` 脚本，加载知识库后输出报告。
3. 导出未解决冲突为 `pending_conflicts_<timestamp>.jsonl`，供人工标注后回写。

**交付物**

- `store.py` 中 `conflict_report()` 方法
- `examples/anyihua_kb_conflict_report.py`
- 未解决冲突导出功能（`store.export_unresolved_conflicts(path)`）

---

### T6 — 知识库版本快照与增量摄入元数据日志

**背景**

每次增量摄入后需要留存快照，支持版本对比和回滚；摄入元数据（处理了多少条 session、新增了多少槽位）应作为可观测信号保存。

**开展方式**

1. 在 `IncrementalMerger.merge_dialogues` 返回前，调用 `store.save_to_json(versioned_path)`，路径格式：`<base_dir>/kb_v<版本号>_<日期>.json`，同时更新 `kb_latest.json` 软指针（JSON 文件，内含最新路径）。
2. `MergeReport` 增加字段：`merge_timestamp`、`new_slot_facts`、`updated_slot_facts`，序列化后追加到 `merge_log.jsonl`。

**交付物**

- `merger.py` 中版本化保存逻辑
- `MergeReport` 新增字段及 `to_dict()` 序列化
- `merge_log.jsonl` 写入逻辑
- `examples/anyihua_kb_merge_history.py`：读取 `merge_log.jsonl` 并打印历次摄入统计

---

### T7 — SlotFact TTL 降权（知识老化）

**背景**

安逸花的客户额度、利率信息随时间变化，6 个月前的外呼数据可能已不准确。知识库应能反映"这条知识有多新鲜"。

**开展方式**

1. `KnowledgeStore.get_slot_value` 改为返回 `SlotFactView`（含 `value`、`confidence`、`is_stale`），而非裸字符串（向后兼容：提供 `.value` 属性）。
2. 新增 `KnowledgeStore.apply_ttl_decay(ttl_days: int = 180, decay_factor: float = 0.9)` 方法：对 `updated_at` 超过 `ttl_days` 的 `SlotFact`，将其 `current_evidence.confidence` 乘以 `decay_factor`，并打 `is_stale=True` 标记。
3. 覆盖率报告（T3）中新增"过期槽位"统计列。

**交付物**

- `schema.py` 中 `SlotFact.is_stale` 字段
- `store.py` 中 `apply_ttl_decay()` 方法
- T3 覆盖率报告新增 `stale_count` 列

---

### T8 — 黄金标准数据集 + Precision/Recall 评测

**背景**

自动统计无法替代真实质量评估。需要人工标注一批对话的正确槽位值，作为 ground truth 来测量提取精度。

**开展方式**

**步骤一：标注黄金集（人工，约 1 天）**

从 `chat_test_100.json` 中随机抽取 30–50 条对话，人工填写每条对话应产出的正确槽位值，保存为：

```jsonl
{"session_id": "xxx", "slot_values": {"customer_name": "高先生", "available_credit": "21000", ...}}
```

路径：`resources/anyihua_gold/gold_annotations.jsonl`

**步骤二：自动评测脚本**

新建 `examples/anyihua_kb_eval.py`，流程：
1. 加载黄金集
2. 对每条对话运行 `AnyihuaKnowledgeExtractor.extract()`
3. 将结果与黄金集对比，按槽位计算：
   - `Precision`：正确提取数 / 实际提取数
   - `Recall`：正确提取数 / 黄金集总数
   - `F1`
4. 输出按槽位分类的评测表格，并列出 bad case（提取错误的具体条目）

**交付物**

- `resources/anyihua_gold/gold_annotations.jsonl`（人工标注，30–50 条）
- `examples/anyihua_kb_eval.py`（自动评测脚本）
- 首次评测结果报告（Markdown 表格，存入 `resources/anyihua_gold/eval_report_v1.md`）

---

### T9 — 跨 session 一致性检测

**背景**

同一客户在不同通话中，相同槽位应保持稳定或有规律变化。若同一 `(customer_id, slot_name)` 的历史值高度分散，说明提取存在系统性错误。

**开展方式**

1. 在 `KnowledgeStore` 新增 `consistency_report()` 方法：
   - 对每个 `(customer_id, slot_name)` 收集所有历史 `SlotEvidence.value`
   - 若同一槽位出现 3 种以上不同值，标记为"不稳定"
   - 输出：不稳定槽位列表、不稳定率（不稳定槽位数 / 总槽位数）
2. 在 T3 覆盖率报告中新增"不稳定槽位"排行列。

**交付物**

- `store.py` 中 `consistency_report()` 方法
- T3 覆盖率报告集成（`--check-consistency` 参数）

---

### T10 — 知识库查询 REST 接口（轻量服务化）

**背景**

Phase 3 目标：让知识库"可检索、可调用"。先实现一个轻量 FastAPI 服务，对外暴露查询接口。

**开展方式**

1. 新建 `contextmind/scenarios/anyihua/knowledge_base/server.py`，使用 FastAPI 定义以下接口：

```
GET  /customer/{customer_id}                     → CustomerRecord（JSON）
GET  /customer/{customer_id}/slot/{slot_name}    → SlotFact（JSON）
GET  /query?slot_name=xxx&value=yyy              → [customer_id, ...]
GET  /stats                                       → KBStats（JSON）
GET  /health                                      → {"status": "ok"}
```

2. 服务启动时从指定 JSON 路径加载 `KnowledgeStore`（只读模式），支持 `--kb-path` 参数。
3. 新建 `examples/anyihua_kb_server.py` 作为启动入口。

**交付物**

- `contextmind/scenarios/anyihua/knowledge_base/server.py`（FastAPI 路由定义）
- `examples/anyihua_kb_server.py`（服务启动脚本）
- `README` 或 docstring 中的 API 使用示例（curl 命令）
- 依赖：`fastapi`、`uvicorn`（加入 `requirements.txt`）

---

### T11 — PyTOD 风格知识辅助对话 demo

**背景**

Phase 3 终极目标：把知识库接入现有的 PyTOD 对话管道，让坐席生成模块能在回复时参考客户的历史槽位值（如可用额度、身份状态），提升回复的准确性和个性化程度。

**开展方式**

1. 在 `contextmind/scenarios/anyihua/generation/` 下扩展 `build_generation_engine()`：
   - 增加 `get_kb_slot(customer_id, slot_name)` API，内部调用 `KnowledgeStore.get_slot_value`
   - 在 CRM 数据查询 API 中优先使用知识库值（若知识库有值且置信度 >= 0.85），否则 fallback 到原始 CRM 数据
2. 修改 `PyTODPromptBuilder` 的 system prompt，引入知识库查询结果作为上下文片段（"根据历史通话记录，该客户可用额度为 2.1 万元"）。
3. 新建 Gradio demo `examples/anyihua_kb_generation_demo.py`，演示：
   - 选择一条新对话（模拟实时外呼）
   - 从知识库中拉取该客户的历史槽位值
   - PyTOD 三步流程（解析 → 执行 → 生成），生成结果与无知识库版本对比

**交付物**

- `generation/` 中知识库集成代码（`get_kb_slot` API）
- `examples/anyihua_kb_generation_demo.py`（Gradio web demo）
- demo 截图（存入 `resources/screenshots/`）

---

## 三、执行顺序建议

```
Week 1（质量基础）:
    T1（Validator）→ T2（分层过滤）→ T3（覆盖率报告）

Week 2（评测与冲突）:
    T8（黄金集 + 评测）→ T4（新策略）→ T5（冲突报告）

Week 3（可维护性）:
    T6（版本快照）→ T7（TTL 降权）→ T9（一致性检测）

Week 4（业务落地）:
    T10（REST 服务）→ T11（PyTOD demo）
```

---

## 四、交付检查清单

- [ ] T1: `validator.py` + 集成 + 测试
- [ ] T2: 分层过滤 + `list_pending_review()` + rejection log
- [ ] T3: `anyihua_kb_coverage_report.py`（含 Markdown 输出）
- [ ] T4a: `TimestampFirstStrategy` + 测试
- [ ] T4b: `FrequencyVotingStrategy` + `value_counts` 字段 + 测试
- [ ] T5: `conflict_report()` + 未解决冲突导出 + 报告脚本
- [ ] T6: 版本化保存 + `merge_log.jsonl` + 历史查看脚本
- [ ] T7: `apply_ttl_decay()` + `is_stale` 字段
- [ ] T8: 黄金集标注 + 评测脚本 + 首次评测报告
- [ ] T9: `consistency_report()` + 覆盖率报告集成
- [ ] T10: FastAPI 服务 + 启动脚本 + curl 示例
- [ ] T11: Gradio demo + 截图
