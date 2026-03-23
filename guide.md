# doc

|  | 核心职责 |
| --- | --- |
| **@负责人** | 负责规则设计、质量把控、应用方案 |
| **@实习生** | 负责数据处理、工程实现、评测执行 |

# 一、任务与分工列表

| 任务 | 简单解释 | @负责人 | @实习生 |
| --- | --- | --- | --- |
| **知识 schema 设计** | 定义知识库的统一表示，参考 SGD，明确 domain / intent / slot / value 和扩展字段 | 定义整体 schema 和业务字段范围 | 将 schema 落成配置或数据结构 |
| **原始数据治理与标准化** | 将 4 万条原始对话清洗成统一输入格式，支持后续抽取 | 定义清洗标准和保留规则 | 实现数据清洗、格式统一、session/turn 切分 |
| **抽取 pipeline 设计与实现** | 基于 langextract 完成知识抽取流程，支持批处理 | 设计抽取规则与输入模板 | 封装 langextract，完成批处理与异常处理 |
| **SGD 格式映射与结构化存储** | 将抽取结果转换成 SGD-compatible 格式并存储 | 定义映射规则 | 实现映射逻辑与结果落库 |
| **知识质量控制与评测** | 评估抽取质量，验证结果是否准确可用 | 定义评测指标与审核标准 | 执行评测并整理 bad case |
| **知识去重、冲突处理与更新机制** | 处理重复、冲突知识，并支持增量更新 | 定义去重、冲突、更新规则 | 实现 dedup / update 逻辑 |
| **知识库索引、查询与服务化** | 让知识库可检索、可调用，支撑业务使用 | 定义查询接口需求 | 实现索引、查询接口和轻量服务化 |
| **PyTOD 风格应用落地** | 将知识库接入对话流程，用于状态表示和知识辅助决策 | 设计应用方案和 demo 场景 | 实现 demo 基础模块并跑通闭环 |

# 二、整体流程

```Plain
原始业务对话
    ↓
原始数据治理与标准化
    ↓
知识 schema 设计
    ↓
抽取 pipeline 设计与实现
    ↓
SGD 格式映射与结构化存储
    ↓
知识质量控制与评测
    ↓
知识去重、冲突处理与更新机制
    ↓
知识库索引、查询与服务化
    ↓
PyTOD 风格应用落地
```

# 三、阶段任务

| 阶段 | 任务 | 重点 | 交付&评价 |
| --- | --- | --- | --- |
| Phase 1/**知识构建** | schema、数据治理、抽取、映射存储 | 跑通知识抽取闭环 | 能稳定产出 SGD-compatible 结构化结果 |
| Phase 2/**质量与更新** | 质量评测、去重冲突、更新机制 | 提升准确性和可维护性 | 形成知识库 v2，并具备增量更新能力 |
| Phase 3/**业务落地** | 索引查询服务、PyTOD 落地 | 接入业务使用 | 至少一个业务 demo 跑通 |

---

# 四、Phase 2 深度分析

## 4.1 知识质量控制与评测

### 思考角度

**角度一：抽取准确性（Extraction Precision）**

核心问题：LLM 从对话中抽取的槽位值是否正确？需要区分两类错误：
- **幻觉值**：LLM 抽取了对话中根本没有的内容（如凭空生成一个金额）
- **错误归因**：值存在于对话中，但对应了错误的槽位名（如把"五万一千"归到 available_credit 而非 withdraw_amount）

**角度二：对齐置信度分布（Alignment Quality）**

langextract 的 `alignment_status` 已提供四级信号：`match_exact / match_lesser / match_fuzzy / None`。
需要分析实际数据的分布，并建立阈值策略：
- `match_exact`（confidence=1.0）：直接进库
- `match_lesser`（confidence=0.85）：进库但标记为"待复核"
- `match_fuzzy`（confidence=0.70）：进入待审队列，不直接使用
- `None`（confidence=0.50）：丢弃，或进入人工标注队列

**角度三：槽位覆盖率与空值分析（Coverage Analysis）**

对知识库整体健康度的统计评估：
- 每条 CustomerRecord 平均填充了多少槽位？哪些槽位长期为空？
- 高空值率的槽位可能意味着：(a) 该槽位在对话中很少被提及；(b) 抽取 prompt 对该槽位的引导不够
- 输出：按槽位名统计填充率，生成 coverage report

**角度四：值合法性验证（Format / Range Validation）**

槽位值存入前应通过规则校验，拦截明显异常：
- 金额类槽位：是否可解析为数字？是否在合理范围内（如 0 ～ 50 万）？
- 姓名类槽位：是否符合中文姓名模式（2~4 汉字，非纯数字）？
- 枚举类槽位（如 loan_status）：是否在白名单值域内？

**角度五：跨 session 一致性（Cross-session Consistency）**

同一客户在不同通话中，相同槽位的值应保持稳定或有规律变化：
- 如果同一客户多条 session 里 available_credit 每次都不同，说明抽取有问题或数据本身有噪声
- 可以统计同一 (customer_id, slot_name) 的值变化次数 / 变化幅度作为质量信号

**角度六：人工抽样评测（Human Evaluation）**

自动指标无法替代人工判断：
- 每批次随机抽取 50~100 条槽位值进行人工标注
- 重点关注：bad case 来自哪类对话？哪类槽位出错最多？
- 输出：Precision@k 以及分槽位的错误率统计

### 潜在解决方案

| 方案 | 适用场景 | 成本 | 说明 |
| --- | --- | --- | --- |
| **置信度阈值过滤** | 快速过滤低质量结果 | 低 | 以 alignment_status 映射的 confidence 为准，低于阈值直接丢弃；`KnowledgeStore` / `SimpleUpdater` 已有基础实现 |
| **规则校验层（Validator）** | 值合法性检查 | 低 | 在 `IncrementalMerger.merge_dialogues` 调用前插入 Validator，逐槽位执行格式 / 范围校验 |
| **覆盖率报告脚本** | 知识库整体健康度监控 | 低 | 扫描所有 CustomerRecord，按槽位统计 filled_count / total_count，输出 Markdown 表格 |
| **对齐质量分层队列** | 模糊 / 无对齐结果的后处理 | 中 | `match_fuzzy` → 进 pending 队列；`None` → 写 rejection log；支持批量人工复核 |
| **黄金标准数据集（Gold Set）** | 自动化精准评测 | 中 | 人工标注 50 条对话的槽位值作为 ground truth，自动对比抽取结果，输出 Precision / Recall / F1 |
| **跨 session 一致性检测** | 识别系统性抽取错误 | 中 | 对同一 (customer_id, slot_name) 聚合所有历史值，计算值方差；方差超阈值则标记为"不稳定槽位" |
| **LLM 二次审核** | bad case 自动分析 | 高 | 对 confidence 低于 0.7 的结果，调用 LLM 以"给定对话原文 + 抽取值，判断是否正确"为 prompt 进行二次校验 |

---

## 4.2 知识去重、冲突处理与更新机制

### 思考角度

**角度一：去重粒度（Deduplication Granularity）**

去重不能"一刀切"，需要区分三个层次：
- **Session 级别去重**：同一 session_id 不重复摄入（幂等摄入）— 最基础，防止批次重叠时重复计算
- **实体级别去重**：同一 customer_id 在知识库中只有一条 CustomerRecord
- **槽位级别去重**：同一 (customer_id, slot_name) 下，相同的 value 只存一份证据

**角度二：冲突的类型定义（What Counts as Conflict）**

同一 (customer_id, slot_name) 出现不同 value 时，需要区分：
- **真实变化**：客户的可用额度从 5 万变成了 3 万（正常业务变更，保留最新值）
- **提取错误**：两次抽取同一通话的结果不一致（以高 confidence 的为准）
- **歧义值**：对话中客户自己也不确定（如"大概五万多吧"），无法判断哪个正确

**角度三：冲突消解策略（Conflict Resolution Strategy）**

这是一个可扩展的策略选择问题，已有 `ConflictStrategy` 协议接口，目前只有 `ConfidenceFirstStrategy`：
- **Confidence First**：新证据 confidence >= 旧证据则替换（已实现）
- **Timestamp First**：时间更晚的通话数据优先（反映最新业务状态）
- **Frequency Voting**：多次抽取中出现次数最多的值胜出（适合同一对话被重复抽取的场景）
- **Human-in-the-loop**：置信度相近且值不同时，进入人工审核队列，不自动消解

**角度四：冲突的可审计性（Audit Trail）**

`schema.py` 中已有 `ConflictEntry` 记录每次冲突的双方证据和消解决定。需要考虑：
- ConflictEntry 是否被持久化到文件 / 数据库？
- 如何快速查询"哪些客户存在未解决冲突"？
- 冲突统计报告：冲突率高的槽位往往反映了数据本身的噪声

**角度五：增量更新机制（Incremental Update）**

每天/每周会有新的通话数据，需要增量处理而非全量重建：
- 识别"新增 session"：通过 `_ingested_sessions` 集合实现（已有）
- 知识库版本管理：每次增量更新后打快照（v1.0, v1.1…），支持回滚
- 批次元数据：记录每次摄入的 session 数量、冲突数量、新增 slot 数量

**角度六：知识老化与 TTL（Knowledge Aging）**

业务数据会随时间失效：
- 客户的可用额度可能因业务变化而过时（上次通话是半年前）
- 需要记录每条 SlotFact 的最后更新时间（已有 `updated_at`）
- 超过一定时间未更新的知识条目应降低置信度，或标记为"待刷新"

### 潜在解决方案

| 方案 | 适用场景 | 成本 | 说明 |
| --- | --- | --- | --- |
| **Session 级幂等摄入** | 防止同一批次数据重复处理 | 已有 | `KnowledgeStore._ingested_sessions` 已实现；需确保持久化时一并保存 |
| **Confidence First 消解** | 自动处理绝大多数冲突 | 已有 | `ConfidenceFirstStrategy` 已实现；适合 confidence 差距明显的场景 |
| **Timestamp First 消解** | 优先使用最新业务数据 | 低 | 在 `ConflictStrategy.resolve` 中比较 `existing.extracted_at` 与 `new.extracted_at`，新值优先 |
| **Frequency Voting 消解** | 同一槽位被多次抽取时取众数 | 中 | 在 `SlotFact` 中维护 `value_counts: Dict[str, int]`，取出现频次最高的 value 为 current |
| **人工审核冲突队列** | 置信度相近、无法自动消解的冲突 | 中 | 将 `resolution="keep_both"` 的 ConflictEntry 导出为待审列表，支持人工标注后回写 |
| **冲突统计报告** | 识别高噪声槽位 | 低 | 扫描所有 ConflictEntry，按 slot_name 统计冲突次数，输出排行榜（冲突率 = conflicts / total_updates） |
| **知识库版本快照** | 支持增量更新与回滚 | 中 | 每次 `merge_dialogues` 完成后调用 `store.save_to_json(path_with_version_tag)`；维护 LATEST 指针 |
| **SlotFact TTL 降权** | 过期知识的自动老化 | 中 | 在查询时检查 `updated_at`，超过 N 天未更新则将 confidence 乘以衰减系数（如 0.9/30天），并在报告中标记 stale |
| **增量摄入元数据日志** | 可观测性 / 运维 | 低 | 每次 `merge_dialogues` 输出 JSON 摘要：新增 sessions、触发冲突数、新增 slot facts 数、耗时 |
