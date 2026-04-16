# ContextMind 架构图

> **版本**：0.3.0 | **最后更新**：2026-04-01

本文档从四个视角描述 ContextMind 框架架构：整体框架、端到端数据流、PyTOD 算法细节、Evolve 记忆系统。

---

## 目录

1. [整体框架](#1-整体框架)
2. [模块说明](#2-模块说明)
3. [端到端调用流程](#3-端到端调用流程)
4. [PyTOD 执行流程](#4-pytod-执行流程)
5. [Evolve 记忆架构](#5-evolve-记忆架构)
6. [算法对比](#6-算法对比)
7. [项目目录结构](#7-项目目录结构)

---

## 1. 整体框架

ContextMind 的核心设计是**三步框架**，由 `ContextPipeline` 作为统一入口串联，不同算法对各步骤的依赖程度不同。

```mermaid
flowchart TD
    IN([原始对话数据])

    subgraph S1["① 知识库构建  ·  contextmind/knowledge"]
        D[Discoverer\n槽位 / 意图发现] --> SY[Synthesizer\nSchema 合成]
    end

    SCH[(schema.json\nSGD 格式)]

    subgraph S2["② Schema 数据生成  ·  contextmind/schema_builder"]
        G[SchemaDataBuilder\n5 阶段 LLM 流水线]
    end

    API[(pytod_apis.py\nAPI 函数代码)]

    subgraph S3["③ 算法执行  ·  contextmind/modes"]
        PT[PyTOD\nAP → EE → DM]
        DS[DST\n槽位追踪]
        FN[FnCTOD\n函数调用]
        EV[Evolve\n记忆进化]
    end

    OUT([结构化上下文输出])

    IN      --> S1
    SY      --> SCH
    SCH     --> S2
    G       --> API
    SCH     --> S3
    API     --> PT
    S3      --> OUT

    classDef s1   fill:#DBEAFE,stroke:#3B82F6,color:#1D4ED8
    classDef s2   fill:#D1FAE5,stroke:#10B981,color:#065F46
    classDef s3   fill:#FEF3C7,stroke:#F59E0B,color:#92400E
    classDef art  fill:#EDE9FE,stroke:#7C3AED,color:#4C1D95
    classDef io   fill:#F9FAFB,stroke:#9CA3AF,color:#374151

    class S1 s1
    class S2 s2
    class S3 s3
    class SCH,API art
    class IN,OUT io
```

---

## 2. 模块说明

下表列出 `contextmind/` 下各子包的核心类与职责：

| 子包 | 核心类 | 职责 |
|------|--------|------|
| `pipeline.py` | `ContextPipeline` | 统一三步框架入口，管理 Tracker 生命周期 |
| `infra/llm_client.py` | `AdkLLMClient` | LLM 统一接入（OpenAI / Qwen / 本地 vLLM） |
| `infra/embedding.py` | `EmbeddingClient` | 文本向量化，支持 OpenAI / SentenceTransformer |
| `knowledge/builder.py` | `KnowledgeBaseBuilder` | 两阶段（发现 + 合成）知识库构建入口 |
| `knowledge/discoverer.py` | `GenericDialogueDiscoverer` | LLM + langextract 开放式槽位 / 意图发现 |
| `knowledge/synthesizer.py` | `SchemaSynthesizer` | 将发现结果合成为 SGD ServiceSchema |
| `knowledge/normalizer.py` | `normalize_dialogues` | 5 种输入格式归一化为统一对话列表 |
| `schema_builder/builder.py` | `SchemaDataBuilder` | Schema → 算法专用数据（PyTOD / FnCTOD） |
| `schema_builder/pytod/` | `PyTODApiCodeGenerator` | 5 阶段 LLM 生成 + 验证 + 修复 API 函数代码 |
| `modes/base.py` | `BaseTracker` | 所有追踪器的共享协议（结构子类型） |
| `modes/pytod/tracker.py` | `AdkPyTODTracker` | PyTOD 三步（AP / EE / DM）流程编排 |
| `modes/pytod/execution_engine.py` | `ExecutionEngine` | 安全执行 PyTOD 程序语句（无 eval，含模糊匹配） |
| `modes/pytod/schemas.py` | `ServiceSchema` | SGD Schema 数据模型与加载工具 |
| `modes/dst/tracker.py` | `DialogueStateTracker` | 基于 ADK LlmAgent 的槽位状态追踪 |
| `modes/fnctod/tracker.py` | `FnCTODTracker` | ADK 原生函数调用式对话状态追踪 |
| `modes/fnctod/function_manager.py` | `FunctionManager` | Schema 槽位 → ADK FunctionTool 转换 |
| `modes/evolve/core/engine.py` | `EvolveEngine` | 演化式上下文优化引擎（AlphaEvolve + ThetaEvolve） |
| `scenarios/registry.py` | `ScenarioRegistry` | YAML 驱动的场景配置注册与查询 |
| `ui/components.py` | — | Gradio UI 布局与事件绑定 |

---

## 3. 端到端调用流程

展示从 `ContextPipeline` 到各模块的完整调用链：

```mermaid
sequenceDiagram
    autonumber
    actor User as 调用方
    participant CP as ContextPipeline
    participant KB as KnowledgeBaseBuilder
    participant SB as SchemaDataBuilder
    participant TR as Tracker
    participant LLM as AdkLLMClient

    Note over User,LLM: ① 知识库构建（可选，一次性离线）
    User->>CP: build_kb(dialogues, scene_name)
    CP->>KB: build(dialogues)
    KB->>LLM: 发现 Prompt（逐轮对话）
    LLM-->>KB: 槽位 + 意图（YAML）
    KB->>LLM: 合成 Prompt
    LLM-->>KB: schema.json（SGD JSON）
    KB-->>CP: schema_dict
    CP-->>User: 知识库已就绪

    Note over User,LLM: ② Schema 数据生成（PyTOD 可选，一次性离线）
    User->>SB: build_pytod_apis(schema_path)
    SB->>LLM: 生成测试用例（Phase 2）
    LLM-->>SB: TestCaseItem[]
    SB->>LLM: 生成函数体（Phase 3）
    LLM-->>SB: Python 函数代码
    SB->>SB: 验证 + 迭代修复（Phase 4）
    SB-->>User: xxx_pytod_apis.py

    Note over User,LLM: ③ 在线对话（每轮）
    User->>CP: process_turn("用户话语")
    CP->>TR: process_turn(utterance)
    TR->>LLM: AP / DST Prompt
    LLM-->>TR: 程序语句 / 槽位 JSON
    TR->>TR: Execution Engine（PyTOD）
    TR->>LLM: DM Prompt（PyTOD）
    LLM-->>TR: 自然语言回复
    TR-->>CP: {response, context, program_text}
    CP-->>User: 结构化上下文结果
```

---

## 4. PyTOD 执行流程

PyTOD 将任务型对话建模为**程序执行**问题，每轮对话经历三个串行步骤：

```mermaid
flowchart TD
    U([用户话语])

    subgraph AP["① Action Parser  —  ADK LlmAgent"]
        AP1[构建 AP 提示词\nSchema 签名 + 对话历史]
        AP2[LLM 生成 PyTOD 程序\nx1 = func · Hint · say]
        AP1 --> AP2
    end

    subgraph EE["② Execution Engine  —  纯 Python，无 LLM"]
        EE1[AST 解析程序语句]
        EE2[函数分发\n精确匹配 + Fuzzy 匹配]
        EE3[调用注册 API 函数\npytod_apis.py]
        EE4[处理 say / Hint / confirm]
        EE1 --> EE2 --> EE3 --> EE4
    end

    subgraph DM["③ Dialogue Manager  —  ADK LlmAgent"]
        DM1[注入执行结果\nsay 输出 + API 返回值]
        DM2[LLM 生成自然语言回复]
        DM1 --> DM2
    end

    OUT([系统回复 + 上下文状态])

    U   --> AP1
    AP2 --> EE1
    EE4 --> DM1
    DM2 --> OUT

    classDef ap fill:#DBEAFE,stroke:#3B82F6,color:#1D4ED8
    classDef ee fill:#D1FAE5,stroke:#10B981,color:#065F46
    classDef dm fill:#FEF3C7,stroke:#F59E0B,color:#92400E

    class AP ap
    class EE ee
    class DM dm
```

**关键设计点：**

- **ExecutionEngine** 不使用 `eval()`，通过 AST 解析安全执行程序语句
- **Fuzzy 匹配**（`difflib`，阈值 0.6）可纠正 AP 幻觉出的近似函数名
- **stub 过滤**：schema 自动注册的 stub 函数结果（`{"status":"success","intent":"..."}` ）不注入 DM，避免歧义
- **say() 机制**：AP 通过 `say(x1.field)` 向 DM 传递需要口播的关键字段，DM 不直接读取 API 原始结果

---

## 5. Evolve 记忆架构

Evolve 基于 **AlphaEvolve + ThetaEvolve** 双算法，通过会话记忆和长期记忆实现上下文持续优化：

```mermaid
flowchart TD
    U([用户输入])
    OUT([上下文优化结果])
    ADK["ADK 基础设施\nSessionService · MemoryService"]

    subgraph PIP["Pipeline  —  上下文处理流水线"]
        P1[InputPreprocessor] --> P2[ContextRetriever]
        P2 --> P3[ContextCompressor] --> P4[ContextReorderer]
    end

    subgraph MEM["Memory  —  记忆子系统"]
        M1[MemoryBank\n记忆存储库]
        M2[MemoryExtractor\nLLM 知识提取]
        M3[MemoryRetriever\n语义向量检索]
        M4[FitnessEvaluator\n适应度评估]
    end

    subgraph EVO["Evolution  —  演化系统"]
        E1[EvolutionaryUpdater\nThetaEvolve]
        E2[FeedbackCollector\nAlphaEvolve]
    end

    U   --> P1
    P2  -->|检索| M3
    M3  -->|返回| P2
    M1  --> E1
    E1  -->|更新| M1
    ADK --> M1
    P4  --> OUT

    classDef pip fill:#DBEAFE,stroke:#3B82F6,color:#1D4ED8
    classDef mem fill:#D1FAE5,stroke:#10B981,color:#065F46
    classDef evo fill:#FEF3C7,stroke:#F59E0B,color:#92400E
    classDef adk fill:#F3F4F6,stroke:#9CA3AF,color:#374151

    class PIP pip
    class MEM mem
    class EVO evo
    class ADK adk
```

---

## 6. 算法对比

### 步骤依赖

| 算法 | ① 知识库 | ② Schema 生成 | ③ 算法执行 |
|------|:--------:|:------------:|:---------:|
| **DST** | 可选 | 不需要 | ✅ 必须 |
| **FnCTOD** | 可选 | 不需要 | ✅ 必须 |
| **PyTOD** | 可选 | 可选 | ✅ 必须 |
| **Evolve** | 不需要 | 不需要 | ✅ 必须 |

### 技术特性

| 维度 | DST | FnCTOD | PyTOD | Evolve |
|------|-----|--------|-------|--------|
| **输出类型** | 槽位状态 JSON | 函数调用 XML | 可执行程序 | 上下文列表 |
| **真实 API 调用** | ❌ | ❌ | ✅ | ❌ |
| **执行反馈** | ❌ | ❌ | ✅ | ❌ |
| **长期记忆** | ❌ | ❌ | ❌ | ✅ |
| **每轮 LLM 调用** | 1 次 | 1 次 | 2 次（AP + DM） | 1 次+ |
| **实现复杂度** | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **适用场景** | 通用槽位提取 | 标准函数调用 | 任务型精确对话 | 开放域长对话 |

---

## 7. 项目目录结构

```text
contextmind/                    # 主包
├── pipeline.py                 # ContextPipeline（推荐统一入口）
│
├── infra/                      # 基础设施层（所有模块共用）
│   ├── llm_client.py           # AdkLLMClient + LLMConfig
│   ├── embedding.py            # EmbeddingUtils（向量化 + 相似度）
│   ├── logger.py               # 统一日志
│   └── data_models.py          # 共享数据模型
│
├── knowledge/                  # ① 知识库构建
│   ├── builder.py              # KnowledgeBaseBuilder（两阶段入口）
│   ├── discoverer.py           # GenericDialogueDiscoverer
│   ├── synthesizer.py          # SchemaSynthesizer
│   └── normalizer.py           # 多格式对话归一化
│
├── schema_builder/             # ② Schema 数据生成
│   ├── builder.py              # SchemaDataBuilder（顶层入口）
│   ├── pytod/                  # PyTOD companion 生成（5 阶段 LLM）
│   │   ├── builder.py          # build_pytod_apis()
│   │   ├── generator.py        # PyTODApiCodeGenerator
│   │   ├── validator.py        # validate_function + _values_match
│   │   ├── models.py           # TestCaseItem + FuncValidation
│   │   ├── helpers.py          # SHARED_HELPERS 工具函数
│   │   └── prompts.py          # LLM 提示词模板
│   └── fnctod/                 # FnCTOD companion 生成（直接转换）
│       └── builder.py
│
├── modes/                      # ③ 算法执行层
│   ├── base.py                 # BaseTracker 协议
│   ├── pytod/                  # PyTOD：AP → EE → DM
│   │   ├── tracker.py          # AdkPyTODTracker
│   │   ├── execution_engine.py # ExecutionEngine（安全执行）
│   │   ├── prompts.py          # PyTODPromptBuilder
│   │   ├── schemas.py          # ServiceSchema
│   │   └── registry.py         # API 函数注册表
│   ├── dst/                    # DST：对话状态追踪
│   │   ├── tracker.py
│   │   ├── prompts.py
│   │   └── parser.py
│   ├── fnctod/                 # FnCTOD：函数调用追踪
│   │   ├── tracker.py
│   │   ├── function_manager.py
│   │   └── schemas.py
│   └── evolve/                 # Evolve：演化式上下文优化
│       ├── core/               # EvolveEngine + 数据模型 + 配置
│       ├── memory/             # MemoryBank / Extractor / Retriever / fitness
│       ├── pipeline/           # 5 步上下文处理流水线
│       └── evolution/          # EvolutionaryUpdater + FeedbackCollector
│
├── scenarios/                  # 场景注册与配置
│   ├── registry.py             # ScenarioRegistry（YAML 驱动）
│   └── anyihua/ callcenter/ chat/ insurance/
│
└── ui/                         # Gradio UI 组件
    ├── components.py
    └── styles.py
```

---

**最后更新**：2026-04-01 | **版本**：0.3.0
