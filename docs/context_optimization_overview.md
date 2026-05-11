# ContextMind 上下文优化框架概述

---

## 一、核心问题：上下文优化要解决什么？

在大语言模型（LLM）驱动的对话系统中，原始对话信息往往是**非结构化的自然语言流**，存在以下三类典型问题：

| 问题类型 | 具体表现 |
|---------|---------|
| **信息丢失** | 多轮对话中，早期提到的关键信息（姓名、需求、偏好）在后续轮次被遗忘或混淆 |
| **LLM 幻觉** | 当 LLM 需要给出业务数据（账户余额、审批状态等）时，可能凭空捏造 |
| **策略失控** | 纯提示词驱动的对话难以保证业务流程的严格执行，LLM 可能偏离预设策略 |

**ContextMind 的核心目标**：将对话过程中产生的上下文信息**结构化提取、精准传递、持久记忆**，同时通过可编程/声明式等机制保证业务利用到精准的上下文信息。

---

## 二、整体框架与处理流程

ContextMind 围绕"**三步框架**"设计，将上下文优化拆解为知识构建、数据生成、算法执行三个层次，通过 `ContextPipeline` 统一串接：

```
原始对话数据（通话录音转写、历史对话等）
        │
        ▼
┌─────────────────────────────────────────────────────┐
│  第一步：知识库构建（Knowledge）                      │
│                                                     │
│  LLM 自动发现对话中的"槽位"和"意图"                   │
│  → 合成标准 SGD schema.json（业务知识图谱）           │
└─────────────────────────────────────────────────────┘
        │ schema.json
        ▼
┌─────────────────────────────────────────────────────┐
│  第二步：Schema 数据生成（SchemaBuilder）  [可选]     │
│                                                     │
│  将 schema.json 转换为算法可执行的代码文件            │
│  → 生成 xxx_pytod_apis.py（业务 API 函数实现）        │
└─────────────────────────────────────────────────────┘
        │ schema + api 代码
        ▼
┌─────────────────────────────────────────────────────┐
│  第三步：算法执行（Modes）                            │
│                                                     │
│  五种可选算法模式（按场景选择）：                     │
│  ┌──────┐ ┌────────┐ ┌────────┐ ┌───────┐ ┌──────┐  │
│  │ DST  │ │FnCTOD  │ │ PyTOD  │ │ Genie │ │Evolve│  │
│  └──────┘ └────────┘ └────────┘ └───────┘ └──────┘  │
└─────────────────────────────────────────────────────┘
        │
        ▼
结构化上下文输出（槽位值、意图、程序执行结果、对话状态）
```

---

## 三、数据如何做的结构化

### 3.1 第一步：从原始对话到结构化知识（schema.json）

**输入**：任意格式的原始对话数据（通话录音转写、历史聊天记录等）

**两阶段 LLM 处理**：

```
阶段一：GenericDialogueDiscoverer（发现）
─────────────────────────────────────────
输入对话 → LLM 开放式分析 → 发现业务实体和对话模式
  - 识别"槽位"：对话中需要收集的信息（如：姓名、贷款金额、手机号）
  - 识别"意图"：用户目标（如：查询余额、申请贷款、修改还款计划）
  - 记录每个槽位的来源对话（溯源）

阶段二：SchemaSynthesizer（合成）
─────────────────────────────────────────
发现结果 → LLM 标准化 → 输出 SGD 格式 schema.json
```

**输出**：标准化的 `schema.json`（以 Google SGD 格式为基础），结构示例：

```json
{
  "services": [{
    "service_name": "loan_service",
    "description": "银行贷款外呼服务",
    "intents": [
      {
        "name": "query_loan_quota",
        "description": "查询贷款额度",
        "required_slots": ["customer_id", "customer_name"]
      }
    ],
    "slots": [
      {
        "name": "customer_name",
        "description": "客户姓名",
        "is_categorical": false
      },
      {
        "name": "loan_amount",
        "description": "贷款金额（万元）",
        "is_categorical": false
      }
    ]
  }]
}
```

**关键价值**：将散乱的对话经验凝练为**机器可读的业务知识图谱**，定义了"哪些信息需要收集、用于什么目的"。

### 3.2 第二步：schema → 可执行代码（可选，仅 PyTOD 需要）

将 `schema.json` 中每个"意图"自动生成对应的 Python API 函数实现，包含：
- 函数签名（参数对应槽位定义）
- 函数体（LLM 生成，经测试验证）
- INTENT_REGISTRY（注册表，供运行时查找调用）

这一步通过**四种代码生成算法**（Loop / Alpha / S* / CTree）迭代生成高质量 API 代码，核心机制：

```
LLM 生成初始函数体
       ↓
自动执行测试用例验证（pass_rate）
       ↓
未达阈值 → LLM 修复（输入当前代码 + 失败用例）
       ↓
循环至通过率达标或达到最大迭代次数
       ↓
输出高质量 API 代码文件
```

---

## 四、结构化数据是如何使用的

结构化数据（schema.json + API 代码）在第三步的五种算法中被不同方式使用：

### 4.1 DST 模式——零样本槽位提取

**使用方式**：schema 中的槽位定义注入提示词，LLM 每轮从对话中提取槽位-值对并累积。

```
用户话语 + 历史对话
    → 提示词（含槽位定义）
    → LLM 返回 JSON：{"customer_name": "李明", "loan_amount": "5万"}
    → 与历史状态合并 → 完整对话状态
```

**适用**：探索型任务、对格式要求不严格的场景。

---

### 4.2 FnCTOD 模式——函数调用式槽位填充

**使用方式**：schema 中的意图/槽位转为 LLM function calling 工具定义，两阶段处理：

```
Stage 1：LLM 选择领域（domain）
Stage 2：LLM 以函数调用格式填充参数
  → <function_call name="apply_loan">{"customer_name": "李明"}</function_call>
  → 约束槽位名称一致性，减少 LLM 自由发挥带来的不稳定
```

**适用**：业务场景明确、需要稳定槽位格式的生产环境。

---

### 4.3 PyTOD 模式——可编程任务型对话（最核心，完整利用三步框架）

**使用方式**：schema 提供函数签名，API 代码提供真实业务实现，三组件协同：

```
用户："帮我查一下账户余额"
    ↓
① Action Parser（LLM）
   输入：schema 函数签名 + 历史对话 + 已计算变量
   输出：Python 程序语句：
         x1 = verify_identity(customer_name="李明")
         x2 = query_balance(user_id=x1.user_id)
         say(x2.balance)
    ↓
② Execution Engine（确定性，无 LLM）
   解析程序语句 → 真实调用注册 API 函数
   管理变量表：{x1: {"user_id": "U001"}, x2: {"balance": "¥8,230"}}
    ↓
③ Dialogue Manager（LLM）
   接收执行结果 → 生成自然语言回复
   "您的账户余额为 ¥8,230.00"
```

**核心创新**：执行引擎调用真实 API，**彻底消除数字/状态类信息的 LLM 幻觉**；跨轮次变量引用（`x2 = query_loan(user_id=x1.user_id)`）实现精准上下文传递。

---

### 4.4 Genie 模式——声明式策略驱动

**使用方式**：schema/Worksheet 声明业务策略字段，确定性状态机驱动对话流程：

```
Worksheet 声明（CSV 表格）：
  user_name → phone → loan_amount → intent（on_success: apply_loan）
                              ↓
用户输入 → LLM-1（仅做语义解析）→ 填充字段
          → PolicyExecutor（纯规则，无 LLM）→ 决定下一步 Ask/Confirm/Report
          → LLM-2（仅做自然语言生成）→ 系统回复
```

**核心创新**：业务策略**完全由声明式表格控制**，LLM 仅负责语义理解和文字生成，业务规则执行零幻觉、可审计。

---

### 4.5 Evolve 模式——演化式长对话记忆

**使用方式**：无需预构建 schema，通过双层记忆架构自动管理长对话上下文：

```
短期记忆（Session）：当前会话完整对话历史
长期记忆（MemoryBank）：跨会话持久化知识
  - FACT（事实）："用户还款记录良好"
  - PREFERENCE（偏好）："用户喜欢简洁回答"
  - EVENT（事件）："2024-01-15 申请了5万贷款"

每轮处理：
  用户输入
  → 检索 Session + MemoryBank（语义相似度，top-K=5）
  → 上下文压缩 + 重排序（相关内容置末尾）
  → LLM 生成回复
  → 异步提取知识 → 进化算法更新记忆库
     （fitness = 使用频率 × 新鲜度 × 置信度，淘汰低质量记忆）
```

**适用**：长期陪伴型对话、开放域聊天、无需预定义业务 schema 的场景。

---

## 五、提取出的上下文如何被使用

上一节（四）描述了各算法**如何提取**上下文；本节聚焦于**提取之后发生了什么**——不同算法对结构化上下文有截然不同的消费方式。

### 5.1 DST / FnCTOD——累积状态驱动下一轮对话

DST 和 FnCTOD 提取的是槽位-值对字典（`{"customer_name": "李明", "loan_amount": "5万"}`），提取后的使用路径有两条：

**路径一：注入下一轮提示词（轮内闭环）**

```
第 N 轮提取结果
     │
     ▼  写入 current_state（累积状态）
第 N+1 轮 Prompt 构建
     │  ← 注入历史槽位 + 本轮对话
     ▼
LLM 基于完整上下文继续追踪，避免遗忘前轮信息
```

**路径二：对外暴露，供业务系统消费（跨系统）**

```python
result = await pipeline.process_turn("我想申请5万")
result["context"]            # 本轮新增槽位：{"loan_amount": "5万"}
result["cumulative_context"] # 全量累积状态：{"customer_name": "李明", "loan_amount": "5万"}
```

业务方可直接读取累积状态，驱动：
- CRM 系统自动填单（客户意图、需求金额等已结构化）
- 对话质检（检查必要字段是否已收集完整）
- 话后小结生成（将槽位值转写为结构化工单）

---

### 5.2 PyTOD——程序语句作为上下文，驱动真实 API 调用

PyTOD 提取的"上下文"不是普通字典，而是**可执行程序语句**（Dataflow Context）：

```
第 N 轮 AP 输出：
  x1 = verify_identity(customer_name="李明")
  x2 = query_balance(user_id=x1.user_id)
  say(x2.balance)

          │
          ▼ 执行引擎（EE）实际调用注册函数
          │ 管理变量表：{x1: {"user_id":"U001"}, x2: {"balance":"¥8,230"}}
          │
          ▼ 变量表随对话历史持久化
第 N+1 轮 AP 输入（Dataflow Context）：
  [已计算变量]
  x1 = verify_identity(customer_name="李明") → {"user_id": "U001"}
  x2 = query_balance(user_id=x1.user_id)    → {"balance": "¥8,230"}

  ← AP 可直接引用 x1.user_id、x2.balance，无需重复提问
```

**关键点**：提取出的程序上下文（变量绑定表）在跨轮次对话中**持续积累**，AP 每轮都能看到所有历史变量及其来源调用，实现精准的跨轮引用，杜绝同一信息被反复索取。

---

### 5.3 Genie——上下文填充 Worksheet，驱动确定性状态机

Genie 从语义解析（LLM-1）中提取字段值后，上下文的后续使用完全由**确定性 PolicyExecutor** 处理：

```
提取结果：{"user_name": "张三", "phone": "138xxxx5678"}
          │
          ▼ executor.fill_batch(extracted)
          │ 更新 Worksheet 状态
          │   user_name: FILLED   ✓
          │   phone:     FILLED   ✓
          │   loan_amount: EMPTY  ←── 下一个需要收集的字段
          │
          ▼ PolicyExecutor 计算 AgentActs（纯规则，无 LLM）
          │   AskAgentAct(field="loan_amount")
          │
          ▼ on_success 触发（字段完整时自动调用注册 API）
          │   check_credit(user_name="张三", phone="138xxxx5678")
          │
          ▼ ResponseGenerator（LLM-2）依据 AgentActs 生成自然语言回复
          "请问您需要申请多少金额的贷款？"
```

上下文的使用完全**可预期、可审计**——每次提取后状态机的下一步动作完全由 Worksheet 声明决定，不依赖 LLM 的"临场判断"。

---

### 5.4 Evolve——提取的知识写入记忆库，跨会话持续增强

Evolve 对上下文的使用是**异步的、跨会话的**，分两个阶段：

**阶段一：知识提取（当轮对话结束后，后台异步执行）**

```
对话结束
  → LLMBasedExtractor 分析本轮对话内容
  → 提取结构化知识条目（FACT / PREFERENCE / EVENT）
  → 进化算法评估并写入 MemoryBank：
      fitness = 使用频率 × 新鲜度 × 置信度
      相似知识合并（余弦相似度 > 0.85）
      超出容量时淘汰低适应度条目
```

**阶段二：记忆检索（下一轮对话开始时）**

```
新一轮用户输入
  → SemanticSearchRetriever 在 MemoryBank 中语义检索（top-K=5）
  → 将相关记忆注入 Prompt（## 已知信息 区块）
  → LLM 基于长期记忆 + 当前输入生成个性化回复

示例（第 N+10 轮）：
  系统 Prompt 中注入：
    ## 已知信息
    - 用户姓名：张三
    - 用户喜欢简洁回答
    - 用户曾于2024-01-15申请了5万贷款
  → LLM 无需重新询问，直接基于记忆进行个性化服务
```

---

### 5.5 所有模式共有：ContextPipeline 统一上下文出口

无论使用哪种算法，`ContextPipeline.process_turn()` 均对外统一暴露两个上下文字段，供调用方使用：

| 字段 | 内容 | 典型用途 |
|------|------|---------|
| `result["context"]` | **本轮**新提取的状态/槽位/知识 | 实时监控、逐轮分析 |
| `result["cumulative_context"]` | **全量累积**上下文（跨所有轮次） | CRM 填单、话后小结、质检 |

```python
result = await pipeline.process_turn("我是李明，想申请5万贷款")
print(result["context"])
# {"customer_name": "李明", "loan_amount": "5万"}

print(result["cumulative_context"])
# {"customer_name": "李明", "loan_amount": "5万", "phone": "138xxxx5678"}  ← 含历史轮次
```

---

## 六、我做的工作

### 6.1 构建了完整的三步上下文工程框架

从零设计并实现了"**知识库构建 → Schema 数据生成 → 算法执行**"三步式框架，通过 `ContextPipeline` 将其统一为可复用的工程体系。对于任意业务场景（银行外呼、保险咨询、电商客服等），只需提供原始对话数据，即可完成端到端的上下文优化接入。

### 6.2 实现了五种上下文提取算法

五种算法覆盖从轻量到精密的全谱系场景需求：

| 算法 | 核心创新点 | 最适场景 |
|------|-----------|---------|
| **DST** | 零样本提示词槽位提取 | 快速验证、探索型任务 |
| **FnCTOD** | 函数调用约束输出格式 | 生产环境业务槽位提取 |
| **PyTOD** | 程序执行 + 真实 API 调用，消除幻觉 | 需要调用真实业务系统的任务型对话 |
| **Genie** | 声明式 Worksheet 状态机，策略可靠 | 严格业务流程、外呼营销 |
| **Evolve** | 双层记忆 + 进化算法，长对话记忆 | 开放域长期对话 |

### 6.3 实现了 LLM 驱动的自动知识库构建

**GenericDialogueDiscoverer + SchemaSynthesizer** 两阶段流水线，将任意格式的原始对话数据自动转化为标准化 `schema.json`，降低上下文优化的接入成本。

### 6.4 实现了 PyTOD API 代码自动生成（四种策略）

`schema_builder/pytod/codegen/` 中实现了四种代码生成策略（Loop、Alpha、S*、CTree），使用"生成 → 验证 → 迭代修复"的闭环流程，自动生成高质量的业务 API Python 实现，免去人工编写 API stub 的繁琐工作。

---

## 七、算法步骤依赖矩阵

| 算法 | 第一步：建立知识库 | 第二步：Schema 数据生成 | 第三步：算法执行 |
|------|:-----------------:|:---------------------:|:--------------:|
| **DST** | 可选 | ❌ 不需要 | ✅ 必须 |
| **FnCTOD** | 可选 | ❌ 不需要 | ✅ 必须 |
| **PyTOD** | 可选 | 可选 | ✅ 必须 |
| **Evolve** | ❌ 不需要 | ❌ 不需要 | ✅ 必须 |
| **Genie** | 可选 | ❌ 不需要 | ✅ 必须 |

---
