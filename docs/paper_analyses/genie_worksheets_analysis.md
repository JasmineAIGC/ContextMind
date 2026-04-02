# Genie Worksheets × ContextMind 集成分析

> **撰写日期**：2026-04-01 | **版本**：0.3.0  
> **参考论文**：*Coding Reliable LLM-based Integrated Task and Knowledge Agents with GenieWorksheets* (ACL 2025, [arXiv:2407.05674](https://arxiv.org/abs/2407.05674))  
> **参考仓库**：[stanford-oval/genie-worksheets](https://github.com/stanford-oval/genie-worksheets)

---

## 目录

1. [Genie Worksheets 核心算法解析](#1-genie-worksheets-核心算法解析)
2. [ContextMind 与 Genie 的概念对照](#2-contextmind-与-genie-的概念对照)
3. [集成机会分析](#3-集成机会分析)
   - [机会 A：Worksheet 作为 Schema 输入新格式](#机会-a-worksheet-作为-schema-输入新格式)
   - [机会 B：SUQL 增强知识检索](#机会-b-suql-增强知识检索)
   - [机会 C：GenieTracker — 第五种执行模式](#机会-c-genietracker--第五种执行模式)
   - [机会 D：Worksheet 约束注入 PyTOD EE](#机会-d-worksheet-约束注入-pytod-ee)
4. [机会综合评估矩阵](#4-机会综合评估矩阵)
5. [推荐集成路线图](#5-推荐集成路线图)
6. [技术差异与挑战](#6-技术差异与挑战)

---

## 1. Genie Worksheets 核心算法解析

### 1.1 设计动机

GPT-4 with function calling 的目标完成率在 Genie 测试的三个真实场景（Yelp 餐厅预订、工单提交、课程注册）中仅为 **21.8%**，而 Genie 达到 **82.8%**。根本原因是：

- **纯 LLM 方案**：策略（policy）在提示词中，LLM 很容易幻觉式跳过字段、回答错误、在条件分支中出错。
- **Genie**：策略在**声明式 Worksheet** 中，LLM 仅做两件事——解析用户输入和生成文字回复，不负责控制流程。

### 1.2 核心组件

```
用户输入
  │
  ▼
┌─────────────────────────────────────────────┐
│  Genie Runtime（算法层，无 LLM）             │
│                                             │
│  Worksheet Spec ──► Policy Executor         │
│       (CSV/JSON/Google Sheets)              │
│           │                                 │
│           │ 缺哪些字段？                     │
│           ▼                                 │
│  SUQLReActParser ◄── semantic_parsing.prompt│
│  (LLM 1: 语义解析)                          │
│           │                                 │
│           │ SUQL 查询                        │
│           ▼                                 │
│  SUQLKnowledgeBase                          │
│  (PostgreSQL + 向量检索)                    │
│           │                                 │
│           │ 结构化结果                       │
│           ▼                                 │
│  ResponseGenerator ◄── response.prompt      │
│  (LLM 2: 回复生成)                          │
└─────────────────────────────────────────────┘
  │
  ▼
系统回复
```

#### Genie Worksheet（声明式策略规范）

Worksheet 是一张表格（Google Sheets / CSV / JSON），每行是一个**字段（Field）**，列包括：

| 列 | 含义 |
|----|------|
| `name` | 字段名（槽位名） |
| `type` | 数据类型（str / int / enum / worksheet_type） |
| `description` | 字段语义描述（给 LLM 用） |
| `required` | 是否必填 |
| `confirm` | 是否需要二次确认 |
| `ask_by_system` | 是否由系统主动询问 |
| `on_success` | 填完此字段后触发什么动作 |

Worksheet 可以**嵌套**（`worksheet_type` 引用另一个 Worksheet），天然支持多轮对话中的子任务链。

#### SUQL（Semantic Understanding Query Language）

SUQL 是 Genie 的知识查询语言，语法类似 SQL，但增加了两个语义谓词：

```sql
-- 普通 SQL 部分：结构化过滤
SELECT restaurant_name, address
FROM restaurants
WHERE cuisine = 'Italian'
  -- 语义谓词：向量相似度搜索
  AND answer(reviews, 'vegan options available') = 'yes'
  -- 摘要谓词：从非结构化文本中抽取
  AND summary(menu, 'price range') = 'moderate'
ORDER BY rating DESC
LIMIT 5;
```

- `answer(col, question)` — 从该列文本中用 LLM 回答问题（RAG 语义搜索）
- `summary(col, topic)` — 对文本列生成摘要

SUQLKnowledgeBase 架构：PostgreSQL + pgvector 扩展 + 专用嵌入服务（FastAPI，端口 8509）。

#### SUQLReActParser（语义解析器）

采用 **ReAct**（Reason + Act）框架，将用户输入和对话历史转换为 SUQL 查询或字段赋值操作：

1. **Reason**：思考当前缺少哪些信息
2. **Act**：生成 SUQL 查询或 `field_name = value` 赋值
3. **Observe**：获取 DB 结果，继续推理直到 Worksheet 满足

这与 PyTOD 的 AP 生成 Python 程序逻辑一致，但 SUQL 语法更规整、可验证。

---

## 2. ContextMind 与 Genie 的概念对照

| Genie Worksheets 概念 | ContextMind 对应模块/概念 | 差距分析 |
|-----------------------|--------------------------|----------|
| **Worksheet Spec** | `schema.json`（SGD 格式）+ `scenarios/` YAML | ContextMind Schema 缺乏字段顺序、条件必填、二次确认、子 Worksheet 等策略信息 |
| **SUQLReActParser** (LLM 1) | PyTOD `ActionParser`（AP） | AP 生成 Python 程序；SUQL 解析器生成结构化查询。相似度高，但 SUQL 对知识密集型任务更强 |
| **ResponseGenerator** (LLM 2) | PyTOD `DialogueManager`（DM） | 概念完全一致，均为基于执行结果生成自然语言回复 |
| **Policy Executor**（无 LLM 运行时） | PyTOD `ExecutionEngine`（EE） | EE 执行 Python 语句；Genie Policy Executor 执行 Worksheet 字段填写逻辑。Genie 更声明式、更可预测 |
| **SUQLKnowledgeBase** | `knowledge/` 模块（仅离线构建 Schema，无在线 DB 查询）| ContextMind 没有在线结构化知识库；Evolve 做向量检索但没有结构化 SQL 能力 |
| **AgentBuilder** | `ContextPipeline` | 概念一致，Genie 的 builder 模式更链式、API 更清晰 |
| **Config**（LLM 配置） | `AdkLLMClient` + `LLMConfig` | ContextMind 已有统一 LLM 接入层，直接复用 |
| **Worksheet 嵌套** | 无直接对应 | ContextMind 当前 Schema 不支持子任务嵌套 |
| **`@agent_api` 装饰器** | `pytod_apis.py` 中的普通函数 | ContextMind 通过 SchemaDataBuilder 自动生成，Genie 需手写 |

### 核心差距总结

1. **策略表达能力**：Genie 的 Worksheet 是**状态机级别**的策略规范；ContextMind Schema 只描述槽位结构，策略隐含在 LLM 提示词中。
2. **在线知识查询**：Genie 有 SUQL + PostgreSQL，支持知识密集型任务；ContextMind 在线阶段无结构化知识库。
3. **AP/EE 可靠性**：Genie Policy Executor 是纯确定性的；ContextMind EE 在 AP 幻觉时只能 Fuzzy Match 补救。
4. **Schema 生成能力**：ContextMind 的 KB Builder（LLM 自动从对话数据提取）是 Genie 不具备的核心优势。

---

## 3. 集成机会分析

### 机会 A：Worksheet 作为 Schema 输入新格式

**问题**：ContextMind 的 schema.json 缺乏 Genie Worksheet 的策略信息（字段顺序、条件必填、二次确认）。  
**方案**：在 `contextmind/knowledge/` 添加 `worksheet_loader.py`，把 Genie 格式的 CSV/JSON Worksheet 转换为 `ServiceSchema`，同时在 `ServiceSchema` 扩展可选的策略字段。

**数据流**：

```
Genie Worksheet (CSV/JSON)
         │
         ▼
  WorksheetLoader.load()        ← 新增 contextmind/knowledge/worksheet_loader.py
         │
         ▼
  ServiceSchema（扩展 policy_fields）
         │
         ├─► PyTOD AP Prompt（注入字段顺序 + 条件逻辑）
         └─► EE（按 confirm=True 字段触发确认流程）
```

**扩展 ServiceSchema 示意**：

```python
@dataclass
class PolicyField:
    name: str
    required: bool = True
    confirm: bool = False           # ← 新增：是否需要二次确认
    ask_by_system: bool = True      # ← 新增：是否主动询问
    depends_on: Optional[str] = None  # ← 新增：条件依赖字段名

@dataclass  
class IntentDefinition:
    # 现有字段...
    policy_fields: List[PolicyField] = field(default_factory=list)  # ← 新增
```

**价值**：
- 让使用 Genie 格式定义业务策略的团队直接复用 ContextMind 基础设施
- AP 提示词可注入字段顺序，减少 AP 跳字段的幻觉

**实现难度**：⭐⭐（低）— 主要是数据格式转换，无算法变更

---

### 机会 B：SUQL 增强知识检索

**问题**：ContextMind 的 Evolve 只做向量语义检索（`MemoryRetriever`），无法处理**结构化 + 语义混合**查询。知识密集型场景（产品库查询、订单状态、FAQ 检索）无法精确过滤。  
**方案**：在 `contextmind/knowledge/` 新增 `suql_connector.py`，将 SUQL 包装为 ContextMind 可调用的知识检索接口，供 Evolve `ContextRetriever` 和 PyTOD EE 使用。

**架构**：

```
contextmind/knowledge/suql_connector.py    ← 新增
├── SUQLConnector                          ← 适配器
│   ├── __init__(pg_dsn, embedding_url)
│   ├── query(suql_str) -> List[dict]      ← 直接执行 SUQL
│   └── semantic_search(question, table)   ← 封装 answer() 谓词

contextmind/modes/evolve/memory/retriever.py  ← 扩展
└── SUQLMemoryRetriever(MemoryRetriever)   ← 新增子类，复用 SUQLConnector
```

**调用示意**：

```python
# 在 PyTOD pytod_apis.py 中的 API 函数
def query_products(category: str, user_requirement: str) -> dict:
    connector = SUQLConnector(pg_dsn=os.environ["PG_DSN"], ...)
    results = connector.query(f"""
        SELECT product_name, price, specs
        FROM products
        WHERE category = '{category}'
          AND answer(description, '{user_requirement}') = 'yes'
        LIMIT 3
    """)
    return {"status": "success", "products": results}
```

**价值**：
- 解决知识密集型任务（Genie 论文中 goal completion 从 21.8% → 82.8% 的核心驱动力之一）
- Evolve 的向量检索可升级为结构化 + 语义混合查询

**依赖**：PostgreSQL + pgvector + 独立向量服务（参考 Genie 的 FastAPI embedding server）

**实现难度**：⭐⭐⭐⭐（中高）— 需引入 PostgreSQL 依赖，适合可选扩展包

---

### 机会 C：GenieTracker — 第五种执行模式

**问题**：当前 PyTOD 的 AP 生成 Python-like 程序，EE 通过 AST 执行。对于**业务策略复杂**（条件分支多、需要用户确认）的场景，AP 幻觉率高。  
**方案**：新增 `contextmind/modes/genie/` 模块，实现 `GenieTracker`，直接将 Genie 的 Worksheet-driven Policy Executor + SUQLReActParser 适配到 ContextMind 的 BaseTracker 协议。

**模块结构**：

```
contextmind/modes/genie/               ← 新增
├── __init__.py
├── tracker.py                         # GenieTracker(BaseTracker 协议)
│   ├── from_scenario(llm, config, worksheet_path)
│   ├── async process_turn(utterance) -> dict
│   └── get_current_state() -> dict
├── policy_executor.py                 # Worksheet 状态机执行器（无 LLM）
│   ├── WorksheetState                 # 当前字段填写状态
│   ├── PolicyExecutor
│   │   ├── next_required_field()      # 返回下一个待填字段
│   │   ├── fill_field(name, value)    # 填写字段（含类型校验）
│   │   └── is_complete()             # 检查 Worksheet 是否完成
├── semantic_parser.py                 # SUQL/Field-assignment 语义解析器（LLM 1）
└── prompts/
    ├── semantic_parsing.prompt        # 类似 Genie 的语义解析提示词（中文版）
    └── response_generator.prompt     # 回复生成提示词
```

**GenieTracker.process_turn 流程**：

```
用户输入
   │
   ▼
PolicyExecutor.next_required_field()    ← 确定性，无 LLM
   │
   ▼
SemanticParser(LLM 1)                   ← 使用 AdkLLMClient
生成: field=value 赋值 / SUQL查询 / NONE
   │
   ├─[赋值]──► PolicyExecutor.fill_field()
   ├─[SUQL]──► SUQLConnector.query()（可选，无 DB 时退化为 LLM 直接回答）
   └─[NONE]──► 跳过本轮
   │
   ▼
ResponseGenerator(LLM 2)               ← 使用 AdkLLMClient
   │
   ▼
{"response": ..., "worksheet_state": ..., "is_complete": ...}
```

**降级设计**（无 PostgreSQL 时）：`SUQLConnector` 降级为纯 LLM 语义回答，功能等同 DST 但有 Worksheet 策略约束。

**价值**：
- 在 ContextMind 中引入 **Worksheet 声明式策略**，解决 PyTOD 在复杂业务规则场景下的幻觉问题
- 兼容现有 `ContextPipeline`，用户只需 `mode="genie"` + `worksheet_path=...` 即可切换
- 自动继承 ContextMind 的 KB Builder：KB Builder 产出的 schema.json 可自动转为 Worksheet 格式

**实现难度**：⭐⭐⭐（中）— 核心是 `policy_executor.py`（纯 Python 状态机），语义解析提示词需调优

---

### 机会 D：Worksheet 约束注入 PyTOD EE

**问题**：PyTOD EE 当前只执行 AP 生成的程序，不检查字段完整性。AP 可能在用户未提供必填槽位时就调用 API，导致 API 调用失败。  
**方案**：在现有 PyTOD EE 的函数调用路径中注入 Worksheet 约束检查：若函数对应的 `policy_fields` 中有 `required=True` 的字段未收集，EE 阻断调用并生成"请先提供 X"的提示给 DM。

**改动点**（最小侵入）：

```python
# contextmind/modes/pytod/execution_engine.py — 在 _call_registered() 中增加

def _check_policy_constraints(
    self, func_name: str, kwargs: dict, schema: Optional[ServiceSchema]
) -> Optional[str]:
    """检查 Worksheet 策略约束。返回 None 表示通过，返回字符串表示阻断原因。"""
    if schema is None:
        return None
    intent = schema.get_intent_by_api_name(func_name)
    if intent is None or not intent.policy_fields:
        return None
    for pf in intent.policy_fields:
        if pf.required and pf.name not in kwargs:
            return f"缺少必填字段：{pf.name}（{pf.description}）"
    return None
```

**价值**：
- **零新模块**，只扩展现有 EE，最小侵入
- 用 Genie 的 Worksheet 约束思想提升 PyTOD 可靠性
- 需与机会 A（WorksheetLoader → ServiceSchema 扩展）配合

**实现难度**：⭐（极低）— 约 50 行代码，无外部依赖

---

## 4. 机会综合评估矩阵

| 机会 | 改善目标 | 实现难度 | 外部依赖 | 对现有代码侵入性 | 推荐优先级 |
|------|----------|----------|----------|-----------------|-----------|
| **A** WorksheetLoader（格式转换） | 兼容 Genie 用户、丰富 Schema 策略信息 | ⭐⭐ | 无 | 低（新文件） | 🥇 **P1** |
| **D** Worksheet 约束注入 EE | 减少 PyTOD 幻觉调用 | ⭐ | 无 | 极低（约 50 行） | 🥇 **P1** |
| **C** GenieTracker（新执行模式） | 声明式策略，复杂业务场景 | ⭐⭐⭐ | 无（降级模式）/ PostgreSQL（完整模式） | 中（新模块） | 🥈 **P2** |
| **B** SUQL 知识检索 | 知识密集型查询精度 | ⭐⭐⭐⭐ | PostgreSQL + pgvector + 向量服务 | 中（可选扩展） | 🥉 **P3** |

---

## 5. 推荐集成路线图

### Phase 1（P1）— 低成本、高兼容性（2 周）

目标：让 Genie 格式的业务策略定义可在 ContextMind 中使用，同时增强 PyTOD 可靠性。

```
新增文件：
  contextmind/knowledge/worksheet_loader.py   (≈200 行)
  tests/test_worksheet_loader.py

修改文件：
  contextmind/modes/pytod/schemas.py          (+PolicyField dataclass, ≈30 行)
  contextmind/modes/pytod/execution_engine.py (+_check_policy_constraints, ≈50 行)
  contextmind/modes/pytod/prompts.py          (+policy_fields 注入 AP System Prompt, ≈30 行)
```

交付物：
- `WorksheetLoader.from_csv(path) -> ServiceSchema`
- `WorksheetLoader.from_json(path) -> ServiceSchema`  
- `WorksheetLoader.from_schema(schema) -> worksheet_csv_str`（反向转换，方便导出）
- PyTOD EE 在缺少必填字段时阻断并给出结构化提示

### Phase 2（P2）— 新执行模式（4 周）

目标：增加 `GenieTracker` 作为第五种执行模式，支持 Worksheet 声明式策略。

```
新增目录：
  contextmind/modes/genie/
    __init__.py
    tracker.py          (GenieTracker)
    policy_executor.py  (WorksheetState + PolicyExecutor)
    semantic_parser.py  (LLM 语义解析，中文优化)
    prompts/
      semantic_parsing.prompt
      response_generator.prompt

修改文件：
  contextmind/pipeline.py   (mode="genie" 分支)
  docs/architecture.md      (更新算法对比表)
```

交付物：
- `ContextPipeline(mode="genie", worksheet_path=...)` 端到端可用
- 降级模式（无 PostgreSQL）下功能等同增强版 DST

### Phase 3（P3）— SUQL 知识库集成（6 周，可选）

目标：为知识密集型任务提供结构化 + 语义混合查询能力。

```
新增目录：
  contextmind/knowledge/suql/
    __init__.py
    connector.py        (SUQLConnector 适配器)
    embedding_server/   (FastAPI 向量服务，参考 Genie)
    
修改文件：
  contextmind/modes/evolve/memory/retriever.py  (SUQLMemoryRetriever)
  contextmind/modes/genie/tracker.py            (接入 SUQLConnector)
  requirements.txt / setup.py                   (psycopg2, pgvector 可选依赖)
```

---

## 6. 技术差异与挑战

### 6.1 ContextMind 对 Genie 的核心优势

| 优势 | 说明 |
|------|------|
| **自动 Schema 生成** | KB Builder 可从任意对话数据自动发现意图 / 槽位，Genie 需手写 Worksheet |
| **pytod_apis.py 自动生成** | SchemaDataBuilder 的 5 阶段 LLM 流水线自动生成 API 函数代码，Genie 需手写 `@agent_api` |
| **ADK 原生集成** | 基于 Google ADK，AP / DM 的 session 管理、工具调用完全托管 |
| **多模式统一框架** | DST / FnCTOD / PyTOD / Evolve 四种模式，同一 `ContextPipeline` 接口 |

### 6.2 引入 Genie 时的主要挑战

| 挑战 | 缓解方案 |
|------|----------|
| **SUQL 依赖 PostgreSQL** | Phase 2 的 `GenieTracker` 默认降级为 LLM 语义回答，无需 DB；Phase 3 再引入 PostgreSQL |
| **Worksheet 手写成本** | `WorksheetLoader.from_schema()` 把 KB Builder 生成的 schema.json 反向转为 Worksheet，降低冷启动成本 |
| **中文场景提示词调优** | ContextMind 的业务场景以中文为主，Genie 的语义解析提示词需要中文版适配（Phase 2 重点工作） |
| **`policy_fields` 与现有 ServiceSchema 兼容** | 新字段设为 `Optional`，默认为空列表，不影响任何现有代码路径 |

### 6.3 不适合直接移植的部分

| Genie 组件 | 原因 | ContextMind 替代 |
|-----------|------|-----------------|
| Google Sheets 同步 | 需要 Google Service Account，企业场景不适用 | CSV / JSON Worksheet 格式足够 |
| Chainlit 前端 | ContextMind 已有 Gradio UI | 保持现有 UI 层 |
| `uv` 包管理 | ContextMind 使用 `pip` + `requirements.txt` | 保持现有构建系统 |

---

**结论**：Genie Worksheets 和 ContextMind 在核心两 LLM 架构（解析器 + 回复生成器）上高度一致，最大差距在于**策略表达能力**（Worksheet vs. 隐式 Prompt）和**知识查询能力**（SUQL vs. 纯向量检索）。推荐**先做 Phase 1**（两周，低风险）：WorksheetLoader 格式转换 + EE 约束检查，即可在不引入任何新依赖的前提下将 Genie 的核心设计思想融入 ContextMind。
