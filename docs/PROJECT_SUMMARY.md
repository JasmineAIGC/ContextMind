# ContextMind 项目总结文档

> **版本**：v0.3.0  
> **生成日期**：2026-04-10  
> **定位**：通用上下文工程（Context Engineering）框架

---

## 目录

1. [项目概述](#1-项目概述)
2. [整体架构](#2-整体架构)
3. [三步框架详解](#3-三步框架详解)
   - [第一步：知识库构建（Knowledge）](#31-第一步知识库构建-knowledge)
   - [第二步：Schema 数据生成（SchemaBuilder）](#32-第二步schema-数据生成-schemabuilder)
   - [第三步：算法执行（Modes）](#33-第三步算法执行-modes)
4. [四种执行模式](#4-四种执行模式)
5. [PyTOD 代码生成算法详解](#5-pytod-代码生成算法详解)
6. [基础设施层](#6-基础设施层)
7. [统一入口：ContextPipeline](#7-统一入口-contextpipeline)
8. [目录结构](#8-目录结构)
9. [依赖与环境](#9-依赖与环境)
10. [已有能力汇总](#10-已有能力汇总)
11. [已知问题与局限性](#11-已知问题与局限性)
12. [设计亮点](#12-设计亮点)
13. [未来展望](#13-未来展望)

---

## 1. 项目概述

**ContextMind** 是一个以 **LLM 驱动的上下文工程（Context Engineering）** 为核心的 Python 框架。它的目标是让开发者以最低代价将任意业务对话场景接入 LLM，并获得结构化的上下文提取能力（槽位值、意图识别、状态追踪等）。

### 核心理念

| 传统方式 | ContextMind 方式 |
|----------|-----------------|
| 手工标注语料，训练 NLU 模型 | LLM 自动从真实对话中发现槽位/意图 |
| 针对每个业务场景单独编写规则 | 通用 schema 驱动，一套代码覆盖多场景 |
| API 代码手工编写 | LLM 自动生成并验证 Python 函数实现 |
| 单一提取算法 | 四种算法可插拔替换，基准对比公平 |

### 技术栈

- **语言**：Python 3.8+
- **LLM 接入**：Google ADK + LiteLLM（支持 OpenAI、Qwen、Claude 等任意兼容接口）
- **对话格式**：标准 SGD（Schema-Guided Dialogue）格式
- **UI**：Gradio（可选）
- **许可证**：MIT

---

## 2. 整体架构

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
│                                           xxx_fnctod_domain.json    │
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
│   ├── logger.py       ← 结构化日志
│   ├── embedding.py    ← 向量嵌入（可选）
│   └── data_models.py
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
│   ├── evolve/         ← EvolveApp
│   └── pytod/          ← AdkPyTODTracker + ExecutionEngine
│
├── schema_builder/     ← 依赖 infra + modes.pytod.schemas
│   ├── builder.py      ← SchemaDataBuilder（orchestrator）
│   └── pytod/
│       ├── testcase/   ← TestCaseGenerator（无 codegen 依赖）
│       └── codegen/    ← 4种代码生成算法
│           ├── loop/
│           ├── alpha/
│           ├── sstar/
│           └── ctree/
│
└── pipeline.py         ← 顶层（依赖所有模块）
```

---

## 3. 三步框架详解

### 算法步骤依赖矩阵

| 算法 | 第一步：知识库 | 第二步：Schema 生成 | 第三步：算法执行 |
|------|:------------:|:-----------------:|:--------------:|
| **DST** | ✅ 可选 | ❌ 不需要 | ✅ 必须 |
| **FnCTOD** | ✅ 可选 | ❌ 不需要 | ✅ 必须 |
| **PyTOD** | ✅ 可选 | ✅ 可选 | ✅ 必须 |
| **Evolve** | ❌ 不需要 | ❌ 不需要 | ✅ 必须 |

---

### 3.1 第一步：知识库构建（Knowledge）

**核心文件**：`contextmind/knowledge/`

**输入**：任意格式的业务对话数据  
**输出**：标准 SGD 格式 `schema.json`（包含 ServiceSchema：意图定义 + 槽位定义）

#### 工作流程

```
原始对话数据
    │
    ▼
normalize_dialogues()           ← normalizer.py
（支持5种输入格式）
    │
    ▼
GenericDialogueDiscoverer       ← discoverer.py
（LLM开放式扫描 + langextract 溯源）
逐对话发现：意图、槽位、事实
    │
    ▼
SchemaSynthesizer               ← synthesizer.py
（LLM合成 SGD 格式 schema）
    │
    ▼
schema.json（SGD ServiceSchema 格式）
```

#### 支持的输入格式（normalizer.py 处理）

1. **chat_test 格式**：`[{"utterances": [...], "speaker": [...]}]`
2. **SGD 格式**：`[{"turns": [{"utterance": ..., "speaker": ...}]}]`
3. **字符串列表**：`[["agent: ...", "user: ..."], ...]`
4. **坐席+用户拼接文本**：`"坐席：...\n用户：..."` 
5. **纯文本列表**：`["...", "..."]`

#### 两阶段 LLM 处理

| 阶段 | 工具 | 作用 |
|------|------|------|
| Discovery | `GenericDialogueDiscoverer` + `langextract` | 从样本对话中开放式发现实体/意图/槽位，并附加原文溯源 |
| Synthesis | `SchemaSynthesizer` | 汇总发现结果，LLM 二次调用生成规范化 SGD JSON |

#### 后处理特性

- **语义去重**：`SchemaSynthesizer.refine()` 在 merge 2+ schema 后做 LLM 语义合并，消除近似重复的槽位/意图（总数 ≤ 5 时跳过）
- **per-dialogue 合成**：每条对话独立合成，结果再 `_merge_service_list()` 归并，不跨对话累积
- **discovery_raw.json**：保存发现阶段中间结果，供后续 TestCaseGenerator 使用

---

### 3.2 第二步：Schema 数据生成（SchemaBuilder）

**核心文件**：`contextmind/schema_builder/`

**输入**：第一步生成的 `schema.json`  
**输出**：算法专用数据文件

#### 输出文件类型

| 文件类型 | 用途 | 示例 |
|---------|------|------|
| `*_pytod_apis.py` | PyTOD 执行引擎 API 代码 | 每个 intent → 一个 Python 函数 |
| `*_fnctod_domain.json` | FnCTOD 函数调用域定义 | DomainSpec 序列化 JSON |
| `*_test_cases.json` | 跨生成器共享测试用例 | 保证 4 种算法评测公平 |

#### 生成流程

```
schema.json
    │
    ├── prebuild_test_cases()   ← [前置] Phase 2：LLM生成测试用例，共享给4种生成器
    │       └── TestCaseGenerator（并行：每意图一个线程）
    │
    └── build_pytod_apis()      ← [主流程] Phase 1-5 完整代码生成
            │
            ├── Phase 1: 解析 schema
            ├── Phase 2: 加载/生成测试用例（TestCaseItem × N）
            ├── Phase 3: LLM 初始函数体生成
            ├── Phase 4: 验证 + 迭代修复（生成算法核心）
            └── Phase 5: 组装输出 .py 文件 + validate_pytod_apis_source()
```

#### 并行能力

- `prebuild_test_cases(workers=N)`：每个 intent 各占一个线程并发调用 LLM
- `_process_dir()`：多个 schema 文件也会并发处理（`--workers` 控制并发数）
- Phase 4 各 intent 之间相互独立，天然可并行

#### 最终验证（Phase 5）

- `validate_pytod_apis_source()`：对生成的整个 `.py` 模块做健康检查
- 失败函数被 `replace_function_in_source()` 替换为 stub（安全降级，不影响整体加载）
- 4 种生成算法（loop/alpha/sstar/ctree）均执行此步骤

---

### 3.3 第三步：算法执行（Modes）

**核心文件**：`contextmind/modes/`

各 Tracker 遵循统一的 `BaseTracker` 协议（`base.py`），对外暴露：

```python
async def process_turn(user_input: str) -> dict:
    # 返回：response / context / cumulative_context / program_text（PyTOD）等
```

---

## 4. 四种执行模式

### 4.1 DST 模式（对话状态追踪）

**文件**：`contextmind/modes/dst/`  
**原理**：将对话历史整理成结构化 prompt，让 LLM 从中提取槽位-值对

**特点**：
- 不需要第二步预生成任何文件
- 基于 `scenario_config` 描述场景（意图、槽位列表）
- 最轻量，适合快速集成

**输出**：`{"slot_name": "slot_value", ...}` 形式的状态字典

---

### 4.2 FnCTOD 模式（函数调用式对话状态追踪）

**文件**：`contextmind/modes/fnctod/`  
**论文来源**：[ACL 2024 - LLMs as Zero-shot Dialogue State Tracker through Function Calling](https://arxiv.org/pdf/2402.10466)

**原理**：  
将槽位提取建模为函数调用问题——把 schema 中的意图/槽位定义转换为 LLM 工具调用描述（tool_use），让 LLM 用 function calling 接口输出结构化槽位值。

**特点**：
- 零样本对话状态追踪
- 利用现代 LLM 原生 function calling 能力
- 与 DST 相比，输出格式更规范（LLM 被强制 JSON 化输出）
- 支持 `FunctionManager.add_domain_from_slots()` 动态添加域

**输出**：函数调用结果（结构化 JSON）

---

### 4.3 Evolve 模式（演化式上下文记忆）

**文件**：`contextmind/modes/evolve/`  
**算法来源**：[ThetaEvolve](https://arxiv.org/pdf/2511.23473) + AlphaEvolve 启发

**原理**：  
对话过程中动态提取和组织知识（事实、偏好、关系等），形成可随时查询的记忆库。每轮对话后自动更新记忆，支持长对话的跨轮知识积累。

**特点**：
- 不需要知识库预构建（无 Step 1/2 依赖）
- 专为长对话场景设计（记忆容量自适应）
- 支持语义检索（基于向量嵌入）
- 适用于通用助手、客户关系管理等场景

---

### 4.4 PyTOD 模式（可编程任务型对话）

**文件**：`contextmind/modes/pytod/`  
**论文来源**：[Apple 研究院 - PyTOD: Programmable Task-Oriented Dialogue with Execution Feedback](https://arxiv.org/pdf/2508.15456)

**原理**：  
将每轮对话建模为程序执行问题，LLM 输出"动作计划（Action Plan）"——一段 Python 代码，再通过 `ExecutionEngine` 实际执行业务 API，并将执行结果反馈给对话管理器。

**三组件架构（AP → EE → DM）**：

```
用户输入
    │
    ▼
Action Parser (AP)                  ← LLM 根据 schema 和上下文，生成 Python 动作计划
（调用哪个 API、传入哪些参数）         例：x1 = query_balance(account_id="123")
    │
    ▼
Execution Engine (EE)               ← 执行 AP 生成的代码，调用注册的业务 API
（ExecutionEngine.execute()）        返回实际 API 结果
    │
    ▼
Dialogue Manager (DM)               ← LLM 根据执行结果生成自然语言回复
（基于 AP + EE 结果）
```

**关键特性**：
- `top_k_intents > 0` 时启用 TF-IDF 多信号意图评分，动态筛选最相关的 K 个意图放入 prompt，减少 context 长度
- `load_pytod_api_module()` 在加载时自动 wrap 有 bug 的函数为安全 stub（避免 NameError/UnboundLocalError）
- `_is_stub_only_result` 过滤 stub-only 结果，不传入 AP 上下文避免误导

---

## 5. PyTOD 代码生成算法详解

**文件**：`contextmind/schema_builder/pytod/codegen/`

四种生成算法共享相同的 5-Phase 框架，差异体现在 Phase 3-4（初始生成 + 迭代修复）。

### 5.1 共同框架

```
Phase 1  解析 schema（意图、槽位、返回字段）
Phase 2  加载/生成测试用例（TestCaseItem × N per intent）
Phase 3  LLM 初始函数体生成        ← 算法差异点
Phase 4  验证 + 迭代修复           ← 算法差异点（核心）
Phase 5  组装 .py 文件 + 模块级健康校验
```

**验证逻辑（validator.py）**：
1. 函数调用无异常
2. 返回值为 `dict`
3. `status == "success"`
4. `expected_keys` 中所有键均存在
5. `expected_values` 中指定字段值匹配（宽松比较 `_values_match`）

**probe 推进机制**（loop / alpha / sstar 共用）：
- `best_code`：仅在通过率提升时更新，用于最终输出
- `probe_code`：无条件推进到最新修复状态，确保每轮 LLM 看到不同的代码与失败用例，避免死循环

### 5.2 Loop（默认，基础五阶段流水线）

**适用**：快速生成、资源有限时的基准方案

| 参数 | 默认值 |
|------|--------|
| `max_iterations` | 3 |
| `pass_rate_threshold` | 0.9 |

**流程**：Phase G 初始生成 → 验证 → probe 推进修复 × N 轮

---

### 5.3 Alpha（ACIA，自适应迭代修复）

**来源**：[AlphaCodium](https://arxiv.org/abs/2401.08500)（2024）启发  
**适用**：需要较强鲁棒性、倾向探索不同实现思路

**三个额外机制**：
1. **Phase R（反思）**：生成前先让 LLM 分析函数业务语义，输出 `reflection JSON`
2. **Phase A（失败分析）**：每轮修复前先分析失败模式，再定向修复
3. **收敛重启**：连续 2 轮无提升 → 完全重新反思 + 重新生成，跳出局部最优

| 参数 | 默认值 |
|------|--------|
| `max_iterations` | 10 |
| `_NO_IMPROVE_THRESHOLD` | 2 |

---

### 5.4 SStar（S*，并行采样与区分性选择）

**论文**：[S* - Test Time Scaling for Code Generation](https://arxiv.org/abs/2502.14382)（2025）  
**适用**：高质量要求场景，可接受更多 LLM 调用

**四阶段**：
| 阶段 | 说明 |
|------|------|
| Phase P | 以 3 种不同"思维模式"并行生成 3 个候选实现 |
| Phase D | 每个草稿独立修复，提供**执行追踪（execution traces）**而非仅错误信息 |
| Phase S | **锦标赛模式**：让 LLM 生成"区分性输入"，实际执行两个候选后由 LLM 裁判选优 |
| Phase R | 对最优候选用剩余预算继续精炼 |

**核心创新**：区分性测试输入（Discriminating Inputs）—— 固定测试集通过率相近时，生成能区分两函数行为差异的专用输入

| 参数 | 默认值 |
|------|--------|
| `_n_drafts` | 3 |
| `_k_per_draft` | 3 |
| `max_iterations` | 10 |

---

### 5.5 CTree（CodeTree，UCB 引导树搜索）

**论文**：[CodeTree - Agent-guided Tree Search for Code Generation](https://arxiv.org/abs/2411.04329)（2024/2025）  
**适用**：复杂函数生成，存在多个互不干扰的失败原因

**核心思想**：将代码修复建模为树搜索，每个失败用例独立生成修复分支，UCB 算法平衡探索/利用：

```
UCB(node) = pass_rate(node) + C × sqrt( ln(parent_visits + 1) / (node_visits + 1) )
```

**三阶段**：
| 阶段 | 说明 |
|------|------|
| Phase G | 生成根节点（初始候选函数） |
| Phase E | 针对每个失败用例独立扩展子节点（最多 `_max_children` 个） |
| Phase S | UCB 评分选择下一个扩展节点（平衡高通过率节点利用 + 低访问节点探索） |

| 参数 | 默认值 |
|------|--------|
| `_UCB_C` | 1.4（≈√2） |
| `_MAX_EXPAND_CHILDREN` | 2 |
| `max_iterations` | 10 |

---

### 5.6 四种算法综合对比

| 特性 | Loop | Alpha | S* | CodeTree |
|------|------|-------|-----|---------|
| **迭代结构** | 线性 | 线性+重启 | 并行+选择 | 树形搜索 |
| **多样性机制** | probe 推进 | probe + 收敛重启 | 多思维模式 | 分支扩展 |
| **候选选择** | 接受改善 | 接受改善 | 区分性测试 | UCB 评分 |
| **修复粒度** | 全部失败 | 全部失败 | 全部失败 | **单个失败用例** |
| **LLM 调用数** | 低 | 中 | 高 | 中偏高 |
| **复杂函数效果** | 一般 | 较好 | 好 | 最好 |
| **推荐场景** | 快速基准 | 普通复杂度 | 高质量要求 | 复杂/多失败点 |

---

## 6. 基础设施层

**文件**：`contextmind/infra/`

### 6.1 LLM 客户端（llm_client.py）

```python
class AdkLLMClient:
    # 统一的 LLM 调用接口，屏蔽底层 provider 差异
    # 支持 sync / async 调用
    # 从 .env 读取配置（LLM_API_KEY / LLM_BASE_URL / LLM_MODEL）
```

**支持的 LLM 接入方式**：
- OpenAI 兼容接口（ChatGPT、Qwen、DeepSeek、vLLM 等）
- Anthropic Claude
- Google Gemini（通过 ADK）
- 任何 LiteLLM 支持的模型

### 6.2 日志系统（logger.py）

- 结构化日志输出
- 可配置级别（`LogLevel.INFO / DEBUG / WARNING / ERROR`）
- 可选写入文件（`save_to_file=True`）

### 6.3 向量嵌入（embedding.py）

- 用于 Evolve 模式的语义检索
- 支持本地 sentence-transformers 模型（可选依赖）
- 支持 API 嵌入

### 6.4 数据模型（data_models.py）

共享基础数据结构定义，在 infra 层统一管理

---

## 7. 统一入口：ContextPipeline

**文件**：`contextmind/pipeline.py`

`ContextPipeline` 是三步框架的统一胶水层，提供最简洁的 API：

```python
from contextmind import ContextPipeline, AdkLLMClient

pipeline = ContextPipeline(
    llm_client=AdkLLMClient(),
    mode="pytod",          # dst / fnctod / evolve / pytod
    scene_name="银行贷款外呼",
)

# 第一步：构建知识库
pipeline.build_kb(dialogues=my_dialogues, scene_name="银行贷款外呼")

# 加载已有 schema
pipeline.load_kb("output/schema.json")

# 注册业务 API（pytod 模式）
@pipeline.register_api("verify_identity")
def verify_identity(customer_name: str) -> dict:
    return {"verified": True, "customer_name": customer_name}

# 第三步：执行对话
result = await pipeline.process_turn("我是李明，想查询贷款额度")
```

**输出字段**：
- `response`：LLM 生成的自然语言回复
- `context`：本轮提取的结构化上下文（槽位/意图）
- `cumulative_context`：跨轮累积的全量上下文
- `program_text`：（PyTOD 模式）本轮生成的动作计划代码

---

## 8. 目录结构

```
ContextMind/
├── contextmind/                    # 核心包
│   ├── __init__.py                 # 顶层导出（ContextPipeline / AdkLLMClient）
│   ├── pipeline.py                 # 统一流水线入口
│   │
│   ├── infra/                      # 基础设施
│   │   ├── llm_client.py           # AdkLLMClient / LLMConfig
│   │   ├── logger.py               # 结构化日志
│   │   ├── embedding.py            # 向量嵌入
│   │   └── data_models.py          # 共享数据模型
│   │
│   ├── knowledge/                  # 第一步：知识库构建
│   │   ├── builder.py              # KnowledgeBaseBuilder
│   │   ├── discoverer.py           # GenericDialogueDiscoverer
│   │   ├── synthesizer.py          # SchemaSynthesizer
│   │   └── normalizer.py           # 多格式对话归一化（5种）
│   │
│   ├── schema_builder/             # 第二步：Schema 数据生成
│   │   ├── builder.py              # SchemaDataBuilder（orchestrator）
│   │   ├── utils.py
│   │   └── pytod/
│   │       ├── testcase/           # 测试用例预生成（无 codegen 依赖）
│   │       │   ├── generator.py    # TestCaseGenerator
│   │       │   ├── cache.py        # save/load *_test_cases.json
│   │       │   ├── kb_loader.py    # KB 上下文加载
│   │       │   ├── models.py       # TestCaseItem / FuncValidation
│   │       │   ├── prompts.py      # LLM 提示模板
│   │       │   └── validator.py    # 测试验证逻辑
│   │       └── codegen/            # 4种代码生成算法
│   │           ├── shared/         # 公共模块（prompt / generator / cleaner）
│   │           ├── loop/           # Loop 基础五阶段
│   │           ├── alpha/          # Alpha ACIA
│   │           ├── sstar/          # S* 并行采样
│   │           └── ctree/          # CodeTree UCB 树搜索
│   │
│   ├── modes/                      # 第三步：算法执行
│   │   ├── base.py                 # BaseTracker 协议
│   │   ├── dst/                    # 对话状态追踪
│   │   ├── fnctod/                 # 函数调用式追踪
│   │   ├── evolve/                 # 演化式上下文记忆
│   │   └── pytod/                  # 可编程任务型对话
│   │       ├── tracker.py          # AdkPyTODTracker
│   │       ├── schemas.py          # ServiceSchema / IntentDefinition / SlotDefinition
│   │       ├── execution_engine.py # ExecutionEngine
│   │       ├── prompts.py          # AP/DM prompt 模板
│   │       └── registry.py         # INTENT_REGISTRY 支持
│   │
│   ├── scenarios/                  # 场景配置
│   └── ui/                         # Gradio UI 组件
│
├── examples/                       # 示例程序
│   ├── context_pipeline_demo.py    # 统一入口端到端演示
│   ├── build_kb.py                 # 第一步：知识库构建
│   ├── prebuild_test_cases.py      # 第二步前置：测试用例预生成（支持并行）
│   ├── build_schema_data.py        # 第二步：API 代码生成（支持4种算法）
│   ├── web_demo.py                 # 第三步 Web 界面
│   ├── cli_demo.py                 # 第三步 命令行交互
│   ├── batch_demo.py               # 批量对话测试
│   ├── fnctod_trace_demo.py        # FnCTOD 链路追踪
│   └── pytod_trace_demo.py         # PyTOD 链路追踪
│
├── benchmark/                      # 评测框架
│   ├── algorithms/                 # 各算法评测逻辑
│   ├── datasets/                   # 数据集适配
│   ├── runners/                    # 评测运行器
│   ├── shared/                     # 公共工具
│   └── tools/                      # 辅助工具
│
├── docs/                           # 文档
│   ├── PROJECT_SUMMARY.md          # 本文件
│   ├── algorithms/                 # 算法说明文档
│   ├── reference/                  # API 参考 / 架构图
│   ├── guides/                     # 使用指南
│   ├── research/                   # 研究笔记
│   └── development/                # 开发说明
│
├── schema/                         # schema.json 存放目录
├── resources/                      # 静态资源和测试数据
├── output/                         # 运行时生成的输出
├── requirements.txt
├── setup.py
└── README.md
```

---

## 9. 依赖与环境

### 核心依赖

| 包 | 用途 |
|----|------|
| `google-adk` | ADK 框架（LLM 工具调用基础） |
| `litellm` | 多模型 LLM 接入适配 |
| `openai` | OpenAI 兼容接口 |
| `python-dotenv` | `.env` 配置加载 |
| `PyYAML>=6.0.0` | 场景配置解析 |
| `langextract>=1.1.1` | 知识发现溯源（第一步 Discovery 阶段） |

### 可选依赖

| 包 | 用途 |
|----|------|
| `sentence-transformers>=2.0.0` | 本地向量嵌入（Evolve 模式语义检索） |
| `gradio>=4.0.0` | Web UI 演示 |
| `aiofiles>=23.0.0` | 异步文件 IO |

### 测试依赖

| 包 | 用途 |
|----|------|
| `pytest>=7.0.0` | 测试框架 |
| `pytest-asyncio>=0.21.0` | 异步测试支持 |

### 环境配置（`.env`）

```bash
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-plus
```

---

## 10. 已有能力汇总

### ✅ 知识库构建能力

- [x] 5 种输入格式自动归一化（chat_test / SGD / 字符串列表 / 坐席对话 / 纯文本）
- [x] LLM 开放式发现槽位、意图、业务事实（不依赖预定义模板）
- [x] `langextract` 原文溯源（每条发现结果附加对话原文）
- [x] 两阶段发现+合成流水线（Discovery → Synthesis → SGD JSON）
- [x] 语义去重合并（2+ schema 合并后 LLM 二次精炼）
- [x] per-dialogue 独立合成再归并（不跨对话污染）
- [x] 异步构建支持（`build_async()` / `build_dataset_async()`）
- [x] 中间结果持久化（`discovery_raw.json` / `conversion_summary.json`）

### ✅ Schema 数据生成能力

- [x] schema.json → Python API 函数代码（`*_pytod_apis.py`）
- [x] schema.json → FnCTOD 域定义（`*_fnctod_domain.json`）
- [x] 测试用例预生成并共享（`*_test_cases.json`），保证多算法评测公平
- [x] 4 种代码生成算法（loop / alpha / sstar / ctree），可通过 `--generator` 切换
- [x] 并行 LLM 调用（`--workers` 参数控制，intent 级 + schema 级双层并发）
- [x] 自动测试验证（Phase 4 验证 + Phase 5 模块级健康校验）
- [x] 失败函数自动 stub 降级（不影响整体模块加载）
- [x] 验证报告（可选 `validation_report.json`）
- [x] KB 目录上下文自动识别（`--kb-dir` 自动加载对话/发现/摘要数据提升生成质量）

### ✅ 对话执行能力

- [x] **DST**：零样本对话状态追踪（槽位-值对提取）
- [x] **FnCTOD**：函数调用式状态追踪（零样本，LLM 原生 function calling）
- [x] **PyTOD**：可编程任务型对话（AP → EE → DM，支持真实 API 执行）
- [x] **Evolve**：演化式长对话记忆（动态知识提取 + 语义检索）
- [x] 跨轮累积上下文（`cumulative_context`）
- [x] TF-IDF 多信号意图排序（`top_k_intents` 参数，减少 prompt 长度）
- [x] 安全 stub 包装（加载时自动处理有 bug 的 API 函数）

### ✅ 基础设施能力

- [x] 统一 LLM 客户端（支持所有 OpenAI 兼容接口）
- [x] `.env` 配置驱动（零代码修改切换模型）
- [x] 结构化日志（可配置级别/文件）
- [x] 向量嵌入支持（本地 + API）
- [x] `ContextPipeline` 统一入口（三步框架胶水层，3 行代码完成端到端）
- [x] Gradio Web UI 演示
- [x] 命令行交互演示
- [x] 批量对话测试工具
- [x] 评测框架（`benchmark/`）

---

## 11. 已知问题与局限性

### 🔴 功能缺失

| 问题 | 位置 | 说明 |
|------|------|------|
| FnCTOD Schema Builder 未实现 | `schema_builder/fnctod/` | 目录存在但为 stub，域定义生成功能暂无 LLM 驱动逻辑 |
| Evolve 模式无第一步依赖 | — | Evolve 不读取 schema.json，无法利用知识库中的意图/槽位定义 |
| PyTOD INTENT_REGISTRY 与 schema 解耦 | — | 手写 API 时需手动维护 INTENT_REGISTRY 与 schema 的一致性 |

### 🟡 设计限制

| 问题 | 说明 |
|------|------|
| **单一 LLM 依赖** | 所有步骤都依赖同一个 `AdkLLMClient` 实例；不同步骤使用不同模型（如弱模型做生成、强模型做审查）需手动传参 |
| **测试验证依赖 Python 执行** | Phase 4 验证需在生成器环境中实际执行 Python 代码；沙箱隔离不完善，恶意生成代码存在安全风险 |
| **LLM 结果不稳定** | 代码生成质量受模型能力影响显著，弱模型（如 7B 参数以下）可能导致大量 Phase 4 修复失败 |
| **schema 意图过多时 prompt 过长** | PyTOD AP prompt 包含所有意图定义，意图数量大时 prompt 超出 context 窗口（`top_k_intents` 可缓解但需手动配置） |
| **多轮 API 依赖** | PyTOD 中前轮 API 结果是否保留到后续轮次，取决于 `cumulative_context` 管理逻辑，复杂场景可能出现上下文漂移 |

### 🟡 性能限制

| 问题 | 说明 |
|------|------|
| **代码生成速度慢** | 每个 intent 需要多轮 LLM 调用（Phase 3+4），100 个 intent 可能需要数小时（依赖 `--workers` 并行加速） |
| **知识发现阶段无并行** | Discovery 阶段 `GenericDialogueDiscoverer` 对对话的处理目前是串行的（`build()` 内部 per-dialogue 顺序处理） |
| **Embedding 可选但影响功能** | Evolve 的语义检索依赖 `sentence-transformers`，未安装时退化为关键词检索，召回质量下降 |

### 🟠 工程问题

| 问题 | 说明 |
|------|------|
| **缺少集成测试** | 现有 pytest 主要是单元测试；端到端集成测试覆盖不足（需要真实 LLM API） |
| **内存架构多次记载** | 历史 memory 记录的架构信息部分已过时（如 `pytod/shared/` 目录已不存在），不同 session 的 memory 之间存在矛盾 |
| **benchmark 评测框架不完整** | `benchmark/` 目录存在但评测脚本覆盖不全，缺少标准化的评测报告生成 |
| **错误处理不一致** | 不同模块的错误处理方式不统一：部分 raise，部分 return None，部分打印警告后继续 |
| **配置管理分散** | 生成参数（max_iterations、threshold 等）在 CLI、Builder、Synthesizer 各层都有默认值，缺少集中配置管理 |

### 🟢 已有缓解措施

| 问题 | 缓解措施 |
|------|---------|
| 代码生成慢 | `--workers N` 并行（intent 级 + schema 级双层） |
| LLM 结果 bug | Phase 5 `validate_pytod_apis_source()` + stub 自动降级 |
| 多算法评测不公平 | `prebuild_test_cases.py` 预生成共享测试集 |
| schema prompt 过长 | `top_k_intents` TF-IDF 动态筛选 |
| API 函数加载失败 | `load_pytod_api_module()` 安全 wrap + `_is_stub_only_result` 过滤 |

---

## 12. 设计亮点

### 12.1 probe 推进机制

Loop / Alpha / S* 三种算法共同使用"probe 推进 + best 保守"的双指针模式：
- `probe_code` 无条件推进 → 每轮 LLM 看到不同代码状态，避免重复相同 prompt 死循环
- `best_code` 仅在改善时更新 → 最终输出历史最优

这是一个简洁而有效的设计，以极小的代价解决了修复循环中"重复失败"的问题。

### 12.2 测试用例共享（公平评测设计）

`prebuild_test_cases.py` + `*_test_cases.json` 机制：
- 先生成测试用例，4 种生成算法从同一测试集出发
- 消除 LLM 随机性对评测公平性的影响
- 这是将"评测公平性"内嵌到工程设计中的典型实践

### 12.3 三步框架的模块独立性

- `knowledge/` 不依赖 `modes/` 或 `schema_builder/`
- `testcase/` 不依赖 `codegen/`
- `modes/` 不依赖 `knowledge/` 或 `schema_builder/`
- 每个模块可单独使用，也可通过 `ContextPipeline` 组合

### 12.4 多算法可插拔

同一个 `SchemaDataBuilder` 接口，通过 `generator="loop"/"alpha"/"sstar"/"ctree"` 切换，方便跨算法对比实验。

### 12.5 安全降级设计

- Phase 5 验证失败 → stub 替换，不影响整模块加载
- `load_pytod_api_module()` wrap 有 bug 函数 → 对话可继续进行
- 对话过程中 API 执行失败 → EE 返回错误信息，DM 可生成合适的错误回复

---

## 13. 未来展望

### 短期（可实现的功能增强）

1. **FnCTOD Schema Builder 完整实现**：实现 `schema_builder/fnctod/` 的 LLM 驱动域定义生成
2. **Knowledge Discovery 并行化**：将 `build()` 中的 per-dialogue 处理改为并发
3. **沙箱隔离**：Phase 4 代码执行引入进程级/容器级隔离，提升安全性
4. **集成测试框架**：基于 mock LLM 的端到端集成测试（不需要真实 API）
5. **统一配置管理**：提供 `ContextMindConfig` 集中管理所有超参数

### 中期（架构演进）

1. **多模型分工**：支持为不同步骤配置不同 LLM（如弱模型做初始生成，强模型做验证/裁判）
2. **流式输出**：支持 `process_turn()` 的流式响应（`AsyncGenerator`）
3. **持久化对话状态**：支持跨进程恢复对话上下文（数据库/文件持久化）
4. **标准化 benchmark**：完善 `benchmark/` 框架，输出标准化评测报告

### 长期（研究方向）

1. **自适应算法选择**：基于意图复杂度自动选择最合适的代码生成算法
2. **跨场景迁移学习**：已生成的 API 代码在类似场景中复用（减少 LLM 调用）
3. **强化学习优化**：用实际对话反馈优化 AP prompt 策略
4. **多语言支持**：目前以中文场景为主，扩展英文及多语言对话数据支持

---

*本文档由 ContextMind 项目自动分析生成，反映截至 v0.3.0 的代码现状。*
