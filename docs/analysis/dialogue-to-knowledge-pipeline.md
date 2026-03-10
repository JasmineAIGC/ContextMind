# 对话数据知识库构建：流程分析与通用化设计

> **文档目的**：
> 1. 分析"安逸花外呼数据 → 结构化知识库（SGD 格式）"流程的合理性与现存问题
> 2. 提出最优的 5 阶段处理流程，并说明各阶段的职责边界
> 3. 归纳**通用化设计模式**，使同一流程可直接应用于任意新的对话数据集
> 4. 说明如何以**动态、可扩展**的方式支持数据集增量扩充与多数据集并行处理

---

## 一、用户描述的流程分析

### 1.1 原始描述（4 步）

| 步骤 | 描述 |
|------|------|
| Step 1 | 通过 LLM 分析原始对话数据，得到意图、槽位、对话行为等信息 |
| Step 2 | 基于这些预定义信息，跑全量数据，对意图/槽位/行为做增删合并更新，得到更全的 schema |
| Step 3 | 使用 langextract 处理全量数据，校验 schema 中各项信息是否可靠（验证意图来源等） |
| Step 4 | 校验完成后，基于全量 schema 跑全量数据，输出 SGD 格式 |

### 1.2 流程正确性评估

**整体方向正确**——该流程体现了"先归纳、再验证、最后转换"的数据工程思想，与 Schema-Guided Dialogue 的设计理念高度吻合。以下是各步骤的评估：

#### Step 1 ✅ 方向正确，但样本数量需关注

从原始对话数据中通过 LLM 归纳本体（意图/槽位/对话行为）是最合理的起点，避免了完全依赖人工预定义导致的覆盖盲区。

**注意**：现有代码（`extract_ontology_from_dialogues`）默认只用 **30 条样本**做归纳。对于低频意图（如 `handle_loan_dispute`），样本量可能不足。建议：
- 采样策略从"前 N 条"改为**分层采样**（按时间、按对话长度、按话题关键词分层）
- 样本量适当提升到 50–100 条，或按数据集规模自适应

#### Step 2 ⚠️ 需要明确"全量数据"的作用

"跑全量数据做 schema 增删合并"实际上包含两个不同操作，应拆分：
- **2a. 合并预定义本体**（predefined schema + LLM 归纳结果 → merged schema）：这是静态合并，已在代码中由 `merge_ontologies()` 实现
- **2b. 基于全量数据的 schema 验证**：用全量数据对每个意图/槽位做统计覆盖率分析，确认哪些 schema 项有足够的数据支撑，哪些是"孤立噪声"

Step 2b 是**目前代码中缺失的关键步骤**。

#### Step 3 ⚠️ langextract 定位需要澄清

langextract（[google/langextract](https://github.com/google/langextract)）是一个基于 LLM 的结构化信息提取库，使用 SGD 对话作为 few-shot 示例。在本流程中，Step 3 的核心诉求是：

> 对 schema 中的每一项（意图/槽位/对话行为），统计其在全量数据中的出现频率与置信度，以此判断该 schema 项是否可靠。

这个需求可以通过**以 merged schema 为标准、对全量数据做一次 LLM 提取（即 Phase 1）后再做统计**来实现。langextract 是可选的实现工具之一，也可以直接用本项目已有的 LLM 提取框架。

**关键认知**：Step 3 的"校验"不是一次性操作，而应与 Step 2 合并为一个**schema 迭代精化**环节：先粗粒度归纳 → 全量统计验证 → 剔除噪声 → 精化 schema → 再次验证（可选）。

#### Step 4 ✅ 正确，但需加入容错设计

全量数据按 validated schema 转 SGD 格式，这一步逻辑正确。用户也正确指出"schema 与 SGD 数据不一定完全匹配，允许有缺失"——这符合实际情况，因为并非每条对话都会覆盖所有意图和槽位。

---

## 二、最优处理流程（5 阶段）

基于以上分析，建议将处理流程重构为以下 **5 阶段（Phase 0–4）**：

```
原始对话数据
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 0：本体归纳（Schema Induction）                       │
│  输入：原始对话（分层采样，N=50~100）                         │
│  工具：LLM（以 _ONTOLOGY_SYSTEM_PROMPT 为指导）              │
│  输出：discovered_ontology（意图/槽位/对话行为，含描述）      │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 1：Schema 合并与精化（Schema Consolidation）          │
│  输入：discovered_ontology + predefined schema               │
│  工具：merge_ontologies()                                    │
│  输出：merged_schema（含 source 标注：both/predefined/dis）  │
│  可选：人工审核合并结果，手动删除明显噪声                     │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 2：全量数据 Schema 验证（Schema Validation）          │
│  输入：全量原始数据 + merged_schema                          │
│  工具：LLM 提取（轻量级，只抽 active_intent + slot_values） │
│  输出：validation_report（每个 schema 项的覆盖率/置信度）    │
│  阈值：覆盖率 < 1% 且 source="discovered" → 标记为"存疑"    │
│  决策：人工确认保留/剔除"存疑"项，得到 validated_schema      │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 3：全量数据完整提取（Full Extraction）                 │
│  输入：全量原始数据 + validated_schema                       │
│  工具：extract_record_with_llm()（含 active_intent / slots  │
│        / dialog acts / service_call / service_results）     │
│  输出：extracted_records（每条对话的完整 SGD 字段）          │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 4：SGD 格式导出（SGD Export）                         │
│  输入：extracted_records + validated_schema                  │
│  工具：export_sgd_format() + save_sgd_to_directory()        │
│  输出：schema.json + dialogues_*.json + README.md 等        │
│  说明：允许 schema 与对话数据部分不匹配（字段缺失容错）       │
└─────────────────────────────────────────────────────────────┘
```

### 2.1 各阶段职责边界说明

| 阶段 | 核心问题 | 允许不确定性 | 需要人工介入 |
|------|----------|------------|-------------|
| Phase 0 本体归纳 | "这个数据集有哪些意图和槽位？" | 高（LLM 归纳可能遗漏） | 否 |
| Phase 1 Schema 合并 | "预定义和归纳的如何统一？" | 中（合并规则清晰） | 可选（审核结果） |
| Phase 2 Schema 验证 | "每个 schema 项在数据中可靠吗？" | 低（基于统计） | 建议（阈值过滤后确认） |
| Phase 3 全量提取 | "每条对话对应哪些 schema 项？" | 中（LLM 可能填错） | 否（自动化） |
| Phase 4 SGD 导出 | "如何输出标准格式？" | 低 | 否 |

### 2.2 与现有代码的对应关系

| 最优流程 | 现有代码实现 | 差距 |
|---------|------------|------|
| Phase 0 本体归纳 | `extract_ontology_from_dialogues()`（30条） | 样本量偏少；采样策略为"前N条" |
| Phase 1 Schema 合并 | `merge_ontologies()` | ✅ 已完整实现 |
| **Phase 2 Schema 验证** | `compare_with_predefined()`（仅静态对比） | ❌ **缺失**：缺少基于全量数据的覆盖率统计 |
| Phase 3 全量提取 | `extract_record_with_llm()`（全量） | ✅ 已完整实现 |
| Phase 4 SGD 导出 | `export_sgd_format()` + `save_sgd_to_directory()` | ✅ 已完整实现 |

### 2.3 Phase 2 设计补充（当前缺失）

Phase 2 的核心输出是一份 **Schema 验证报告**，对每个 schema 项统计：

```json
{
  "intent_coverage": {
    "verify_identity": {"count": 87, "coverage_pct": 87.0, "source": "both", "reliable": true},
    "handle_loan_dispute": {"count": 3, "coverage_pct": 3.0, "source": "discovered", "reliable": false},
    "...": "..."
  },
  "slot_coverage": {
    "customer_name": {"count": 95, "crm_coverage_pct": 100.0, "source": "both", "reliable": true},
    "new_slot_x": {"count": 1, "crm_coverage_pct": 0.0, "source": "discovered", "reliable": false}
  },
  "validation_thresholds": {
    "min_count": 2,
    "min_coverage_pct": 2.0
  },
  "items_flagged_as_unreliable": ["handle_loan_dispute", "new_slot_x"]
}
```

**验证规则（建议）**：
- `source="both"` 的项：无论覆盖率如何，默认保留（预定义具有优先权）
- `source="discovered"` 的项：覆盖率 < 2% 或 count < 2 → 标记为"存疑"，提示人工确认
- `source="predefined"` 的项：无论覆盖率如何保留（可能是低频但重要的边缘场景）

---

## 三、通用化设计模式

### 3.1 核心思想

将上述 5 阶段流程抽象为**与领域无关的通用框架**，通过配置文件描述数据集特征，使同一套代码可以处理任意新的对话数据集。

### 3.2 数据集配置（Dataset Config）

每个新数据集对应一个 YAML/JSON 配置文件：

```yaml
# configs/datasets/anyihua.yaml
dataset_name: "anyihua_outbound"
service_name: "AnYiHua_1"
description: "安逸花外呼促活对话服务"
language: "zh"

input:
  path: "resources/data/chat_test_100.json"
  format: "list_of_dialogues"           # 输入格式类型
  dialogue_field: null                   # null = 每条记录本身就是对话
  text_format: "prefix_separated"        # "坐席：xxx\n用户：yyy"
  agent_prefix: "坐席："
  user_prefix: "用户："

output:
  dir: "resources/data/anyihua_sgd_extracted"
  dialogues_per_file: 50

phase0:
  sample_n: 50                           # 本体归纳样本量
  sampling_strategy: "stratified"        # "first_n" | "random" | "stratified"
  stratify_by: "dialogue_length"

phase2:
  min_count_threshold: 2                 # 低于此数量标记为"存疑"
  min_coverage_pct: 2.0
  auto_reject_discovered_below_threshold: false  # true=自动剔除，false=标记后人工确认

predefined_schema:
  path: "resources/anyihua_sgd/schema.json"   # 可选，null=完全数据驱动
  merge_strategy: "predefined_priority"         # 预定义优先

crm_fields:                              # 可选，有 CRM 数据时配置
  enabled: true
  parser: "contextmind.scenarios.anyihua.utils.parse_user_info"
```

**对于一个全新数据集**，只需提供：
1. 输入文件路径与格式
2. 对话文本的格式（前缀分隔、JSON 结构、纯文本等）
3. 是否有预定义 schema（没有则完全数据驱动）
4. Phase 2 验证阈值

### 3.3 标准化接口

通用框架应定义以下接口，每个数据集实现对应的适配器：

```python
class DialogueDatasetAdapter:
    """通用对话数据集适配器接口"""

    def load_dialogues(self, path: str) -> List[Dict]:
        """加载原始对话数据，返回标准化的对话列表"""
        raise NotImplementedError

    def extract_turns(self, dialogue: Dict) -> List[Dict]:
        """从单条对话中提取轮次列表，每个轮次含 speaker 和 text"""
        raise NotImplementedError

    def get_crm_context(self, dialogue: Dict) -> Optional[Dict]:
        """返回 CRM/用户画像上下文（可选，无则返回 None）"""
        return None

    def get_dialogue_id(self, dialogue: Dict) -> str:
        """返回对话唯一 ID"""
        raise NotImplementedError
```

针对安逸花的适配器已隐式实现在 `analyze_chat_test.py` 中；通用化后，只需继承此接口并在配置文件中指定适配器类路径。

### 3.4 通用流程调用示例

```bash
# 处理安逸花外呼数据
python -m contextmind.pipeline.run \
    --config configs/datasets/anyihua.yaml \
    --phases 0,1,2,3,4

# 处理一个全新的酒店预订对话数据集（只有原始对话，无预定义 schema）
python -m contextmind.pipeline.run \
    --config configs/datasets/hotel_booking.yaml \
    --phases 0,1,2,3,4
```

### 3.5 不同数据集类型的适配策略

| 数据集类型 | Phase 0 重点 | Phase 1 策略 | Phase 2 重点 |
|-----------|-------------|-------------|-------------|
| **有预定义 schema** | 验证与补充 | predefined_priority | 重点关注 discovered-only 项 |
| **无预定义 schema** | 深度归纳 | discovered_only | 全量统计，阈值过滤 |
| **多服务对话**（如 SGD） | 按服务分组归纳 | 多 schema 合并 | 按服务分别验证 |
| **中文对话** | 使用中文 prompt | 统一 snake_case 归一化 | 同英文，无特殊处理 |
| **有 CRM/知识库** | CRM 字段优先提示 | 保留 CRM 对应槽位 | CRM 覆盖率 = 额外可靠性指标 |

---

## 四、动态支持数据集扩充与多数据集

### 4.1 场景描述

随着业务发展，同一类型的对话数据会持续增加（例如每月新增一批安逸花外呼录音数据），或者需要支持完全不同的业务场景（如信用卡投诉对话、贷款审批对话等）。

### 4.2 增量数据扩充（同一数据集新增数据）

**挑战**：新数据可能包含现有 schema 未覆盖的新意图或槽位，需要在不从头重跑的前提下更新 schema。

**推荐策略**：

```
旧 validated_schema
        +
新增对话数据（增量批次）
        │
        ▼
 Phase 0'（增量本体归纳）
 仅对新增数据做 LLM 本体归纳
        │
        ▼
 Phase 1'（增量 schema 合并）
 merge_ontologies(旧 validated_schema, 新增 discovered)
 source 标注：
   - 旧有且新数据也有 → "both"（已升级来源）
   - 旧有但新数据没有 → "predefined"（保持）
   - 新数据新发现 → "discovered"（待验证）
        │
        ▼
 Phase 2'（增量 schema 验证）
 只验证 source="discovered" 的新增项
        │
        ▼
 新 validated_schema（版本 v2）
        │
        ▼
 Phase 3'（仅对新增数据做全量提取，使用 validated_schema v2）
```

**Schema 版本管理建议**：

```
resources/schemas/
├── anyihua/
│   ├── schema_v1.0_2024-01.json    # 首次生成
│   ├── schema_v1.1_2024-03.json    # 增量更新：新增 3 个意图
│   ├── schema_v2.0_2024-06.json    # 重大更新：预定义重构
│   └── schema_current.json -> schema_v2.0_2024-06.json  # 软链接指向当前版本
```

每次 schema 更新记录 changelog：
```json
{
  "version": "1.1",
  "date": "2024-03-15",
  "changes": [
    {"type": "add_intent", "name": "handle_early_repayment", "source": "discovered", "coverage_pct": 4.2},
    {"type": "add_slot", "name": "repayment_amount", "source": "discovered", "coverage_pct": 4.1},
    {"type": "remove_intent", "name": "legacy_greeting", "reason": "coverage_pct < 1%"}
  ]
}
```

### 4.3 多数据集并行处理

**场景**：同一套流程，同时处理安逸花外呼、信用卡客服、贷款审批等多个不同业务场景的对话数据集。

**推荐架构**：

```
configs/datasets/
├── anyihua_outbound.yaml        # 安逸花外呼
├── credit_card_service.yaml     # 信用卡客服
├── loan_approval.yaml           # 贷款审批
└── base.yaml                    # 公共默认配置（可继承）

resources/schemas/
├── anyihua/                     # 每个数据集独立 schema 目录
├── credit_card/
└── loan_approval/

resources/sgd_output/
├── anyihua_sgd/                 # 每个数据集独立 SGD 输出目录
├── credit_card_sgd/
└── loan_approval_sgd/
```

**跨数据集 Schema 复用**：当多个数据集共享某些通用意图/槽位（如 `say_goodbye`、`escalate_to_human`、`customer_name`），可建立**公共基础 schema**：

```yaml
# configs/datasets/base.yaml
shared_schema:
  path: "resources/schemas/shared_base.yaml"
  intents:
    - name: "say_goodbye"
      description: "礼貌告别，结束对话"
    - name: "escalate_to_human"
      description: "转接人工客服"
  slots:
    - name: "customer_name"
      description: "客户姓名"
    - name: "phone_suffix"
      description: "手机号后四位，用于身份验证"
```

每个数据集配置可 `extends: base.yaml`，自动继承公共 schema 并在此基础上做领域特定扩展。

### 4.4 全量重建 vs. 增量更新的决策矩阵

| 情况 | 建议策略 |
|------|---------|
| 新增数据 < 20% 原有数据量 | 增量更新（仅新数据跑 Phase 0'、1'、2'、3'） |
| 新增数据 > 20% 原有数据量 | 全量重建（Phase 0 样本扩充，重新做 0~4） |
| predefined schema 发生重大变化 | 全量重建 |
| 新增数据发现大量新意图（> 3 个） | 全量重建（新意图可能影响旧数据的提取质量） |
| 数据集语言、领域完全不同 | 新建数据集配置，独立全量处理 |

---

## 五、总结与行动建议

### 5.1 现有流程的问题汇总

| 问题 | 影响 | 优先级 |
|------|------|--------|
| Phase 2 缺失（无全量数据 schema 验证） | schema 中可能保留噪声，影响下游提取质量 | 🔴 高 |
| Phase 0 样本量仅 30 条，采样策略为"前N" | 低频意图可能被遗漏 | 🟡 中 |
| 流程硬编码安逸花逻辑，不可复用 | 新数据集需要重写代码 | 🟡 中 |
| 无 schema 版本管理 | 无法追溯 schema 变更历史 | 🟢 低 |

### 5.2 行动建议（优先级排序）

1. **【高优先级】实现 Phase 2 Schema 验证模块**
   - 新增函数 `validate_schema_coverage(extracted_records, merged_schema) -> ValidationReport`
   - 对每个意图/槽位统计在全量数据中的出现次数和覆盖率
   - 输出 `chat_test_schema_validation_report.json`
   - 在 `main()` 中插入 Phase 2 和 Phase 3 之间

2. **【中优先级】提升 Phase 0 采样质量**
   - 将 `extract_ontology_from_dialogues` 的采样策略从"前 N 条"改为分层采样
   - 按对话长度（短/中/长）分层，每层各取 1/3 样本
   - 样本量参数化（`--ontology-sample-n`，默认 50）

3. **【中优先级】提取数据集配置层**
   - 将安逸花相关的硬编码参数（前缀格式、CRM parser 路径等）迁移到 YAML 配置
   - 定义 `DialogueDatasetAdapter` 接口

4. **【低优先级】建立 Schema 版本管理**
   - 在 `save_sgd_to_directory` 中自动生成 schema changelog
   - 按版本号保存 schema 文件

### 5.3 最终目标架构

```
contextmind/
├── pipeline/
│   ├── run.py                    # 通用流程入口
│   ├── phase0_induction.py       # Phase 0：本体归纳
│   ├── phase1_consolidation.py   # Phase 1：schema 合并（现有 merge_ontologies）
│   ├── phase2_validation.py      # Phase 2：全量 schema 验证（待实现）
│   ├── phase3_extraction.py      # Phase 3：全量数据提取
│   └── phase4_export.py          # Phase 4：SGD 格式导出
├── adapters/
│   ├── base.py                   # DialogueDatasetAdapter 接口
│   ├── anyihua.py                # 安逸花适配器
│   └── sgd.py                   # 标准 SGD 格式适配器
└── configs/
    └── datasets/
        ├── base.yaml             # 公共配置
        └── anyihua_outbound.yaml # 安逸花外呼配置
```

这一架构使得**任何新的对话数据集只需要一个适配器 + 一个配置文件**，就可以完整走完知识库构建的 5 阶段流程，最终输出可供下游 TOD 系统（PyTOD、FnCTOD、DST 等）直接使用的 SGD 格式知识库。

---

## 附录：各阶段输出文件说明

| 阶段 | 输出文件 | 用途 |
|------|---------|------|
| Phase 0 | `chat_test_discovered_ontology.json` | LLM 归纳的原始本体 |
| Phase 1 | `chat_test_merged_ontology.json` | 预定义+归纳合并后的本体（含 source 标注） |
| Phase 1 | `chat_test_merged_schema.json` | SGD 格式的合并 schema（供 Phase 2/3 使用） |
| Phase 2 *(待实现)* | `chat_test_schema_validation_report.json` | 每个 schema 项的覆盖率与可靠性评估 |
| Phase 2 *(待实现)* | `chat_test_validated_schema.json` | 通过验证的最终 schema |
| Phase 3 | `chat_test_extraction_report.json` | 提取统计报告 |
| Phase 3 | `chat_test_extraction_report.md` | 人类可读报告（含对比+合并本体） |
| Phase 4 | `anyihua_sgd_extracted/schema.json` | 最终 SGD schema（供 TOD 系统使用） |
| Phase 4 | `anyihua_sgd_extracted/dialogues_*.json` | SGD 格式对话数据 |
| Phase 4 | `anyihua_sgd_extracted/README.md` | 数据集说明文档 |
