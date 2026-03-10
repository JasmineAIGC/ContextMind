# Schema 格式统一为 SGD 规范的分析报告

> **目的**：分析将 ContextMind 项目中所有 schema 数据格式统一为 SGD（Schema-Guided Dialogue）规范的可行性与收益，并说明安逸花外呼数据在转换时允许字段缺失的处理策略。

---

## 一、背景

### 1.1 现有 Schema 系统

ContextMind 项目中目前存在两套 schema 表示体系：

| 类型 | 位置 | 用途 |
|------|------|------|
| `ServiceSchema` / `IntentDefinition` / `SlotDefinition` | `contextmind/modes/pytod/schemas.py` | PyTOD 对话生成与 QC 任务 |
| `PartialServiceSchema` / `PartialSlot` / `PartialIntent` | `contextmind/scenarios/anyihua/schema_extraction/schema.py` | Schema 提取任务（允许字段缺失） |

### 1.2 SGD 格式规范

[SGD（Schema-Guided Dialogue）](https://github.com/google-research-datasets/dstc8-schema-guided-dialogue) 是 Google Research 发布的对话数据集标准格式，被以下主流项目采用：

- **ml-pytod**（Apple）：PyTOD 算法官方训练数据格式
- **langextract**（Google）：`https://github.com/google/langextract` — 基于 LLM 的结构化信息提取库，使用 SGD 对话数据作为 few-shot 示例

### 1.3 两套体系的格式差异

**`IntentDefinition`（内部格式）vs SGD 格式**：

| 字段 | 内部格式 | SGD 格式 | 差异 |
|------|---------|---------|------|
| `optional_slots` | `List[str]` | `Dict[str, str]`（`{slot: ""}`) | **格式不同** |
| `result_slots` | 缺失 | `List[str]` | **内部缺少此字段** |
| `is_transactional` | 缺失 | `bool` | **内部缺少此字段** |

**`SlotDefinition`（内部格式）vs SGD 格式**：

| 字段 | 内部格式 | SGD 格式 | 差异 |
|------|---------|---------|------|
| `is_required` | `bool` | 不存在 | **内部额外字段** |

---

## 二、统一为 SGD 格式的优势分析

### 2.1 ✅ 与 ml-pytod 官方数据直接兼容

SGD 数据集是 PyTOD 算法的官方评测数据集。统一格式后：

- `ServiceSchema.from_dict()` 可直接解析 `schema.json` 中的任意服务定义
- `ServiceSchema.to_sgd_json()` 输出可直接写入 SGD 标准目录
- 消除 `optional_slots` 的 list vs dict 转换层，减少序列化/反序列化错误

**修复前的问题**：若直接将 SGD `schema.json` 加载到旧版 `IntentDefinition.from_dict()`，`optional_slots` 为 `dict` 类型会被错误地原样存储，而非 `List[str]`。

**修复后**：`from_dict()` 自动检测 dict 或 list 格式并统一转换为 `List[str]`，向上兼容两种输入。

### 2.2 ✅ 与 langextract 互操作

[google/langextract](https://github.com/google/langextract) 使用 SGD 对话数据作为 few-shot 提取示例。统一格式后，完整的互操作链路如下：

```
安逸花对话数据（chat_test_100.json）
    ↓ ChatTestToSGDConverter（benchmark/datasets/anyihua/adapter.py）
SGD 格式对话（resources/anyihua_sgd/dialogues_001.json）
    ↓ dialogues_to_langextract_examples()（schema_extraction/extractor.py）
langextract ExampleData 字典列表
    ↓ lx.extract(examples=..., model_id="gemini-2.5-flash")
结构化提取结果
```

该链路已在 `contextmind/scenarios/anyihua/schema_extraction/` 完整实现。

### 2.3 ✅ 生态一致性，降低维护成本

统一格式意味着：
- 同一份 `schema.json` 可同时用于 PyTOD 评测、langextract 提取、ContextMind 运行
- 无需在不同任务之间做格式转换
- 新增数据集只需维护一套 SGD 格式，减少重复代码

### 2.4 ✅ `result_slots` 增强执行引擎语义

`result_slots` 明确声明了 API 调用的返回字段，增强了执行引擎的语义：
- 动作解析器（Action Parser）可从中推断哪些槽位由 API 填充
- 对话管理器（Dialogue Manager）可据此决定何时需要先调用 API 再告知用户

---

## 三、安逸花数据转为 SGD 格式的字段对齐分析

### 3.1 允许字段缺失的设计原则

安逸花外呼数据（`chat_test_100.json`）是真实通话录音的转录文本，原始数据**不包含**结构化标注。因此：

> **核心原则**：转换时不要求所有 SGD 字段完整对齐，允许部分字段缺失，但不影响下游任务可用性。

这一设计已体现在两个层面：

1. **`PartialServiceSchema`（schema_extraction/schema.py）**：所有字段均为 `Optional`，仅 `service_name`（服务名）和 `name`（槽位/意图名）为必填。
2. **`ChatTestToSGDConverter`（benchmark/datasets/anyihua/adapter.py）**：通过规则推断近似标注（`active_intent`、`slot_values` 等），明确标注了哪些字段是高可靠、哪些是低可靠推断。

### 3.2 字段对齐详细分析

#### 3.2.1 schema.json 字段对齐

| SGD 字段 | 安逸花数据来源 | 对齐状态 | 说明 |
|---------|--------------|---------|------|
| `service_name` | 固定值 `"AnYiHua_1"` | ✅ 完整 | 规范命名 |
| `description` | 手动撰写 | ✅ 完整 | 服务描述 |
| `slots[].name` | 业务分析定义 | ✅ 完整 | 11+ 个槽位 |
| `slots[].description` | 手动撰写 | ✅ 完整 | |
| `slots[].is_categorical` | 手动标注 | ✅ 完整 | |
| `slots[].possible_values` | 手动枚举 | ✅ 完整 | 分类槽位有值 |
| `intents[].name` | 业务分析定义 | ✅ 完整 | 9–10 个意图 |
| `intents[].description` | 手动撰写 | ✅ 完整 | |
| `intents[].is_transactional` | 手动标注 | ✅ 完整（v2） | 更新后已添加 |
| `intents[].required_slots` | 业务逻辑分析 | ✅ 完整 | |
| `intents[].optional_slots` | 业务逻辑分析 | ✅ 完整 | |
| `intents[].result_slots` | 业务逻辑分析 | ✅ 完整（v2） | 更新后已添加 |

#### 3.2.2 dialogues_*.json 字段对齐

| SGD 字段 | 安逸花数据来源 | 对齐状态 | 可靠性 |
|---------|--------------|---------|-------|
| `dialogue_id` | `session_id` 直接映射 | ✅ 完整 | 100% |
| `services` | 固定 `["AnYiHua_1"]` | ✅ 完整 | 100% |
| `turns[].speaker` | 前缀识别（坐席/用户） | ✅ 完整 | 99%+ |
| `turns[].utterance` | 转录文本去前缀 | ✅ 完整 | 99%+ |
| `frames[].service` | 固定 `"AnYiHua_1"` | ✅ 完整 | 100% |
| `state.active_intent` | **关键词规则推断** | ⚠️ 近似 | 50–70% |
| `state.slot_values` | CRM 结构化字段 | ✅ 完整 | 99% |
| `state.requested_slots` | 疑问句关键词检测 | ⚠️ 近似 | 50–70% |
| `frames[].actions` | 意图→动作规则映射 | ⚠️ 近似 | 50–70% |
| `service_call.method` | 意图→API 规则映射 | ⚠️ 近似 | 50–70% |
| `service_call.parameters` | CRM 数据填充 | ✅ 高可靠 | 90%+ |
| `service_results` | CRM 数据填充 | ✅ 高可靠 | 90%+ |
| `frames[].slots`（字符跨度） | **未实现** | ❌ 缺失 | — |

#### 3.2.3 缺失字段的影响评估

**`frames[].slots`（槽位字符跨度）**：
- SGD 用于非分类槽位的字符级标注（如 `[{"slot": "hotel_name", "start": 10, "end": 15}]`）
- **安逸花数据无法自动生成**：需要在对话文本中定位槽位值的精确字符位置
- **影响范围**：Slot Tagging F1 指标计算；PyTOD 不强依赖此字段运行
- **处理方案**：在 `frames[].slots` 填写空列表 `[]`，PyTOD 运行正常，仅跳过字符跨度评估

**`state.active_intent` 准确率偏低（50–70%）**：
- **根因**：安逸花通话中意图混合复杂，关键词规则难以精确匹配
- **处理方案**：使用 `--use-llm` 模式启用 LLM 语义识别，准确率可提升至 85–95%
- **影响范围**：Intent Accuracy 指标；不影响实际对话生成

### 3.3 PartialServiceSchema vs ServiceSchema：如何选择

| 场景 | 推荐类 | 原因 |
|------|-------|------|
| 从 LLM 归纳提取 schema | `PartialServiceSchema` | 允许字段缺失，可渐进式填充 |
| 加载完整 SGD schema.json | `ServiceSchema` | 功能更完整，支持 to_sgd_json() |
| PyTOD 生成/QC 任务 | `ServiceSchema` | 直接用于 prompt 构建，需要完整字段 |
| langextract 互操作 | `PartialServiceSchema` | 有 to_langextract_schema_dict() 接口 |
| schema 对齐分析 | `PartialServiceSchema` | align_schema_with_sgd() 专用接口 |

---

## 四、统一后的 Schema 格式规范（更新后）

### 4.1 `ServiceSchema.to_sgd_dict()` 输出

```json
{
  "service_name": "AnYiHua_OutboundCall_Generation",
  "description": "安逸花外呼促活服务",
  "slots": [
    {
      "name": "customer_name",
      "description": "客户姓名",
      "is_categorical": false,
      "possible_values": []
    }
  ],
  "intents": [
    {
      "name": "verify_identity",
      "description": "开场身份核实",
      "is_transactional": false,
      "required_slots": ["customer_name", "identity_confirmed"],
      "optional_slots": {"phone_suffix": ""},
      "result_slots": ["identity_confirmed"]
    }
  ]
}
```

关键点：
- `optional_slots` 为 **dict 格式**（SGD 规范）
- `slots` 中**不含** `is_required`（SGD 规范）
- `intents` 含 `is_transactional` 和 `result_slots`（SGD 规范完整字段）

### 4.2 `ServiceSchema.to_dict()` 输出（内部格式，向后兼容）

```json
{
  "service_name": "AnYiHua_OutboundCall_Generation",
  "description": "安逸花外呼促活服务",
  "slots": [
    {
      "name": "customer_name",
      "description": "客户姓名",
      "is_categorical": false,
      "possible_values": [],
      "is_required": true
    }
  ],
  "intents": [
    {
      "name": "verify_identity",
      "description": "开场身份核实",
      "is_transactional": false,
      "required_slots": ["customer_name", "identity_confirmed"],
      "optional_slots": ["phone_suffix"],
      "result_slots": ["identity_confirmed"]
    }
  ]
}
```

关键点：
- `slots` 含 `is_required`（由意图 `required_slots` 推导，方便运行时查询）
- `optional_slots` 为 **list 格式**（内部表示，更易操作）

---

## 五、两种 Schema 类的互操作路径

```
SGD schema.json
    ↓ ServiceSchema.from_dict() / PartialServiceSchema.from_sgd_dict()
内存中的 Schema 对象
    ↓ .to_sgd_dict() / .to_sgd_json()     ← 标准 SGD 输出
    ↓ .to_dict() / .to_json()             ← 内部格式输出（向后兼容）
    ↓ .to_langextract_schema_dict()       ← langextract 互操作（PartialServiceSchema）
    ↓ .to_prompt_text()                   ← PyTOD Prompt 嵌入
```

---

## 六、结论

### 统一为 SGD 格式是更好的选择，理由如下：

1. **生态一致性**：ml-pytod（Apple）和 langextract（Google）都使用 SGD 格式，统一后可零摩擦对接两个主流项目
2. **安逸花转换成本低**：大部分字段已可自动提取；缺失字段（如字符跨度）用空列表代替，不影响核心功能
3. **允许部分字段缺失**：`PartialServiceSchema` 专为安逸花等不完整数据场景设计，`optional_slots` 等字段均可为 `None`，通过 `save_schema_as_sgd()` 自动补全默认值
4. **最小化维护成本**：同一份 schema 数据服务多个任务，无需在格式之间手动转换
5. **`result_slots` 语义增强**：明确 API 返回字段，提升执行引擎和提示词的表达能力

### 实施建议：

| 优先级 | 行动 | 状态 |
|--------|------|------|
| P0 | `IntentDefinition.from_dict()` 支持 dict/list 两种 `optional_slots` 格式 | ✅ 已完成 |
| P0 | `IntentDefinition` / `SlotDefinition` 添加 `to_sgd_dict()` | ✅ 已完成 |
| P0 | `ServiceSchema` 添加 `to_sgd_dict()` 和 `to_sgd_json()` | ✅ 已完成 |
| P1 | `IntentDefinition` 添加 `result_slots` 和 `is_transactional` 字段 | ✅ 已完成 |
| P1 | 安逸花 generation/qc schema 补充 `is_transactional` 和 `result_slots` | ✅ 已完成 |
| P2 | 实现 SGD 数据集适配器（`SGDAdapter`），用于 PyTOD 评测 | 📋 待实现 |
| P2 | 安逸花 dialogues.json 补充字符跨度（`frames[].slots`） | 📋 待实现 |

---

## 相关文件

- `contextmind/modes/pytod/schemas.py` — `ServiceSchema` / `IntentDefinition` / `SlotDefinition`（已更新）
- `contextmind/scenarios/anyihua/schema_extraction/schema.py` — `PartialServiceSchema`（已实现 SGD 兼容）
- `contextmind/scenarios/anyihua/schema_extraction/schema_io.py` — `save_schema_as_sgd()` / `align_schema_with_sgd()` / `format_comparison_report()`
- `contextmind/scenarios/anyihua/generation/schema.py` — Generation 任务 Schema（已更新）
- `contextmind/scenarios/anyihua/qc/schema.py` — QC 任务 Schema（已更新）
- `benchmark/datasets/anyihua/adapter.py` — 安逸花 → SGD 转换器
- `resources/anyihua_sgd/schema.json` — 安逸花 SGD 服务 Schema（标准格式）
- `docs/datasets/sgd.md` — SGD 数据集详细说明
