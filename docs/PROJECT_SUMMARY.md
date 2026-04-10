# ContextMind 项目总结

> **版本**：v0.3.0 · 2026-04-10

---

## 目录

1. [项目概述](#1-项目概述)
2. [整体架构](#2-整体架构)
3. [模块详解](#3-模块详解)
4. [PyTOD 代码生成算法](#4-pytod-代码生成算法)
5. [已有能力与已知问题](#5-已有能力与已知问题)

---

## 1. 项目概述

**ContextMind** 是一个以 LLM 驱动的 **上下文工程（Context Engineering）** Python 框架，目标是以最低代价将任意业务对话场景接入 LLM，并获得结构化上下文（槽位值、意图识别、状态追踪）。

框架分三步：**知识库构建 → Schema 数据生成 → 算法执行**，统一由 `ContextPipeline`（`pipeline.py`）串联。

**环境**：Python 3.8+，LLM 接入通过 `AdkLLMClient`（基于 Google ADK + LiteLLM），支持所有 OpenAI 兼容接口，配置来自 `.env`（`LLM_API_KEY / LLM_BASE_URL / LLM_MODEL`）。

---

## 2. 整体架构

```
原始对话数据
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ Step 1  Knowledge（知识库构建）                           │
│   GenericDialogueDiscoverer → SchemaSynthesizer          │
│   输出：schema.json（SGD ServiceSchema 格式）            │
└─────────────────────────────────────────────────────────┘
    │
    ▼ schema.json
┌─────────────────────────────────────────────────────────┐
│ Step 2  SchemaBuilder（Schema 数据生成，可选）            │
│   TestCaseGenerator → [4 种代码生成算法]                 │
│   输出：*_pytod_apis.py / *_fnctod_domain.json           │
└─────────────────────────────────────────────────────────┘
    │
    ▼ schema + apis
┌─────────────────────────────────────────────────────────┐
│ Step 3  Modes（算法执行）                                 │
│   DST │ FnCTOD │ Evolve │ PyTOD（AP → EE → DM）         │
└─────────────────────────────────────────────────────────┘
    │
    ▼
结构化上下文（槽位、意图、状态、程序执行结果）
```

### 模块依赖关系

```
contextmind/
├── infra/              ← 最底层（无上层依赖）
│   ├── llm_client.py   # AdkLLMClient / LLMConfig
│   ├── logger.py       # 结构化日志
│   ├── embedding.py    # 向量嵌入（Evolve 模式用）
│   └── data_models.py
│
├── knowledge/          ← 仅依赖 infra
│   ├── builder.py      # KnowledgeBaseBuilder
│   ├── discoverer.py   # GenericDialogueDiscoverer
│   ├── synthesizer.py  # SchemaSynthesizer
│   └── normalizer.py   # 5 种输入格式归一化
│
├── modes/              ← 依赖 infra；不依赖 knowledge/schema_builder
│   ├── dst/            # DialogueStateTracker
│   ├── fnctod/         # FnCTODTracker
│   ├── evolve/         # EvolveApp
│   └── pytod/          # AdkPyTODTracker + ExecutionEngine
│
├── schema_builder/     ← 依赖 infra + modes.pytod.schemas
│   ├── builder.py      # SchemaDataBuilder（orchestrator）
│   └── pytod/
│       ├── testcase/   # TestCaseGenerator（无 codegen 依赖）
│       └── codegen/    # 4 种代码生成算法（loop/alpha/sstar/ctree）
│
└── pipeline.py         ← 顶层（依赖所有模块）
```

### 各算法的步骤依赖

| 算法 | Step 1 知识库 | Step 2 Schema 生成 | Step 3 执行 |
|------|:-----------:|:-----------------:|:----------:|
| DST | 可选 | 不需要 | ✅ |
| FnCTOD | 可选 | 不需要 | ✅ |
| PyTOD | 可选 | 可选 | ✅ |
| Evolve | 不需要 | 不需要 | ✅ |

---

## 3. 模块详解

### 3.1 知识库构建（Knowledge）

**文件**：`contextmind/knowledge/`  **输入**：任意格式对话数据  **输出**：`schema.json`（SGD ServiceSchema）

`normalizer.py` 支持 5 种输入格式：chat_test / SGD / 字符串列表 / 坐席拼接文本 / 纯文本列表。

**两阶段处理**：`GenericDialogueDiscoverer`（LLM 开放式发现意图/槽位/事实，`langextract` 原文溯源）→ `SchemaSynthesizer`（汇总结果，LLM 生成规范 SGD JSON）。

关键行为：每条对话独立合成，结果经 `_merge_service_list()` 归并；合并 2+ schema 时 `SchemaSynthesizer.refine()` 做 LLM 语义去重（总条目 ≤ 5 跳过）；发现中间结果持久化为 `discovery_raw.json`（供 `testcase/kb_loader.py` 使用）；支持 `build_async()` / `build_dataset_async()`。

---

### 3.2 Schema 数据生成（SchemaBuilder）

**文件**：`contextmind/schema_builder/`  **输入**：`schema.json`  **输出**：`*_pytod_apis.py` / `*_fnctod_domain.json`

**5 阶段生成**：Phase 1 解析 schema → Phase 2 加载/生成 `TestCaseItem`（可预生成：`prebuild_test_cases(workers=N)`，intent 级并行）→ Phase 3 LLM 初始函数体生成 → Phase 4 测试验证+迭代修复（算法差异点）→ Phase 5 组装 `.py` + `validate_pytod_apis_source()` 模块健康校验。

Phase 5 中失败函数由 `replace_function_in_source()` 替换为安全 stub，不影响整体模块加载。4 种算法（loop/alpha/sstar/ctree）共享相同框架，差异在 Phase 3-4。

---

### 3.3 算法执行（Modes）

所有 Tracker 实现 `BaseTracker` 协议，统一暴露 `async process_turn(user_input) -> dict`，返回 `response / context / cumulative_context / program_text`。

| 模式 | 原理 | 参考 |
|------|------|------|
| **DST** | 结构化 prompt → LLM 提取槽位-值对，无预生成依赖 | — |
| **FnCTOD** | schema 转 tool_use，LLM function calling 输出结构化槽位 | [ACL 2024](https://arxiv.org/pdf/2402.10466) |
| **Evolve** | 每轮动态提取知识写入记忆库，向量检索支持跨轮召回 | [ThetaEvolve](https://arxiv.org/pdf/2511.23473) |
| **PyTOD** | AP（动作计划代码生成）→ EE（真实 API 执行）→ DM（结果转自然语言） | [Apple 2024](https://arxiv.org/pdf/2508.15456) |

**PyTOD 关键实现细节**：
- `top_k_intents > 0`：`_score_intents_for_query()` 用加权 TF-IDF 评分（name×3 / desc×2 / slots×1.5，IDF 加权，已调用惩罚×0.2）动态筛选最相关意图入 prompt
- `load_pytod_api_module()`：加载时将有 bug 的函数（`NameError/UnboundLocalError`）包装为安全 stub，`_is_stub_only_result` 过滤 stub 结果不传入 AP 上下文

**统一入口**（`pipeline.py`）：

```python
pipeline = ContextPipeline(llm_client=AdkLLMClient(), mode="pytod", scene_name="银行外呼")
pipeline.build_kb(dialogues=my_dialogues, scene_name="银行外呼")   # Step 1（或 load_kb）

@pipeline.register_api("verify_identity")
def verify_identity(customer_name: str) -> dict:
    return {"status": "success", "verified": True}

result = await pipeline.process_turn("我是李明，想查贷款额度")    # Step 3
```

---

## 4. PyTOD 代码生成算法

**文件**：`contextmind/schema_builder/pytod/codegen/`

四种算法共享 5-Phase 框架（Phase 1-2 相同，差异在 Phase 3-4）。**验证规则**：调用无异常 + 返回 `dict` + `status=="success"` + `expected_keys` 全部存在 + `expected_values` 宽松匹配。**probe 机制**（loop/alpha/sstar 共用）：`best_code` 仅在通过率提升时更新，`probe_code` 无条件推进，避免 LLM 修复死循环。

| 算法 | 核心机制 | max_iter | LLM 调用 | 推荐场景 |
|------|---------|:--------:|:-------:|---------|
| **Loop** | 线性修复，probe 推进 | 3 | 低 | 快速基准 |
| **Alpha** | +反思 (R) + 失败分析 (A) + 收敛重启（连续 2 轮无提升则重新反思） | 10 | 中 | 普通复杂度 |
| **S\*** | 3 种思维模式并行生成候选 → execution trace 修复 → LLM 锦标赛裁判（区分性输入） | 10 | 高 | 高质量要求 |
| **CTree** | UCB 树搜索（`C≈√2`），每个失败用例独立扩展子节点，per-case 修复粒度最细 | 10 | 中高 | 复杂/多失败点 |

- **Alpha** 来源：[AlphaCodium](https://arxiv.org/abs/2401.08500)（2024）
- **S\*** 来源：[S* Test Time Scaling](https://arxiv.org/abs/2502.14382)（2025）
- **CTree** 来源：[CodeTree](https://arxiv.org/abs/2411.04329)（2024）

---

## 5. 已有能力与已知问题

### ✅ 已有能力

**知识库构建**：5 种输入格式归一化；LLM 开放式发现（`langextract` 原文溯源）；两阶段 Discovery→Synthesis 流水线；per-dialogue 独立合成+归并；语义去重（`refine()`）；异步构建（`build_async()`）；中间结果持久化（`discovery_raw.json`）。

**Schema 数据生成**：schema → `*_pytod_apis.py` / `*_fnctod_domain.json`；4 种代码生成算法（`--generator loop/alpha/sstar/ctree`）；测试用例预生成共享（`*_test_cases.json`）；intent 级 + schema 级双层并行（`--workers`）；Phase 5 模块健康校验 + 失败函数 stub 降级；`--kb-dir` KB 上下文辅助生成。

**对话执行**：DST（零样本槽位提取）/ FnCTOD（function calling 强约束输出）/ PyTOD（AP→EE→DM 真实 API 执行）/ Evolve（动态记忆+向量检索）；跨轮累积上下文；`top_k_intents` TF-IDF 动态意图筛选；安全 stub 自动包装。

**基础设施**：统一 `AdkLLMClient`（LiteLLM，支持所有 OpenAI 兼容接口）；`.env` 配置驱动；结构化日志；向量嵌入；`ContextPipeline` 统一入口；Gradio Web UI / CLI / 批量测试 / 评测框架（`benchmark/`）。

---

### ⚠️ 已知问题

| 类型 | 问题 | 说明 / 缓解 |
|------|------|------------|
| 功能缺失 | FnCTOD Schema Builder 未实现 | `schema_builder/fnctod/` 为 stub，无 LLM 驱动逻辑 |
| 功能缺失 | Evolve 不读取 schema | 无法利用知识库意图/槽位定义 |
| 功能缺失 | PyTOD INTENT_REGISTRY 与 schema 手动同步 | 手写 API 时需人工保持一致 |
| 安全 | Phase 4 无沙箱隔离 | 生成代码直接在进程内执行；已有 Phase 5 stub 降级缓解 |
| 性能 | 代码生成慢（多轮 LLM） | `--workers N` 并行；100 intent 仍需数小时 |
| 性能 | Discovery 阶段串行 | `build()` 内 per-dialogue 顺序处理，暂无并发 |
| 性能 | Evolve embedding 为可选依赖 | 未安装 `sentence-transformers` 退化为关键词检索 |
| 工程 | 集成测试缺失 | 现有 pytest 仅覆盖单元测试；端到端需真实 LLM API |
| 工程 | 错误处理不一致 | 各模块混用 raise / return None / 警告继续 |
| 工程 | 配置管理分散 | max_iterations 等超参散落在 CLI / Builder / Synthesizer 各层 |
| 工程 | benchmark 框架不完整 | 目录存在但评测覆盖不全，缺少标准化报告输出 |

---

