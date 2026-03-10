# 对话数据知识库构建：最终方案

> **文档目的**：给出从原始对话数据到 SGD 格式知识库的完整可行方案，包含各步骤的具体操作、以 langextract 为核心的 schema 校验机制，以及对流程优缺点、可扩展性与动态支持的分析。

---

## 一、整体流程

```
原始对话数据
    │
    ▼  Step 1  LLM 归纳（抽样）
    │
    ▼  Step 2  Schema 合并精化
    │
    ▼  Step 3  langextract 全量校验（原文定位）
    │
    ▼  Step 4  全量 SGD 转换
    │
    ▼
SGD 知识库（schema.json + dialogues_*.json）
```

---

## 二、各步骤具体操作

### Step 1：LLM 归纳初始 Schema

**目标**：从少量对话样本中自动发现服务的意图、槽位和对话行为。

**操作**：
- 从全量数据中**分层抽样** 50–100 条（按对话长度短/中/长各取三分之一，覆盖不同复杂度的对话）
- 调用 LLM，提示词要求：分析对话目的（意图）、信息项（槽位）、话语动作（对话行为），输出结构化 JSON
- 输出：`discovered_ontology`，格式示例：

```json
{
  "intents": [
    {"name": "verify_identity", "description": "核实客户身份", "typical_phrases": ["请问您的手机尾号是多少"]}
  ],
  "slots": [
    {"name": "phone_suffix", "description": "手机号后四位", "data_type": "string"}
  ],
  "dialog_acts": ["INFORM", "REQUEST", "CONFIRM", "GOODBYE"]
}
```

**注意**：这一步只做"发现"，不做最终判断，允许有遗漏和噪声。现有代码：`extract_ontology_from_dialogues()`。

---

### Step 2：Schema 合并精化

**目标**：将 Step 1 归纳结果与已有的预定义 schema 合并，得到完整的候选 schema。

**操作**：
- 以预定义 schema（`resources/anyihua_sgd/schema.json`）为基准
- 对意图和槽位分别执行：
  - **同名合并**：取更完整的描述，合并 `typical_phrases`、`possible_values`
  - **预定义有、归纳无**：保留（标注 `source: predefined`，可能是低频边缘场景）
  - **归纳有、预定义无**：追加（标注 `source: discovered`，待 Step 3 校验）
- 输出：`merged_schema`，每个条目携带 `source` 字段（`both` / `predefined` / `discovered`）

现有代码：`merge_ontologies()`，`chat_test_merged_schema.json`。

**可选人工干预点**：查看合并结果，手动剔除明显错误的归纳项，然后再进入 Step 3。

---

### Step 3：langextract 全量校验（原文定位）

**目标**：对 `merged_schema` 中每一个意图和槽位，在全量数据中验证其真实存在性，并获取精确的原文依据。

#### 3.1 langextract 的核心能力

[google/langextract](https://github.com/google/langextract) 以 SGD 对话为 few-shot 示例进行结构化信息提取。它的关键特性是：**每次提取同时输出结果值和该值在原文中的精确定位（字符偏移量或原句引用）**。这意味着不仅知道"这条对话中存在 `verify_identity` 意图"，还能看到触发该意图的确切原句，例如：

```json
{
  "intent": "verify_identity",
  "evidence": "请问您的手机尾号是多少？",
  "span": {"start": 42, "end": 57}
}
```

#### 3.2 具体操作

- **输入**：全量原始对话 + `merged_schema`（作为提取目标定义）
- **对每条对话**，调用 langextract 提取：
  - `active_intent`：该轮用户主要意图及触发原句
  - `slot_values`：提及的槽位值及其在对话中的原文位置
- **汇总统计**（每个 schema 项）：

| 指标 | 计算方式 | 说明 |
|------|---------|------|
| `evidence_count` | 出现该项的对话条数 | 主要可靠性指标 |
| `coverage_pct` | `evidence_count / 全量数据总数 × 100` | 覆盖率 |
| `sample_quotes` | 随机抽取 3–5 条原文证据 | 供人工复查 |

- **校验规则**：

| schema 项来源 | 校验规则 |
|--------------|---------|
| `source: both` | 无条件保留（预定义优先权） |
| `source: predefined` | 无条件保留（可能低频但业务必要） |
| `source: discovered` | `evidence_count < 2` → 标记删除；否则保留 |

- **输出**：
  - `schema_validation_report.json`：每个 schema 项的 `evidence_count`、`coverage_pct`、`sample_quotes`、`keep` 决策
  - `validated_schema.json`：已删除噪声项的最终 schema，并用原文证据丰富 `description`

#### 3.3 原文定位的额外价值

- `sample_quotes` 直接作为 schema 中 `typical_phrases` 字段的内容，提升 schema 的可读性和后续 LLM 提取的质量
- 可根据原文定位追溯任意 schema 项的"数据来源对话 ID"，便于人工抽查和审计
- 对槽位校验时，langextract 的定位可区分"槽位名称出现过"与"槽位值被实际填充"，校验更精确

---

### Step 4：全量 SGD 格式转换

**目标**：以 `validated_schema` 为标准，将全量对话数据转换为 SGD 格式。

**操作**：
- 对全量数据重新调用 LLM 提取（以 `validated_schema` 约束意图/槽位列表），提取每轮：
  - USER 轮：`active_intent`、`requested_slots`、`slot_values`、`actions`
  - SYSTEM 轮：`actions`、`service_call`、`service_results`
- **容错设计**：schema 中定义的意图/槽位不要求每条对话都出现，缺失字段留空或使用默认值
- 按 SGD 标准格式打包输出：

```
output/
├── schema.json              # validated_schema 转换而来
├── dialogues_001.json       # 前 50 条对话（每文件默认 50 条）
├── dialogues_002.json
├── extraction_summary.json  # 提取统计
└── README.md                # 数据集说明
```

现有代码：`extract_record_with_llm()`、`export_sgd_format()`、`save_sgd_to_directory()`。

---

## 三、各步骤输出与衔接

```
Step 1  →  discovered_ontology.json
Step 2  →  merged_schema.json
Step 3  →  schema_validation_report.json
            validated_schema.json
Step 4  →  schema.json  +  dialogues_*.json
```

Step 3 是唯一的"去噪"节点；Step 4 是最终的格式化节点。两者之间有一个可选人工确认窗口（查看 `schema_validation_report.json` 后决定是否手动调整 `validated_schema`），之后 Step 4 完全自动化。

---

## 四、优缺点分析

### 优点

| 优点 | 说明 |
|------|------|
| **有据可查** | langextract 的原文定位为每个 schema 项提供真实数据证据，而非纯粹 LLM 推理 |
| **降低幻觉风险** | Step 3 用统计+原文双重验证，能有效过滤 LLM 在 Step 1 中凭空捏造的意图/槽位 |
| **容错性强** | Step 4 允许 schema 与对话数据部分不匹配，不因单条数据缺字段而失败 |
| **人工干预点明确** | 两个可选介入点（Step 2 合并后、Step 3 报告后），不强制，但存在质量把关机会 |
| **输出标准化** | 最终输出符合 SGD 规范，可直接供 PyTOD / FnCTOD / DST 算法使用 |

### 缺点

| 缺点 | 说明 |
|------|------|
| **Step 3 计算开销较大** | langextract 对全量数据逐条调用 LLM，数据量大时耗时长（可用批量 API 缓解） |
| **Step 1 样本偏差风险** | 分层抽样无法保证覆盖所有低频场景，罕见意图仍可能被遗漏 |
| **依赖 LLM 质量** | 整个流程的上限受限于 LLM 对特定语言和领域的理解能力 |
| **Step 3 阈值需要调整** | `evidence_count < 2` 是经验值，不同规模数据集需要相应调整 |

---

## 五、可扩展性与动态支持

### 5.1 处理任意新数据集

整个流程与数据集内容无关，只需提供：

1. **输入适配器**：将新数据集的格式（JSON / CSV / 数据库 / 音频转写文本）标准化为 `[{dialogue_id, turns: [{speaker, text}]}]` 的通用格式
2. **数据集配置**（YAML 文件）：

```yaml
dataset_name: "hotel_booking"
language: "zh"
input_path: "data/hotel_dialogues.json"
predefined_schema: null         # 无预定义时，Step 2 仅用 Step 1 结果
step1_sample_n: 80
step3_min_evidence_count: 2
output_dir: "output/hotel_sgd"
```

3. **可选 CRM/知识库上下文**：如有外部用户数据，在 Step 4 中作为 `service_results` 填充依据

新数据集**不需要改动核心流程代码**，只需新增一个适配器函数和一个配置文件。

### 5.2 增量数据扩充

当同一数据集新增一批数据时，无需从头重跑：

```
新增对话数据（增量批次）
    │
    ▼ Step 1'  仅对新增数据做 LLM 归纳
    │
    ▼ Step 2'  与现有 validated_schema 合并
              （只合并 source: discovered 的新增项）
    │
    ▼ Step 3'  仅对新增项运行 langextract 校验
    │
    ▼ Step 4'  仅对新增数据做 SGD 转换，追加到现有输出目录
```

**判断是否需要全量重建**：

| 情况 | 策略 |
|------|------|
| 新增数据 < 20% 原有量，且无新意图 | 增量更新（Step 1'–4'） |
| 新增数据 > 20% 原有量 | 全量重建（更新 Step 1 样本池） |
| 发现 3 个以上新意图 | 全量重建（新意图影响旧数据的提取质量） |
| predefined schema 大幅变更 | 全量重建 |

### 5.3 多数据集并行

每个数据集独立维护自己的 schema 版本和 SGD 输出目录。跨数据集共享的通用意图（如 `say_goodbye`、`escalate_to_human`）可抽取到公共 base schema，各数据集配置通过 `extends: base.yaml` 继承，避免重复定义。

---

## 附录：输出文件一览

| 步骤 | 文件名 | 用途 |
|------|--------|------|
| Step 1 | `discovered_ontology.json` | LLM 归纳的初始意图/槽位/对话行为 |
| Step 2 | `merged_schema.json` | 预定义 + 归纳合并的候选 schema |
| Step 3 | `schema_validation_report.json` | 每个 schema 项的证据数量、覆盖率、原文引用 |
| Step 3 | `validated_schema.json` | 校验后的最终 schema（噪声已清除） |
| Step 4 | `schema.json` | SGD 格式 schema（供 TOD 系统直接使用） |
| Step 4 | `dialogues_*.json` | SGD 格式对话数据 |
| Step 4 | `extraction_summary.json` | 提取统计（字段覆盖率、意图分布等） |
