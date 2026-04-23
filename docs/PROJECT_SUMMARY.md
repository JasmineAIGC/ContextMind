# ContextMind 架构概览

> **版本**：v0.3.0

---

## 整体架构

```
用户对话数据
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 第一步：Knowledge（知识库构建）                                       │
│   GenericDialogueDiscoverer → SchemaSynthesizer → schema.json       │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼ schema.json
┌─────────────────────────────────────────────────────────────────────┐
│ 第二步：SchemaBuilder（Schema 数据生成）         [可选]              │
│   TestCaseGenerator → [4种代码生成算法] → xxx_pytod_apis.py         │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼ schema + apis
┌─────────────────────────────────────────────────────────────────────┐
│ 第三步：Modes（算法执行）                                             │
│   ┌────────┐ ┌─────────┐ ┌────────┐ ┌─────────────────────────┐    │
│   │  DST   │ │ FnCTOD  │ │ Evolve │ │  PyTOD（AP→EE→DM）      │    │
│   └────────┘ └─────────┘ └────────┘ └─────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
结构化上下文（槽位、意图、状态、程序执行结果）
```

### 模块依赖关系

```
contextmind/
├── infra/              ← 最底层（无上层依赖）
│   ├── llm_client.py   ← AdkLLMClient / LLMConfig
│   ├── logger.py
│   └── embedding.py    ← 向量嵌入（Evolve 语义检索）
│
├── knowledge/          ← 仅依赖 infra
│   ├── builder.py      ← KnowledgeBaseBuilder
│   ├── discoverer.py   ← GenericDialogueDiscoverer
│   ├── synthesizer.py  ← SchemaSynthesizer
│   └── normalizer.py   ← 5种输入格式归一化
│
├── modes/              ← 依赖 infra；不依赖 knowledge/schema_builder
│   ├── dst/            ← DialogueStateTracker
│   ├── fnctod/         ← FnCTODTracker
│   ├── evolve/         ← EvolveEngine + EvolveApplication
│   └── pytod/          ← AdkPyTODTracker + ExecutionEngine
│
├── schema_builder/     ← 依赖 infra + modes.pytod.schemas
│   ├── builder.py      ← SchemaDataBuilder
│   └── pytod/
│       ├── testcase/   ← TestCaseGenerator
│       └── codegen/    ← 4种代码生成算法（loop / alpha / sstar / ctree）
│
└── pipeline.py         ← 顶层（依赖所有模块）
```

---

## 四种执行模式

### DST — 对话状态追踪
- **文件**：`contextmind/modes/dst/`
- 零样本 LLM 槽位提取，不依赖第一/二步
- 输出：`{"slot_name": "value", ...}`

### FnCTOD — 函数调用式状态追踪
- **文件**：`contextmind/modes/fnctod/`
- **论文**：[ACL 2024 - LLMs as Zero-shot DST through Function Calling](https://arxiv.org/pdf/2402.10466)
- schema 中意图/槽位转为 LLM function calling 工具定义，输出格式更规范

### Evolve — 演化式长对话记忆
- **文件**：`contextmind/modes/evolve/`
- **论文**：[ThetaEvolve](https://arxiv.org/pdf/2511.23473)
- 动态知识提取 + 语义记忆检索，无需预构建知识库

### PyTOD — 可编程任务型对话
- **文件**：`contextmind/modes/pytod/`
- **论文**：[PyTOD: Programmable TOD with Execution Feedback](https://arxiv.org/pdf/2508.15456)
- 三组件架构：Action Parser → Execution Engine → Dialogue Manager
- LLM 输出 Python 动作计划，ExecutionEngine 执行真实业务 API

---

## PyTOD 代码生成算法

`contextmind/schema_builder/pytod/codegen/` 实现四种 schema → Python API 代码的生成算法，均基于 5-Phase 框架：

```
Phase 1  解析 schema
Phase 2  加载/生成测试用例
Phase 3  LLM 初始函数体生成     ← 算法差异点
Phase 4  验证 + 迭代修复        ← 算法差异点
Phase 5  组装 .py + 健康校验
```

| 算法 | 迭代结构 | 多样性机制 | LLM 调用量 | 推荐场景 |
|------|---------|-----------|-----------|---------|
| **Loop** | 线性 | probe 推进 | 低 | 快速基准 |
| **Alpha** | 线性+重启 | probe + 收敛重启 | 中 | 普通复杂度 |
| **S\*** | 并行+锦标赛 | 多思维模式 + 区分性测试 | 高 | 高质量要求 |
| **CTree** | 树形（UCB） | 分支扩展 | 中偏高 | 复杂/多失败点 |

**probe 推进机制**（Loop/Alpha/S* 共用）：`best_code` 仅在通过率提升时更新；`probe_code` 无条件推进到最新状态，避免每轮 LLM 看到相同代码死循环。

---

## 已知问题与局限性

| 类型 | 问题 | 说明 |
|------|------|------|
| 🔴 缺失 | FnCTOD Schema Builder 未实现 | `schema_builder/fnctod/` 为 stub，无 LLM 驱动逻辑 |
| 🔴 缺失 | Evolve 不读 schema.json | 无法利用知识库中的意图/槽位定义 |
| 🟡 限制 | 代码执行无沙箱隔离 | Phase 4 验证直接执行 LLM 生成代码，存在安全风险 |
| 🟡 限制 | PyTOD prompt 过长 | 意图数量大时超出 context 窗口（`top_k_intents` 可缓解） |
| 🟡 性能 | 代码生成速度慢 | 每 intent 多轮 LLM 调用，100 个 intent 可能需数小时 |
| 🟠 工程 | 集成测试覆盖不足 | 端到端测试需真实 LLM API，无 mock 方案 |

---

## 相关文档

- [文档中心](README.md) — 三步框架概述与导航
- [快速开始](guides/quick-start.md) — 安装与第一个示例
- [API 参考](reference/api-reference.md)
- [Benchmark 评测框架](reference/benchmark.md)
