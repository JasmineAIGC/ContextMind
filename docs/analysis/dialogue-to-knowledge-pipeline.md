# 对话数据知识库构建：最终方案

> **文档目的**：给出从原始对话数据到 SGD 格式知识库的完整可行方案，包含各步骤的具体操作、以 langextract 贯穿全程的原文定位机制，以及对流程优缺点、可扩展性与动态支持的分析。

---

## 一、设计原则：每一步都用 langextract

langextract 的核心特性是：**每次提取同时输出结果值和该值在原文中的精确定位（字符偏移量或原句引用）**。这意味着每次调用 langextract 本身就是一次隐式校验——若某个意图或槽位值无法在原文中定位，langextract 就不会输出它。

基于这一特性，新方案将 langextract 贯穿 Schema 发现和 SGD 转换两个核心环节，**无需再设置独立的校验步骤**。每一次提取计算都自带原文定位，相当于每一步都在做校验。

---

## 二、整体流程

```
原始对话数据
    │
    ▼  Step 1  langextract Schema 发现（抽样，原文定位 = 内嵌校验）
    │
    ▼  Step 2  Schema 合并精化（LLM 合并去重 + 预定义 schema 补充低频项）
    │
    ▼  Step 3  langextract 全量 SGD 转换（原文定位 = 内嵌校验）
    │
    ▼
SGD 知识库（schema.json + dialogues_*.json）
```

---

## 三、各步骤具体操作

### Step 1：langextract Schema 发现（抽样）

**目标**：从少量对话样本中，通过 langextract 的原文定位能力自动发现服务的意图与槽位，确保每个发现项都有原文证据支撑。

**操作**：
- 从全量数据中**分层抽样** 50–100 条（按对话长度短/中/长各取三分之一，覆盖不同复杂度的对话）
- 以少量预标注的 SGD 对话作为 few-shot 示例，调用 langextract 对每条抽样对话提取：
  - `intent`：对话轮次的主要意图及触发原句
  - `slot_value`：提及的槽位值及其在对话中的原文位置
- langextract 提取结果示例：

```json
{
  "intent": "verify_identity",
  "evidence": "请问您的手机尾号是多少？",
  "span": {"start": 42, "end": 57}
}
```

- 汇总抽样结果，归纳出候选的意图名称列表和槽位名称列表，形成 `discovered_ontology`

**关键优势**：与旧方案用普通 LLM 归纳不同，langextract 的每条归纳结果都携带原文证据。没有原文证据的意图或槽位不会出现在输出中——**发现即校验**。

**注意**：这一步只做"发现"，不做最终判断，允许低频意图被遗漏（低频意图因抽样覆盖不足可能未出现在样本中，Step 2 通过引入预定义 schema 来补充这些边缘场景）。现有相关代码：`dialogue_to_langextract_example()`、`dialogues_to_langextract_examples()`。

---

### Step 2：Schema 合并精化

**目标**：将 Step 1 的 langextract 发现结果与已有的预定义 schema 合并，得到完整的候选 schema。

**操作**：
- 以预定义 schema（`resources/anyihua_sgd/schema.json`）为基准
- 对意图和槽位分别执行：
  - **同名合并**：取更完整的描述，合并 `typical_phrases`（直接来自 Step 1 langextract 提取的原句证据）、`possible_values`
  - **预定义有、发现无**：保留（标注 `source: predefined`，可能是低频边缘场景）
  - **发现有、预定义无**：追加（标注 `source: discovered`，已有 Step 1 原文证据支撑）
- 输出：`merged_schema`，每个条目携带 `source` 字段（`both` / `predefined` / `discovered`）

现有代码：`merge_ontologies()`，`chat_test_merged_schema.json`。

**可选人工干预点**：查看合并结果，手动剔除明显错误的条目，然后再进入 Step 3。由于 Step 1 的发现结果已经过 langextract 的原文定位筛选，此处需要剔除的噪声比旧方案更少。

---

### Step 3：langextract 全量 SGD 转换

**目标**：以 `merged_schema` 为标准，对全量对话数据调用 langextract 进行结构化提取，直接输出 SGD 格式数据。每次 langextract 调用均携带原文定位，相当于在转换的同时完成校验。

#### 3.1 langextract 在转换中的角色

[google/langextract](https://github.com/google/langextract) 以 SGD 对话为 few-shot 示例进行结构化信息提取。在 Step 3 中，langextract 承担双重职责：

1. **转换**：按 `merged_schema` 定义从对话中提取意图、槽位值，直接组装为 SGD 格式
2. **校验**：每个提取项都必须能在原文中定位，无法定位的项不输出，避免幻觉

与旧方案"先用普通 LLM 转换、再单独校验"相比，langextract 将转换和校验合并为单次调用。

#### 3.2 具体操作

- **输入**：全量原始对话 + `merged_schema`（作为 few-shot 描述和提取目标定义）
- **对每条对话**，调用 langextract 提取：
  - `active_intent`：该轮用户主要意图及触发原句
  - `slot_values`：提及的槽位值及其在对话中的原文位置
  - `system_intent`：坐席执行的服务调用动作及对应发言
- **质量指标**（在 `extraction_summary.json` 中记录）：

| 指标 | 计算方式 | 说明 |
|------|---------|------|
| `evidence_rate` | 有原文证据的提取项占比 | langextract 内建，反映提取质量 |
| `slot_fill_rate` | 各槽位在全量数据中的填充率 | 反映 schema 覆盖度 |
| `intent_distribution` | 各意图出现频次分布 | 供后续分析使用 |
| `sample_quotes` | 各 schema 项的原文证据示例 | 供人工抽查 |

- **容错设计**：schema 中定义的意图/槽位不要求每条对话都出现，缺失字段留空或使用默认值

#### 3.3 SGD 输出格式

按 SGD 标准格式打包输出：

```
output/
├── schema.json              # merged_schema 转换而来
├── dialogues_001.json       # 前 50 条对话（每文件默认 50 条）
├── dialogues_002.json
├── extraction_summary.json  # 提取统计（含原文证据率、槽位填充率等）
└── README.md                # 数据集说明
```

现有相关代码：`dialogue_to_langextract_example()`、`export_sgd_format()`、`save_sgd_to_directory()`。

---

## 四、各步骤输出与衔接

```
Step 1  →  discovered_ontology.json    （langextract 发现，含原文证据）
Step 2  →  merged_schema.json          （预定义 + 发现合并，typical_phrases 来自原文）
Step 3  →  schema.json  +  dialogues_*.json  +  extraction_summary.json
```

Step 2 之后有一个可选人工确认窗口（查看 `merged_schema.json` 后决定是否手动调整），之后 Step 3 完全自动化。由于 Step 1 和 Step 3 都使用 langextract，schema 中的每个条目和每条 SGD 记录均可追溯到原文证据。

---

## 五、优缺点分析

### 与旧方案的对比

旧方案共四步：Step 1 普通 LLM 归纳 → Step 2 Schema 合并 → Step 3 langextract 独立校验 → Step 4 普通 LLM SGD 转换。新方案共三步，去掉了独立的校验步骤，并将 Step 1 和 Step 3 均改为 langextract。两方案的 LLM 调用总量基本持平（旧方案 Step 3 校验全量数据 + Step 4 转换全量数据，新方案 Step 1 对抽样数据调用 langextract + Step 3 对全量数据调用 langextract），但新方案每次调用都自带原文定位，质量更高、流程更简洁。

### 优点

| 优点 | 说明 |
|------|------|
| **每步都有据可查** | langextract 在 Step 1 和 Step 3 均输出原文定位，Schema 发现和 SGD 转换结果均可追溯 |
| **校验内嵌，无需额外步骤** | 每次 langextract 调用即是一次原文校验，无法在原文中定位的项不会出现在输出中 |
| **降低幻觉风险** | Step 1 的 Schema 发现已通过 langextract 过滤，噪声意图/槽位在发现阶段即被淘汰 |
| **流程更简洁** | 三步替代旧方案四步，去掉了独立的校验步骤，逻辑链更清晰 |
| **容错性强** | Step 3 允许 schema 与对话数据部分不匹配，不因单条数据缺字段而失败 |
| **人工干预点明确** | 一个可选介入点（Step 2 合并后），不强制，但存在质量把关机会 |
| **输出标准化** | 最终输出符合 SGD 规范，可直接供 PyTOD / FnCTOD / DST 算法使用 |

### 缺点

| 缺点 | 说明 |
|------|------|
| **Step 1 和 Step 3 计算开销均较大** | 两个步骤都调用 langextract（底层为 LLM），但总调用量与旧方案（Step 3 校验 + Step 4 转换）基本持平，且去掉了独立校验步骤（可用批量 API 缓解） |
| **Step 1 样本偏差风险** | 分层抽样无法保证覆盖所有低频场景，罕见意图仍可能被遗漏（Step 2 通过预定义 schema 补充） |
| **依赖 LLM 质量** | 整个流程的上限受限于 LLM 对特定语言和领域的理解能力 |
| **few-shot 示例质量影响结果** | langextract 的提取质量依赖 few-shot 示例的覆盖度，需要维护高质量示例集 |

---

## 六、可扩展性与动态支持

### 6.1 处理任意新数据集

整个流程与数据集内容无关，只需提供：

1. **输入适配器**：将新数据集的格式（JSON / CSV / 数据库 / 音频转写文本）标准化为 `[{dialogue_id, turns: [{speaker, text}]}]` 的通用格式
2. **数据集配置**（YAML 文件）：

```yaml
dataset_name: "hotel_booking"
language: "zh"
input_path: "data/hotel_dialogues.json"
predefined_schema: null         # 无预定义时，Step 2 仅用 Step 1 结果
step1_sample_n: 80
langextract_model: "gemini-2.5-flash"
output_dir: "output/hotel_sgd"
```

3. **可选 CRM/知识库上下文**：如有外部用户数据，在 Step 3 中作为 `service_results` 填充依据

新数据集**不需要改动核心流程代码**，只需新增一个适配器函数和一个配置文件。

### 6.2 增量数据扩充

当同一数据集新增一批数据时，无需从头重跑：

```
新增对话数据（增量批次）
    │
    ▼ Step 1'  仅对新增数据用 langextract 做抽样发现
    │
    ▼ Step 2'  与现有 merged_schema 合并
              （只合并 source: discovered 的新增项）
    │
    ▼ Step 3'  仅对新增数据做 langextract SGD 转换，追加到现有输出目录
```

**判断是否需要全量重建**：

| 情况 | 策略 |
|------|------|
| 新增数据 < 20% 原有量，且无新意图 | 增量更新（Step 1'–3'） |
| 新增数据 > 20% 原有量 | 全量重建（更新 Step 1 样本池） |
| 发现 3 个以上新意图 | 全量重建（新意图影响旧数据的提取质量） |
| predefined schema 大幅变更 | 全量重建 |

### 6.3 多数据集并行

每个数据集独立维护自己的 schema 版本和 SGD 输出目录。跨数据集共享的通用意图（如 `say_goodbye`、`escalate_to_human`）可抽取到公共 base schema，各数据集配置通过 `extends: base.yaml` 继承，避免重复定义。

---

## 附录：输出文件一览

| 步骤 | 文件名 | 用途 |
|------|--------|------|
| Step 1 | `discovered_ontology.json` | langextract 发现的初始意图/槽位（含原文证据） |
| Step 2 | `merged_schema.json` | 预定义 + 发现合并的候选 schema |
| Step 3 | `schema.json` | SGD 格式 schema（供 TOD 系统直接使用） |
| Step 3 | `dialogues_*.json` | SGD 格式对话数据 |
| Step 3 | `extraction_summary.json` | 提取统计（原文证据率、槽位填充率、意图分布等） |
