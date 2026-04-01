# ContextMind 架构图

> **版本**：0.3.0 | **最后更新**：2026-04-01

本文档以多种视角描述 ContextMind 框架的整体架构，帮助开发者快速理解模块职责、数据流转和算法结构。

---

## 目录

1. [三步核心框架总览](#1-三步核心框架总览)
2. [模块依赖关系图](#2-模块依赖关系图)
3. [数据流端到端示意](#3-数据流端到端示意)
4. [第一步：知识库构建流水线](#4-第一步知识库构建流水线)
5. [第二步：Schema 数据生成（5 阶段流水线）](#5-第二步schema-数据生成5-阶段流水线)
6. [第三步：四种算法执行模式](#6-第三步四种算法执行模式)
   - [6.1 PyTOD — AP→EE→DM 三步程序执行](#61-pytod--apeeedm-三步程序执行)
   - [6.2 Evolve — 演化式上下文优化](#62-evolve--演化式上下文优化)
   - [6.3 DST — 对话状态追踪](#63-dst--对话状态追踪)
   - [6.4 FnCTOD — 函数调用追踪](#64-fnctod--函数调用追踪)
7. [ContextPipeline 统一接口](#7-contextpipeline-统一接口)
8. [基础设施层（infra）](#8-基础设施层infra)
9. [算法步骤依赖矩阵](#9-算法步骤依赖矩阵)

---

## 1. 三步核心框架总览

```mermaid
graph TB
    subgraph INPUT["📥 输入"]
        D["原始对话数据\n(任意格式)"]
    end

    subgraph STEP1["① 建立知识库\ncontextmind.knowledge"]
        DISC["GenericDialogueDiscoverer\n(LLM 开放式发现\n槽位 + 意图)"]
        SYNTH["SchemaSynthesizer\n(LLM 合成\n标准 SGD Schema)"]
        DISC --> SYNTH
    end

    subgraph STEP2["② Schema 数据生成\ncontextmind.schema_builder"]
        SDB["SchemaDataBuilder"]
        PYTOD_B["PyTOD\npytod_apis.py\n(5阶段LLM生成)"]
        FNCTOD_B["FnCTOD\nfnctod_domain.json\n(槽位→函数参数)"]
        SDB --> PYTOD_B
        SDB --> FNCTOD_B
    end

    subgraph STEP3["③ 算法执行\ncontextmind.modes.*"]
        PYTOD["PyTOD\nAP→EE→DM\n程序执行"]
        DST["DST\n槽位状态追踪"]
        FNCTOD["FnCTOD\n函数调用追踪"]
        EVOLVE["Evolve\n记忆进化\n上下文优化"]
    end

    subgraph OUTPUT["📤 输出"]
        CTX["结构化上下文\n(意图+槽位+回复)"]
    end

    D --> STEP1
    SYNTH -->|"schema.json\n(SGD格式)"| STEP2
    SYNTH -->|"schema.json"| STEP3
    PYTOD_B -->|"pytod_apis.py"| PYTOD
    FNCTOD_B -->|"fnctod_domain.json"| FNCTOD
    STEP3 --> CTX

    style STEP1 fill:#dbeafe,stroke:#3b82f6
    style STEP2 fill:#dcfce7,stroke:#22c55e
    style STEP3 fill:#fef9c3,stroke:#eab308
    style INPUT fill:#f3f4f6,stroke:#6b7280
    style OUTPUT fill:#f3f4f6,stroke:#6b7280
```

---

## 2. 模块依赖关系图

```mermaid
graph LR
    subgraph PKG["contextmind 包"]
        PIPE["pipeline.py\nContextPipeline"]

        subgraph INFRA["infra/"]
            LLM["llm_client.py\nAdkLLMClient"]
            EMB["embedding.py\nEmbeddingUtils"]
            LOG["logger.py"]
            DM["data_models.py"]
        end

        subgraph KB["knowledge/"]
            KBB["builder.py\nKnowledgeBaseBuilder"]
            DISC2["discoverer.py\nGenericDialogueDiscoverer"]
            SYNTH2["synthesizer.py\nSchemaSynthesizer"]
            NORM["normalizer.py"]
        end

        subgraph SB["schema_builder/"]
            SBLD["builder.py\nSchemaDataBuilder"]
            subgraph PYTOD_SB["pytod/"]
                SBGEN["generator.py\nPyTODApiCodeGenerator"]
                SBVAL["validator.py\nvalidate_function"]
                SBMOD["models.py\nTestCaseItem"]
                SBHLP["helpers.py\nSHARED_HELPERS"]
                SBPMT["prompts.py"]
                SBBLD["builder.py\nbuild_pytod_apis"]
            end
            subgraph FNCTOD_SB["fnctod/"]
                SBFN["builder.py\nbuild_fnctod_domain"]
            end
        end

        subgraph MODES["modes/"]
            BASE["base.py\nBaseTracker"]
            subgraph PYTOD_M["pytod/"]
                APT["tracker.py\nAdkPyTODTracker"]
                EE["execution_engine.py\nExecutionEngine"]
                PROM["prompts.py\nPyTODPromptBuilder"]
                SCH["schemas.py\nServiceSchema"]
            end
            subgraph DST_M["dst/"]
                DSTT["tracker.py\nDialogueStateTracker"]
                DSTP["prompts.py"]
                DSTP2["parser.py"]
            end
            subgraph FN_M["fnctod/"]
                FNT["tracker.py\nFnCTODTracker"]
                FM["function_manager.py\nFunctionManager"]
            end
            subgraph EV_M["evolve/"]
                ENG["core/engine.py\nEvolveEngine"]
                MEM["memory/"]
                PIP["pipeline/"]
                EVO["evolution/"]
            end
        end

        subgraph SCEN["scenarios/"]
            REG["registry.py\nScenarioRegistry"]
            BASE_S["base.py\nScenarioConfig"]
        end

        subgraph UI["ui/"]
            UICOMP["components.py"]
        end
    end

    PIPE --> KB
    PIPE --> MODES
    PIPE --> INFRA
    KBB --> DISC2
    KBB --> SYNTH2
    KBB --> NORM
    DISC2 --> LLM
    SYNTH2 --> LLM
    SBLD --> PYTOD_SB
    SBLD --> FNCTOD_SB
    SBGEN --> LLM
    APT --> EE
    APT --> PROM
    APT --> SCH
    APT --> LLM
    DSTT --> LLM
    FNT --> FM
    FNT --> LLM
    ENG --> MEM
    ENG --> PIP
    ENG --> LLM
    MODES --> BASE
    PIPE --> SCEN
```

---

## 3. 数据流端到端示意

```mermaid
sequenceDiagram
    participant U as 用户/调用方
    participant CP as ContextPipeline
    participant KB as KnowledgeBaseBuilder
    participant SB as SchemaDataBuilder
    participant TR as Tracker<br/>(PyTOD/DST/FnCTOD/Evolve)
    participant LLM as AdkLLMClient<br/>(LLM API)

    Note over U,LLM: 第一步：建立知识库（可选）
    U->>CP: build_kb(dialogues, scene_name)
    CP->>KB: build(dialogues)
    KB->>LLM: 发现阶段 Prompt（逐轮）
    LLM-->>KB: 槽位 + 意图（YAML）
    KB->>LLM: 合成阶段 Prompt
    LLM-->>KB: SGD schema.json（JSON）
    KB-->>CP: schema_dict
    CP-->>U: schema 已加载

    Note over U,LLM: 第二步：Schema 数据生成（PyTOD 可选）
    U->>SB: build_pytod_apis(schema_path)
    SB->>LLM: 测试用例生成（Phase 2）
    LLM-->>SB: TestCaseItem[]
    SB->>LLM: 函数体生成（Phase 3）
    LLM-->>SB: Python 函数代码
    SB->>SB: 验证 + 迭代修复（Phase 4）
    SB-->>U: xxx_pytod_apis.py

    Note over U,LLM: 第三步：对话上下文提取
    U->>CP: process_turn("用户话语")
    CP->>TR: process_turn(utterance)
    TR->>LLM: AP Prompt（PyTOD）/ DST Prompt
    LLM-->>TR: 程序语句 / 槽位状态
    TR->>TR: 执行引擎（PyTOD EE）/ 函数调用
    TR->>LLM: DM Prompt（PyTOD）
    LLM-->>TR: 自然语言回复
    TR-->>CP: {response, context, program_text, ...}
    CP-->>U: 结构化结果
```

---

## 4. 第一步：知识库构建流水线

```mermaid
flowchart TD
    IN["原始对话数据\n支持 5 种格式：\n• chat_test JSON\n• SGD turns dict\n• List[str] 带前缀\n• 纯文本\n• chat_test_500 嵌套格式"] --> NORM2["normalizer.py\n格式归一化\n→ 统一对话列表"]

    NORM2 --> DISC3["GenericDialogueDiscoverer\n发现阶段（Phase 1）"]

    subgraph DISC3_DETAIL["发现阶段详情"]
        direction TB
        EACH["逐条对话处理"]
        LX["langextract\n(可选)\n字符级溯源"]
        LLMD["LLM\nYAML 格式提取"]
        MERGE["合并结果\n(Counter 去重)"]
        EACH --> LX
        EACH --> LLMD
        LX --> MERGE
        LLMD --> MERGE
    end

    DISC3 --> DISC3_DETAIL
    DISC3_DETAIL --> RAW["discovery_raw.json\n原始提取结果\n{intent, slot_value, fact}"]

    RAW --> SYNTH3["SchemaSynthesizer\n合成阶段（Phase 2）"]

    subgraph SYNTH3_DETAIL["合成阶段详情（多轮分批）"]
        direction TB
        BATCH["分批处理\n(>200意图时多轮)"]
        LLM2["LLM\nSGD JSON 格式输出"]
        MERGE2["合并 / 去重"]
        BATCH --> LLM2 --> MERGE2
    end

    SYNTH3 --> SYNTH3_DETAIL
    SYNTH3_DETAIL --> OUT1["schema.json\n(SGD ServiceSchema)"]
    SYNTH3_DETAIL --> OUT2["dialogues_001.json\n(SGD 标注对话)"]
    SYNTH3_DETAIL --> OUT3["conversion_summary.json\n(构建统计)"]

    style IN fill:#dbeafe
    style OUT1 fill:#dcfce7
    style OUT2 fill:#dcfce7
    style OUT3 fill:#dcfce7
```

---

## 5. 第二步：Schema 数据生成（5 阶段流水线）

```mermaid
flowchart LR
    SCH_IN["schema.json\n(SGD格式)"]

    subgraph SDB_FLOW["SchemaDataBuilder — 5 阶段 LLM 生成流水线"]
        direction TB
        P1["Phase 1\n解析 Schema\n提取意图 + 槽位定义"]
        P2["Phase 2\n测试用例生成\n每意图: 5种对话场景\n(早期/中期/完整/跨意图/边界)\n+ expected_values 预期计算值"]
        P3["Phase 3\n逐意图函数生成\nLLM 生成函数体\n(few-shot 测试用例 + KB 背景)"]
        P4["Phase 4\n验证 + 迭代修复\nexec() 执行测试\n通过率 < 阈值 → 重新生成\n(max_iterations=3)"]
        P5["Phase 5\n组装输出文件\n完整 .py 文件\n+ 可选验证报告"]

        P1 --> P2 --> P3 --> P4
        P4 -->|"通过率不足"| P3
        P4 -->|"达到阈值"| P5
    end

    subgraph HELPERS["共享工具函数\n(helpers.py / SHARED_HELPERS)"]
        H1["_ticket_id(prefix)\n生成工单号"]
        H2["_parse_amount(v)\n解析金额"]
        H3["_calc_monthly_payment()\n计算月供"]
        H4["_next_work_day(d)\n计算工作日"]
    end

    SCH_IN --> SDB_FLOW
    HELPERS --> P3
    HELPERS --> P4

    P5 --> OUT_PY["xxx_pytod_apis.py\n每个意图一个 Python 函数\n含 SHARED_HELPERS"]
    P5 --> OUT_RPT["xxx_validation_report.json\n通过率 / 迭代次数"]
    SCH_IN --> OUT_FN["xxx_fnctod_domain.json\n(不需要 LLM\n直接从 schema 槽位生成)"]

    style SDB_FLOW fill:#dcfce7,stroke:#22c55e
    style HELPERS fill:#fef3c7,stroke:#f59e0b
```

---

## 6. 第三步：四种算法执行模式

### 6.1 PyTOD — AP→EE→DM 三步程序执行

```mermaid
sequenceDiagram
    participant USR as 用户话语
    participant AP as Action Parser<br/>(ADK LlmAgent)
    participant EE as Execution Engine<br/>(Python 纯执行，无LLM)
    participant DM as Dialogue Manager<br/>(ADK LlmAgent)
    participant API as 注册 API 函数<br/>(xxx_pytod_apis.py)

    USR->>AP: 用户输入 + 对话历史 + Schema
    Note over AP: 生成 PyTOD 程序语句
    AP-->>EE: x1 = verify_identity(account_status='正常')\nx2 = Hint('request: loan_amount')\nx3 = say(x2)

    EE->>API: 调用 verify_identity(account_status='正常')
    API-->>EE: {verified_identity: True, status: 'success'}
    EE->>EE: 解析 Hint / say / confirm 语句
    EE-->>DM: 执行结果 + say() 内容 + 程序文本

    Note over DM: 基于执行结果生成自然语言回复
    DM-->>USR: "您的身份已核实，请告知贷款金额"
```

```mermaid
flowchart TD
    subgraph AP_DETAIL["Action Parser 提示词结构"]
        SYS_AP["System:\n• 服务 Schema（槽位+意图描述）\n• 可调用函数签名（来自 ExecutionEngine）\n• PyTOD 程序语法规则"]
        USR_AP["User（每轮）:\n• 对话历史（多轮积累）\n• 当前 API 调用结果（prior_dataflow）\n• 用户话语"]
        SYS_AP --> USR_AP
    end

    subgraph EE_DETAIL["Execution Engine 处理流程"]
        PARSE["AST 解析程序语句\n(安全，无 eval())"]
        DISPATCH["函数分发\n(精确匹配 + Fuzzy 匹配\ncutoff=0.6)"]
        EXEC["调用注册函数\n(xxx_pytod_apis.py)"]
        SAY["处理 say()/Hint()\n/confirm()/perform()"]
        PARSE --> DISPATCH --> EXEC --> SAY
    end

    subgraph DM_DETAIL["Dialogue Manager 提示词结构"]
        SYS_DM["System:\n• 服务描述 + 角色定位"]
        USR_DM["User:\n• 完整对话历史\n• say() 输出内容（关键信息）\n• API 执行结果"]
        SYS_DM --> USR_DM
    end

    AP_DETAIL --> EE_DETAIL --> DM_DETAIL
```

### 6.2 Evolve — 演化式上下文优化

```mermaid
flowchart TB
    USR2["用户输入"]

    subgraph EVOLVE_SYS["EvolveEngine"]
        direction TB

        subgraph PIPE_EV["Pipeline（上下文处理流水线）"]
            PRE["InputPreprocessor\n输入预处理"]
            RETR["ContextRetriever\n上下文检索"]
            COMP["ContextCompressor\n上下文压缩"]
            REORD["ContextReorderer\n相关性重排序"]
            SUM["ConversationSummarizer\n摘要生成"]
            PRE --> RETR --> COMP --> REORD --> SUM
        end

        subgraph MEM_EV["Memory（记忆子系统）"]
            MB["MemoryBank\n记忆存储库"]
            ME["MemoryExtractor\n知识提取器\n(LLM)"]
            MR["MemoryRetriever\n语义检索\n(Embedding)"]
            MU["MemoryUpdater\n记忆更新器"]
            MF["fitness.py\n适应度评估\n(MemoryFitness)"]
        end

        subgraph EVO_EV["Evolution（演化系统）"]
            EU["EvolutionaryMemoryUpdater\n进化式记忆更新\n(ThetaEvolve)"]
            FC["FeedbackCollector\n反馈收集\n(AlphaEvolve)"]
        end

        subgraph ADK_EV["ADK 基础设施"]
            ISS["InMemorySessionService\n会话生命周期管理"]
            IMS["InMemoryMemoryService\n跨会话语义记忆"]
        end
    end

    USR2 --> PIPE_EV
    PIPE_EV <--> MEM_EV
    MEM_EV --> EVO_EV
    EVO_EV --> MEM_EV
    ADK_EV --> MEM_EV
    PIPE_EV --> OUT_EV["上下文优化结果\n{response, context_items,\nmemory_hits, session_turns}"]
```

### 6.3 DST — 对话状态追踪

```mermaid
flowchart LR
    IN_DST["用户话语\n+ 可选 schema.json"]

    subgraph DST_SYS["DialogueStateTracker"]
        PM["PromptManager\n构建提取 Prompt\n(可选注入 Schema 槽位)"]
        AGENT_DST["ADK LlmAgent\n+ InMemoryRunner\n(自动维护历史)"]
        PARSER["DSTResponseParser\n解析 YAML/JSON 输出\n→ DialogueTurn"]
        STATE["累积对话状态\n(predicted_state dict)"]
        PM --> AGENT_DST --> PARSER --> STATE
    end

    IN_DST --> DST_SYS
    DST_SYS --> OUT_DST["{ predicted_state:\n   {slot: value, ...},\n  turn_updates: {...},\n  response: ... }"]
```

### 6.4 FnCTOD — 函数调用追踪

```mermaid
flowchart LR
    IN_FN["用户话语\n+ schema.json (槽位→函数参数)"]

    subgraph FNCTOD_SYS["FnCTODTracker"]
        FM2["FunctionManager\n槽位 → FunctionTool\nDomainSpec → OpenAI Function Schema"]
        TOOLS["ADK FunctionTool\n(原生函数调用格式)"]
        AGENT_FN["ADK LlmAgent\n(带 FunctionTool)\n自动触发函数调用"]
        PARSE_FN["FunctionCallParser\n解析 XML 函数调用\n→ 槽位状态"]
        FM2 --> TOOLS --> AGENT_FN --> PARSE_FN
    end

    IN_FN --> FNCTOD_SYS
    FNCTOD_SYS --> OUT_FN["{ state: {slot: value},\n  function_calls: [...],\n  response: ... }"]
```

---

## 7. ContextPipeline 统一接口

```mermaid
stateDiagram-v2
    [*] --> 初始化: ContextPipeline(llm_client, mode)

    初始化 --> 知识库就绪: build_kb(dialogues) / load_kb(schema_path)
    初始化 --> 知识库就绪: set_schema(schema) [直接传入]
    初始化 --> 知识库就绪: (Evolve/DST 无需 schema)

    知识库就绪 --> API注册: register_api(func) [PyTOD 可选]
    知识库就绪 --> 对话中: process_turn(utterance) [延迟初始化 Tracker]
    API注册 --> 对话中: process_turn(utterance)

    对话中 --> 对话中: process_turn(utterance) [多轮积累]
    对话中 --> 初始化: reset() [重置会话]
    对话中 --> [*]: 会话结束
```

```mermaid
flowchart TD
    CP["ContextPipeline"]

    CP -->|"mode='pytod'"| PYTOD2["AdkPyTODTracker\n(默认模式)"]
    CP -->|"mode='dst'"| DST2["DialogueStateTracker"]
    CP -->|"mode='fnctod'"| FN2["FnCTODTracker"]
    CP -->|"mode='evolve'"| EV2["EvolveEngine\n(via _EvolveTrackerAdapter)"]

    CP -->|"build_kb()"| KBB2["KnowledgeBaseBuilder"]
    CP -->|"load_kb(path)"| JSON2["schema.json → ServiceSchema"]
    CP -->|"register_api(func)"| EE2["ExecutionEngine.register()"]

    subgraph OUTPUT2["process_turn() 返回值"]
        R1["response: str — 自然语言回复"]
        R2["context: dict — 本轮提取上下文"]
        R3["cumulative_context: dict — 累积全量上下文"]
        R4["program_text: str — PyTOD 程序(仅pytod)"]
        R5["turn_updates: dict — 本轮槽位更新"]
    end

    PYTOD2 --> OUTPUT2
    DST2 --> OUTPUT2
    FN2 --> OUTPUT2
    EV2 --> OUTPUT2
```

---

## 8. 基础设施层（infra）

```mermaid
flowchart TB
    subgraph INFRA2["contextmind/infra/"]
        subgraph LLM_CLIENT["llm_client.py"]
            CFG["LLMConfig\n(.env 读取)\nLLM_API_KEY\nLLM_BASE_URL\nLLM_MODEL"]
            CLIENT["AdkLLMClient\n统一 LLM 接口\n同步 + 异步"]
            LOCAL["create_local_adk_model()\nvLLM / 本地端点\n(LiteLlm 接入)"]
            QWEN["Qwen3 特殊支持\nenable_thinking=False\n(chat_template_kwargs)"]
            CFG --> CLIENT
            CLIENT --> LOCAL
            CLIENT --> QWEN
        end

        subgraph EMB2["embedding.py"]
            EMB_CLS["EmbeddingUtils\n文本向量化"]
            OAI["OpenAI Embeddings\n(text-embedding-3-small)"]
            ST["SentenceTransformer\n(本地模型)"]
            COS["余弦相似度计算"]
            EMB_CLS --> OAI
            EMB_CLS --> ST
            EMB_CLS --> COS
        end

        subgraph LOG2["logger.py"]
            GLOG["get_logger(name)\n分级日志\nINFO/DEBUG/WARNING"]
            FILE["可选: 日志文件\nsetup_logging(save_to_file=True)"]
            GLOG --> FILE
        end

        subgraph DM2["data_models.py"]
            EI["EmbeddingInfo\n向量 + 元数据"]
        end
    end

    ALL_MODS["所有模块"] -->|"依赖"| INFRA2
```

---

## 9. 算法步骤依赖矩阵

```mermaid
quadrantChart
    title 算法复杂度 vs 准确性
    x-axis 实现复杂度低 --> 实现复杂度高
    y-axis 准确性一般 --> 准确性最高
    quadrant-1 高复杂高准确
    quadrant-2 低复杂高准确
    quadrant-3 低复杂一般准确
    quadrant-4 高复杂一般准确
    DST: [0.2, 0.4]
    FnCTOD: [0.45, 0.7]
    Evolve: [0.55, 0.55]
    PyTOD: [0.85, 0.92]
```

| 算法 | ① 建立知识库 | ② Schema 生成 | ③ 算法执行 | LLM 调用/轮 | 核心优势 |
|------|:-----------:|:------------:|:---------:|:----------:|---------|
| **DST** | ✅ 可选 | ❌ 不需要 | ✅ 必须 | 1次 | 最简单，通用槽位提取 |
| **FnCTOD** | ✅ 可选 | ❌ 不需要 | ✅ 必须 | 1次 | 原生函数调用，高精度 |
| **PyTOD** | ✅ 可选 | ✅ 可选 | ✅ 必须 | 2次(AP+DM) | 真实API调用+执行反馈 |
| **Evolve** | ❌ 不需要 | ❌ 不需要 | ✅ 必须 | 1次+ | 长期记忆，开放域对话 |

---

## 附：项目完整目录结构

```
ContextMind/
├── contextmind/                    # 主包
│   ├── __init__.py                 # 公开 API 导出
│   ├── pipeline.py                 # ContextPipeline（推荐统一入口）
│   │
│   ├── infra/                      # 基础设施层
│   │   ├── llm_client.py           # AdkLLMClient + LLMConfig
│   │   ├── embedding.py            # 文本向量化工具
│   │   ├── logger.py               # 统一日志
│   │   └── data_models.py          # 共享数据模型
│   │
│   ├── knowledge/                  # ① 知识库构建
│   │   ├── builder.py              # KnowledgeBaseBuilder（两阶段入口）
│   │   ├── discoverer.py           # GenericDialogueDiscoverer（发现）
│   │   ├── synthesizer.py          # SchemaSynthesizer（合成SGD Schema）
│   │   └── normalizer.py           # 多格式对话数据归一化
│   │
│   ├── schema_builder/             # ② Schema数据生成
│   │   ├── builder.py              # SchemaDataBuilder（顶层入口）
│   │   ├── pytod/                  # PyTOD companion生成（5阶段LLM）
│   │   │   ├── builder.py          # build_pytod_apis()
│   │   │   ├── generator.py        # PyTODApiCodeGenerator
│   │   │   ├── validator.py        # validate_function + _values_match
│   │   │   ├── models.py           # TestCaseItem + FuncValidation
│   │   │   ├── helpers.py          # SHARED_HELPERS工具函数库
│   │   │   └── prompts.py          # LLM提示词模板
│   │   └── fnctod/                 # FnCTOD companion生成（直接转换）
│   │       └── builder.py          # build_fnctod_domain()
│   │
│   ├── modes/                      # ③ 算法执行层
│   │   ├── base.py                 # BaseTracker协议
│   │   ├── pytod/                  # PyTOD：AP→EE→DM程序执行
│   │   │   ├── tracker.py          # AdkPyTODTracker
│   │   │   ├── execution_engine.py # ExecutionEngine（安全执行）
│   │   │   ├── prompts.py          # PyTODPromptBuilder
│   │   │   ├── schemas.py          # ServiceSchema + load_schema_from_dict
│   │   │   └── registry.py         # API函数注册表
│   │   ├── dst/                    # DST：对话状态追踪
│   │   │   ├── tracker.py          # DialogueStateTracker
│   │   │   ├── prompts.py          # 槽位提取Prompt
│   │   │   └── parser.py           # YAML/JSON响应解析
│   │   ├── fnctod/                 # FnCTOD：函数调用追踪
│   │   │   ├── tracker.py          # FnCTODTracker
│   │   │   ├── function_manager.py # FunctionManager + DomainSpec
│   │   │   └── schemas.py          # FnCTOD专用Schema
│   │   └── evolve/                 # Evolve：演化式上下文优化
│   │       ├── core/               # EvolveEngine + 数据模型 + 配置
│   │       ├── memory/             # MemoryBank + 提取/检索/更新/适应度
│   │       ├── pipeline/           # 上下文处理流水线（5步）
│   │       └── evolution/          # 演化算法（ThetaEvolve + AlphaEvolve）
│   │
│   ├── scenarios/                  # 场景注册与配置
│   │   ├── registry.py             # ScenarioRegistry（YAML驱动）
│   │   ├── base.py                 # ScenarioConfig基类
│   │   └── anyihua/ callcenter/ chat/ insurance/  # 内置场景
│   │
│   └── ui/                         # Gradio UI组件
│       ├── components.py           # create_layout / bind_events
│       └── styles.py               # CUSTOM_CSS
│
├── examples/                       # 示例脚本
│   ├── context_pipeline_demo.py    # ContextPipeline 端到端演示
│   ├── build_kb_demo.py            # 第一步：知识库构建
│   └── build_schema_data.py        # 第二步：Schema数据生成
│
├── benchmark/                      # 评测框架
├── resources/                      # 静态资源与测试数据
└── docs/                           # 文档（本目录）
```

---

**最后更新**: 2026-04-01 | **版本**: 0.3.0
