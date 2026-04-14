# ContextMind 评测数据集策略深度分析

> **任务背景**：评测方法框架已在 `contextmind_evaluation_framework_analysis.md` 中建立，本文档专注解决评测的另一半——**数据集问题**。TransferTOD、RiSAWOZ 是现有公开数据集，业务侧有无标注对话数据。本分析回答：哪些数据集能支撑 ContextMind 整个框架及各步骤的评测？如何弥补数据集缺口？
>
> **分析日期**：2026-04-14

---

## 一、评测对象的分解：ContextMind 各步骤需要什么数据？

在讨论数据集之前，必须先明确 ContextMind 的处理流水线及每个步骤的评测需求。ContextMind 是一个多阶段的系统，每个阶段都有独立的评测需求，因此数据需求也各不相同。

### 1.1 ContextMind 完整流水线图

```
阶段 1：知识库构建（离线）
  原始对话数据
       │
       ▼
  KnowledgeBaseBuilder.build()
    ├── discoverer.py（意图发现）
    ├── synthesizer.py（意图合并/精炼）
    └── normalizer.py（格式标准化）
       │
       ▼
  [产出] KB（意图 + 槽位 + 示例对话）

阶段 2：Schema 构建（离线）
  KB（阶段 1 产出）
       │
       ▼
  SchemaDataBuilder（schema_builder/）
    ├── Phase 1: 测试用例预生成（TestCaseGenerator）
    ├── Phase 2: 代码草稿生成（PyTOD codegen: loop/alpha/sstar/ctree）
    ├── Phase 3: 迭代修复（validate + repair, max 3 rounds）
    ├── Phase 4: 最终验证（validate_pytod_apis_source）
    └── Phase 5: 写出
       │
       ▼
  [产出] *_pytod_apis.py（可执行 Python API 函数）

阶段 3：运行时对话（在线）
  用户输入
       │
       ▼
  AdkPyTODTracker（modes/pytod/tracker.py）
    ├── AP（Action Parser）：调用 schema 中的 API 函数
    │     ├── 决策：选哪个 intent → 调用哪个 API
    │     ├── 参数：从对话历史中提取 slot 值
    │     └── 失败：调用 NONE() 表示无法处理
    ├── DM（Dialogue Manager）：生成用户响应
    └── ExecutionEngine：执行 API 调用，管理 prior_dataflow
       │
       ▼
  [产出] 对话轨迹、prior_dataflow、task_result
```

### 1.2 各阶段的评测目标与数据需求

| 阶段 | 评测目标 | 所需数据类型 | 难度 |
|------|---------|------------|------|
| **阶段 1：KB 构建** | 从对话中提取的意图/槽位是否正确？ | 有标注的对话数据（意图+槽位 ground truth）| ⭐⭐ |
| **阶段 2：Schema 构建** | 生成的 PyTOD API 代码是否正确可执行？ | 带 Schema 定义的测试用例 | ⭐ |
| **阶段 3a：AP 评测** | AP 是否调用了正确的 API、传递了正确参数？ | 带 API 调用标注的多轮对话（golden trajectory）| ⭐⭐⭐⭐ |
| **阶段 3b：DST 评测** | 对话状态追踪是否准确（槽位填充）？ | 带 DST 标注的多轮对话 | ⭐⭐⭐ |
| **阶段 3c：端到端评测** | 整个系统能否完成任务（pass@1）？ | 完整的端到端场景与预期结果 | ⭐⭐⭐⭐⭐ |
| **上下文质量评测** | 各组件 token 效率、信噪比 | 运行日志（从系统自身产生）| ⭐ |
| **KB 完整性评测** | KB 是否覆盖了所有真实用户意图？ | 真实业务对话（有/无标注均可）| ⭐⭐ |

**核心发现**：ContextMind 的评测需求呈现出"金字塔结构"——底层（KB、DST）有现成数据集可用，顶层（端到端 pass@1、AP 调用评测）严重缺乏数据，必须专门构建。

---

## 二、现有可用数据集的深度分析

### 2.1 TransferTOD：最直接可用的评测数据集

**基础信息**：
- 语言：中文
- 规模：30 个领域，训练集 4,320 条，域内测试 540 条，域外测试（OOD）600 条
- 标注类型：意图标签 + 槽位名 + 槽位值（对话状态标注）
- 当前集成状态：✅ DST 模式（`run_dst_transfertod.py`）、✅ FnCTOD 模式（`run_fnctod_transfertod.py`）

**TransferTOD 可以直接支撑的评测维度**：

| 评测指标 | 支撑方式 | 数据质量 |
|---------|---------|---------|
| **DST 准确率（槽位填充）** | 用标注的槽位值作为 ground truth，与 ContextMind 的 DST 模式输出对比 | ✅ 优质，EMNLP 2024 发表 |
| **意图识别准确率（intent_accuracy）** | 用 `intent_labels_30_domains_Version2.json` 中的意图标签作为 ground truth | ✅ 已有配置（`benchmark/shared/configs/`）|
| **OOD 泛化能力** | 用 OOD Test（3 个新领域）评测 KB 构建对未知域的适应性 | ✅ 独特价值：唯一有 OOD 测试集的中文数据集 |
| **KB 构建质量（阶段 1 评测）** | 从 TransferTOD 对话构建 KB，与官方 Schema 对比 Precision/Recall | ✅ 有 Schema ground truth（30 个领域的意图/槽位定义）|

**TransferTOD 的关键局限**：

1. **没有 API 调用序列标注**：TransferTOD 记录的是对话状态（槽位值），但没有"在每一轮调用了哪个 API、传入了什么参数"的标注。这意味着无法直接评测 AP 的 API 调用决策。

2. **没有任务完成标注**：每条对话没有"是否成功完成了任务"的 ground truth 标签，无法直接计算 pass@1。

3. **没有 prior_dataflow 标注**：TransferTOD 不记录 API 返回值的流转，无法评测 prior_dataflow 机制的正确性。

4. **域结构与 ContextMind Schema 格式不完全匹配**：TransferTOD 的意图/槽位定义是扁平的，而 ContextMind 的 Schema 是嵌套的（service → intent → slot）。适配需要一定的转换工作。

**TransferTOD 的最高优先级用途**：

```
优先级 P1：KB 构建质量评测（阶段 1 评测）
  - 用 TransferTOD 的 27 个领域对话喂给 KnowledgeBaseBuilder
  - 将提取出的意图/槽位与 TransferTOD 官方 Schema 对比
  - 计算：intent_precision, intent_recall, intent_F1, slot_coverage

优先级 P1：DST 准确率评测（阶段 3b 评测）
  - 继续当前已有的 run_dst_transfertod.py 使用
  - 用 OOD Test 作为 KB 泛化能力的压力测试

优先级 P2：意图识别评测（阶段 3a 部分评测）
  - 将对话状态变化解读为意图调用，与 AP 决策对比
  - 注意：这不是真正的 API 调用评测，而是意图层面的代理指标
```

---

### 2.2 RiSAWOZ：中文多领域深度标注数据集

**基础信息**：
- 语言：中文
- 规模：12 个领域，11,200 条对话，~35% 多领域对话（每条对话可能跨 2 个领域）
- 标注类型：意图 + 槽位 + 槽位值 + 关系标注（实体之间的关系）
- 当前集成状态：✅ DST 模式（`run_dst_risawoz.py`）

**RiSAWOZ 对 ContextMind 的独特价值**：

| 独特特点 | 评测价值 |
|---------|---------|
| **多领域对话（~35%）** | 评测 ContextMind 在跨域切换时的上下文管理能力 |
| **丰富关系标注** | 可用于评测 KB 中实体关系的正确性（DDC 的实体元模型质量）|
| **规模大（11,200 条）** | 可以构建统计意义更强的评测（比 TransferTOD 的 540 条测试集更大）|
| **12 个中文场景** | 更贴近国内业务场景（景点、酒店、餐厅、医院等）|

**RiSAWOZ 的关键局限**：

与 TransferTOD 相同，没有 API 调用序列标注，无法直接支撑端到端评测。此外，RiSAWOZ 的多领域对话在 ContextMind 中有一个特殊挑战：ContextMind 目前是**单 Schema 模式**（每个 Schema 对应一个服务域），而 RiSAWOZ 的跨域对话需要动态切换 Schema，这在当前架构中并未实现。

**RiSAWOZ 的最高优先级用途**：

```
优先级 P1：大规模 DST 评测基准
  - RiSAWOZ 的 11,200 条 × 35% 多领域 = 约 3,900 条跨域对话
  - 这是 ContextMind 跨域上下文管理的压力测试数据集

优先级 P2：KB 密度与完整性评测
  - 从 RiSAWOZ 对话提取 KB，评测：kb_density（每意图平均槽位数）
  - 与官方 Schema 对比：kb_coverage_rate, exemplar_coverage
  
优先级 P3：信息可见度（Information Visibility）评测的基础数据
  - 多领域对话创造了更复杂的 prior_dataflow 场景
  - 可以测试 Context Cartography 的 Displacement 效果（跨域信息如何被清除）
```

---

### 2.3 SGD（Schema-Guided Dialogue）：PyTOD 的官方数据集

**基础信息**：
- 语言：英文
- 规模：22,825 条对话，16 个领域，26 个服务，214 个槽位
- 标注类型：意图 + 槽位 + API 调用标注（✅ **有 API 调用序列**）+ 服务 Schema
- 当前集成状态：⚠️ 文档中标记为"评测集成待完成"（`datasets.md`）

**SGD 的决定性优势：有 API 调用序列标注**

这是 SGD 与 TransferTOD/RiSAWOZ 最重要的区别。SGD 记录了每轮对话中发生的 API 调用，包括：
- 调用了哪个 service_call（意图）
- 传递了哪些 slot 参数及其值
- API 返回了什么状态

这直接对应 ContextMind AP 的行为，使得 AP 调用准确率（intent_accuracy）和参数准确率（slot_fill_completeness）的评测成为可能。

**SGD 可以支撑的评测维度**：

| 评测指标 | 支撑方式 | 质量 |
|---------|---------|------|
| **AP 调用准确率（intent_accuracy）** | 与 SGD 记录的 API 调用序列对比 | ⭐⭐⭐⭐ 最强 |
| **槽位填充准确率（slot_fill_completeness）** | 与 SGD 记录的 slot 参数值对比 | ⭐⭐⭐⭐ 最强 |
| **KB 构建质量** | SGD 有完整的 26 个 Schema，与 KnowledgeBaseBuilder 产出对比 | ⭐⭐⭐⭐ |
| **PyTOD 代码质量（阶段 2 评测）** | SGD 是 PyTOD 的官方数据集，有配套的 Python API 参考实现 | ⭐⭐⭐⭐⭐ 最权威 |
| **多轮状态管理** | SGD 的 22,825 条对话提供丰富的多轮场景 | ⭐⭐⭐ |

**SGD 的关键局限**：

1. **英文数据集**：如果 ContextMind 的主要应用场景是中文，SGD 的评测结果在语言上存在迁移差距。
2. **没有显式的"任务完成"标签**：仍然无法直接计算 pass@1（是否"成功完成任务"需要额外定义）。
3. **需要格式适配**：SGD 的 API 调用格式需要转换为 ContextMind 的 PyTOD 格式。

**SGD 的最高优先级用途**：

```
优先级 P0（最高）：AP 调用准确率基准——现有数据集中唯一能做到这一点的
  - 将 SGD 对话喂给 ContextMind AP
  - 比较 AP 决策的 API 调用 vs SGD ground truth API 调用
  - 计算：intent_accuracy, slot_fill_completeness, none_rate

优先级 P0（最高）：PyTOD 代码质量评测（阶段 2 基准）
  - SGD 作为 PyTOD 的官方 benchmark，是 schema_builder 质量的权威评测
  - 用 SGD Schema 驱动 schema_builder，评测生成代码的正确性

优先级 P1：KB 构建流水线的端到端评测
  - 从 SGD 对话（忽略 Schema ground truth）跑 KB 构建
  - 将提取的 KB 与 SGD Schema 对比
  - 量化 KnowledgeBaseBuilder 的 Precision, Recall, F1
```

**SGD 集成的紧迫性**：

`datasets.md` 中 SGD 的 PyTOD 支持状态标记为"⏳"（待完成），但 SGD 是评测 AP 调用准确率的**唯一现成可用的公开数据集**。在业务 golden trajectories 建立之前，SGD 是填补 AP 评测空白的最高优先级工作。

---

### 2.4 τ-Banking（来自 τ-Knowledge 论文）

**基础信息**：
- 来源：arXiv:2603.04370，Sierra Research 团队
- 语言：英文
- 规模：约 700 个文档 + 多步对话场景
- 标注类型：✅ 完整的 API 调用序列 + ✅ 合规性约束 + ✅ 任务完成标签
- 可用性：**需要确认是否开源**（论文发布时间为 2026 年 3 月，开源状态待查）

**τ-Banking 的决定性价值：唯一同时具备 API 调用序列 + 任务完成标签 + 合规约束的数据集**

τ-Banking 场景（金融客服 Agent）与 ContextMind 的主要应用场景**高度重叠**：
- 需要从非结构化文档（政策、流程）中检索知识
- 执行多步 API 调用（身份验证→查询→操作→确认）
- 遵守业务合规约束（单日限额、前置验证等）

**τ-Banking 可以支撑的评测**：

| 评测指标 | 质量 | 说明 |
|---------|------|------|
| **pass@1（任务完成率）** | ⭐⭐⭐⭐⭐ | 有显式任务完成标签，是真正的 pass@1 |
| **policy_compliance_rate（合规率）** | ⭐⭐⭐⭐⭐ | 有合规约束定义，可自动验证 |
| **retrieval_precision（检索精确率）** | ⭐⭐⭐⭐ | 有 700 文档的 ground truth 检索答案 |
| **multi-step_success_rate（多步成功率）** | ⭐⭐⭐⭐⭐ | 明确记录每步操作结果 |

**行动建议**：立即调研 τ-Knowledge 数据集的开源状态。如果开源，τ-Banking 是 ContextMind 建立 pass@1 基准的最快路径，同时提供与学术界基准线（25.5%）的直接对比能力。

---

## 三、业务对话数据（无标注）的处理策略

用户提到有"业务上的对话数据（无标注）"。这是 ContextMind 最有价值但也最难处理的数据来源，需要专门的策略。

### 3.1 无标注业务数据的四层价值

| 价值层 | 用途 | 需要标注？ | 使用方式 |
|-------|------|---------|---------|
| **L1：KB 构建原料** | 直接用于建设领域知识库 | ❌ 不需要 | 喂给 KnowledgeBaseBuilder，自动提取意图/槽位 |
| **L2：意图分布分析** | 了解真实用户意图的分布，指导 KB 完整性评测 | ⚠️ 需要最小标注 | 聚类分析 + 少量人工标注确认 |
| **L3：失败案例挖掘** | 识别 ContextMind 的弱点，指导改进方向 | ⚠️ 需要中等标注 | 运行 ContextMind，收集 NONE() 调用，人工分析原因 |
| **L4：Golden Trajectory 构建** | 建立 pass@1 评测基准 | ✅ 需要完整标注 | 挑选典型对话，人工标注完整轨迹 |

### 3.2 无标注数据的"最小标注"策略（DDC 方法论）

直接参考 `ddc_analysis.md` 中的 DDC（Demand-Driven Context）方法论，这是处理无标注业务数据最具成本效益的策略：

**阶段 1：运行-失败-分析循环（零标注成本）**

```
① 将无标注业务对话喂给 KnowledgeBaseBuilder → 自动提取初始 KB
② 在 KB 上运行 ContextMind，对真实用户输入进行模拟响应
③ 收集所有 NONE() 调用（自动记录）
④ 对 NONE() 调用按意图聚类（LLM 辅助）
⑤ 识别出"高频未覆盖意图"
```

这个阶段**不需要任何人工标注**，但可以产出：
- 业务数据的意图分布热图（哪些意图最常被请求）
- KB 覆盖率初估（哪些意图 ContextMind 无法处理）
- `kb_coverage_rate` 的业务场景版基线

**阶段 2：失败驱动的最小标注（低成本）**

```
① 挑选 NONE() 率最高的 Top 20 个意图场景
② 人工确认：这些场景的正确 API 调用是什么？
③ 补充到 KB 中（DDC 的"按需补充"原则）
④ 重新运行，验证 NONE() 率是否下降
⑤ 记录每个 DDC 循环的 new_intent_count 和 none_rate_change
```

**关键收益**：用 20-30 个人工确认（DDC 论文的收敛假设）替代全量数据标注，就能覆盖 80% 的真实场景。

**阶段 3：Golden Trajectory 的精准构建（中等成本）**

```
① 从业务数据中挑选"任务类型明确、对话完整"的典型对话（约 100-200 条）
② 对每条对话标注：
   - 每轮的正确 API 调用（intent + slot values）
   - 是否成功完成任务（二值标签）
   - 违反的合规规则（如有）
③ 使用 LLM（如 GPT-4）辅助初始标注 + 人工审核（节省 70% 标注时间）
④ 这 100-200 条 golden trajectories 直接用于 pass@1 计算
```

### 3.3 LLM 辅助标注流程（具体操作方案）

对于无标注业务数据的 Golden Trajectory 构建，推荐以下 LLM 辅助流程：

**Step 1：自动意图识别**
```
Prompt: 这是一段客服对话，请识别用户在每一轮的意图（从以下已知意图中选择，
        或标注为"未知意图"）：
        [已知意图列表：来自 ContextMind 当前 KB]
        
        对话内容：{dialogue_text}
        
        输出格式：[{turn_id: 1, intent: "查询余额", confidence: 0.9}, ...]
```

**Step 2：槽位值自动提取**
```
Prompt: 对于以下对话中识别到的意图，提取每个槽位的值：
        意图：{intent_name}
        所需槽位：{required_slots}
        对话上下文：{relevant_turns}
        
        输出格式：{slot_name: slot_value, ...}
```

**Step 3：任务完成自动判断**
```
Prompt: 根据对话结尾，判断用户的任务是否成功完成？
        评判标准：用户明确表示满意 或 系统确认了操作完成 → 成功
        
        对话：{full_dialogue}
        输出：{completed: true/false, reason: "..."}
```

**Step 4：人工审核（20% 抽样）**
- 对 LLM 标注结果进行 20% 抽样人工复核
- 重点审核：confidence < 0.7 的标注、被标注为"未知意图"的轮次
- 修正错误标注，将修正结果反馈给 LLM 提示词

**预期成本**：100 条对话的 Golden Trajectory 构建，LLM 辅助后人工时间约 8-16 小时（vs 无 LLM 辅助的 40-80 小时）。

---

## 四、数据集缺口分析与补充方案

### 4.1 三个关键缺口

通过上述分析，ContextMind 评测数据集存在三个关键缺口：

**缺口 1：端到端任务完成标签（pass@1 评测的前提）**

- **现状**：TransferTOD、RiSAWOZ 都没有"任务是否完成"的 ground truth 标签
- **影响**：无法计算 ContextMind 最核心的评测指标 pass@1
- **严重程度**：🔴 严重（这是 τ-Knowledge 论文 25.5% 警报的直接指向）
- **填补方案**：见第五节"Golden Trajectory 构建方案"

**缺口 2：合规约束验证数据**

- **现状**：三个公开数据集都没有显式的"业务合规规则"标注
- **影响**：无法计算 `policy_compliance_rate`，无法检测 AutoHarness 式的非法动作
- **严重程度**：🟡 中等（影响安全性评测，但不影响功能性评测）
- **填补方案**：手工定义每个业务场景的合规规则（参考 τ-Knowledge 的合规约束设计）

**缺口 3：API 返回值的 prior_dataflow 评测**

- **现状**：所有数据集都不记录 API 的实际返回值（只记录 slot values，不记录函数返回）
- **影响**：无法评测 prior_dataflow 机制的正确性（变量引用准确率）
- **严重程度**：🟡 中等（影响 Context Cartography 相关指标的评测）
- **填补方案**：在 ContextMind 运行时自动记录 prior_dataflow 使用情况（无需外部数据集）

### 4.2 合成数据集方案（弥补 API 调用序列缺口）

如果 τ-Banking 未开源，且 SGD 的英文-中文差距无法接受，可以构建领域特定的**合成评测数据集**：

**方案：Schema 驱动的合成对话生成**

基于 ContextMind 已有的 Schema（业务方已有的 schema.json），用 LLM 生成合成评测场景：

```
Step 1：从 Schema 中提取所有意图和槽位定义

Step 2：对每个意图生成 N 个合成用户查询（N=10-20）
  Prompt: 你是一个真实用户，你想要{intent_description}。
          生成一段自然的对话开始语，可以包含以下信息（随机挑选部分）：
          {random_slots_from_schema}

Step 3：生成期望的 AP 响应（Golden API Call）
  Prompt: 对于用户输入{user_query}，在{service_description}这个服务中，
          应该调用哪个 API？传入哪些参数？
          可用 API：{api_signatures}
          输出：{intent: "...", slots: {...}}

Step 4：生成完整的多轮 Golden Trajectory
  - 将单意图场景组合成多意图场景（模拟真实多步对话）
  - 验证：用 ContextMind 的 ExecutionEngine 验证 API 调用能够执行

Step 5：人工审核（30% 抽样）
  - 检查合成对话的自然度
  - 验证 Golden API Call 的正确性
```

**合成数据的可信度限制**：合成数据存在"LLM 自我评测"的偏差——用 LLM 生成数据再用 LLM 评测，存在系统性盲点。因此合成数据只能作为**补充**，不能替代真实标注数据。建议：
- 合成数据用于基础功能验证和快速迭代（低成本）
- 真实标注数据用于最终报告和对外对标（高可信度）

---

## 五、Golden Trajectory 构建方案（核心缺口填补）

Golden Trajectory 是整个评测体系的核心基础数据，没有它就无法计算 pass@1。以下是具体的构建方案：

### 5.1 Golden Trajectory 的数据结构定义

参考 τ-Knowledge 的评测框架，ContextMind 的 Golden Trajectory 应包含：

```json
{
  "trajectory_id": "bank_001",
  "scenario_type": "account_balance_inquiry",
  "schema_name": "banking_service",
  "difficulty": "easy",
  
  "dialogue": [
    {
      "turn_id": 1,
      "role": "user",
      "text": "我想查一下我的账户余额",
      "ground_truth": {
        "intent": "query_balance",
        "slots": {},
        "api_call": null,
        "ap_expected": "NONE()",
        "dm_goal": "请求身份验证"
      }
    },
    {
      "turn_id": 2,
      "role": "agent",
      "text": "请问您的账号是？"
    },
    {
      "turn_id": 3,
      "role": "user",
      "text": "是 622848XXXX1234",
      "ground_truth": {
        "intent": "verify_identity",
        "slots": {"account_number": "622848XXXX1234"},
        "api_call": {
          "function": "verify_identity",
          "params": {"account_number": "622848XXXX1234"}
        },
        "ap_expected": "verify_identity(account_number='622848XXXX1234')",
        "prior_dataflow_expected": {"x1": {"status": "verified", "account_id": "..."}}
      }
    }
  ],
  
  "task_definition": {
    "success_condition": "所有 required_intents 均成功调用且返回 success",
    "required_intents": ["verify_identity", "query_balance"],
    "policy_constraints": [
      "query_balance 必须在 verify_identity 成功后调用",
      "account_number 必须通过格式验证（16-19位数字）"
    ],
    "failure_conditions": ["verify_identity 失败则终止", "连续 3 次 NONE() 则判定失败"]
  },
  
  "ground_truth_outcome": {
    "task_completed": true,
    "completion_turn": 5,
    "required_intents_called": ["verify_identity", "query_balance"],
    "no_policy_violations": true
  }
}
```

### 5.2 Golden Trajectory 的分层构建策略

**从已有数据集出发，逐步扩展到业务场景：**

**第一批（0成本，SGD 已有 API 调用标注）**：
- 选取 SGD 中 5 个与业务最相近的服务领域
- 将 SGD 的 API 调用标注转换为 ContextMind 的 Golden Trajectory 格式
- 预计 200-500 条，覆盖英文基础场景
- 用途：快速建立 pass@1 计算能力（但指标只代表英文场景）

**第二批（低成本，基于 TransferTOD + LLM 辅助）**：
- 从 TransferTOD 测试集中挑选 10 个领域 × 10 条对话 = 100 条
- 用 LLM 为每条对话添加 API 调用标注（参考第三节的 LLM 辅助流程）
- 人工审核 30%
- 预计总工时：20-30 小时
- 用途：中文场景的基础 pass@1 评测

**第三批（中等成本，业务场景专属）**：
- 从无标注业务数据中挑选 100-200 条典型对话
- 完整标注 Golden Trajectory（包含 task_definition 和 policy_constraints）
- 这是最有商业价值的评测数据集（领域精准、真实场景）
- 预计总工时：80-120 小时（含 LLM 辅助）
- 用途：业务 pass@1 基准、合规性评测、对外展示的核心数字

### 5.3 Golden Trajectory 的版本控制策略

Golden Trajectory 是一种容易随业务变化而过时的数据。建议：

```
resources/
└── benchmark/
    ├── golden_trajectories/
    │   ├── v1.0_sgd_adapted/           # 第一批
    │   │   ├── scenarios.json
    │   │   └── metadata.json           # 来源、标注时间、标注者
    │   ├── v1.1_transfertod_cn/        # 第二批
    │   └── v2.0_business_domain/       # 第三批（最重要）
    └── evaluation_configs/
        ├── baseline_config.json        # 基线评测配置
        └── regression_config.json     # 回归测试配置（每次 KB 更新后运行）
```

---

## 六、各评测指标的数据集覆盖矩阵

### 6.1 完整覆盖矩阵

以下矩阵显示每个评测指标应该用哪个数据集：

| 评测指标 | SGD | TransferTOD | RiSAWOZ | τ-Banking | Business Data | Golden Traj | 日志（实时）|
|---------|-----|------------|---------|-----------|--------------|------------|-----------|
| **pass@1** | ⚠️需转换 | ❌ | ❌ | ✅最强 | ⚠️需标注 | ✅ | ❌ |
| **intent_accuracy** | ✅最强 | ✅(代理) | ✅(代理) | ✅ | ⚠️需标注 | ✅ | ❌ |
| **slot_fill_completeness** | ✅最强 | ✅ | ✅ | ✅ | ⚠️需标注 | ✅ | ❌ |
| **none_rate** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅最强 |
| **illegal_action_rate** | ❌ | ❌ | ❌ | ✅ | ⚠️需规则 | ⚠️需规则 | ✅ |
| **policy_compliance_rate** | ❌ | ❌ | ❌ | ✅ | ⚠️需规则 | ✅ | ❌ |
| **kb_coverage_rate** | ✅ | ✅ | ✅ | ⚠️部分 | ✅(NONE分析) | ❌ | ✅ |
| **kb_density** | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ |
| **tokens_per_turn** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅最强 |
| **privilege_excess** | ⚠️部分 | ❌ | ❌ | ❌ | ❌ | ⚠️部分 | ✅ |
| **variable_reference_accuracy** | ❌ | ❌ | ❌ | ❌ | ❌ | ⚠️部分 | ✅最强 |
| **cache_efficiency** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅最强 |
| **context_relevance** | ✅(计算) | ✅(计算) | ✅(计算) | ✅ | ✅(计算) | ✅ | ✅ |
| **OOD 泛化性** | ⚠️弱 | ✅强(3域) | ⚠️弱 | ❌ | ⚠️ | ❌ | ❌ |
| **多领域切换** | ⚠️弱 | ⚠️弱 | ✅强(35%) | ❌ | ⚠️ | ❌ | ❌ |

**关键观察**：
- `none_rate`、`tokens_per_turn`、`cache_efficiency`、`variable_reference_accuracy` 这类指标**不依赖外部数据集**，从系统运行日志中直接获取
- `pass@1`、`policy_compliance_rate` 是需要专门构建数据的高价值指标
- SGD 是最全面的 API 调用评测数据集，其集成是当前最高优先级

### 6.2 数据集组合的覆盖评分

| 数据集组合 | 覆盖评测指标数 | 覆盖质量 | 推荐程度 |
|-----------|-------------|---------|---------|
| TransferTOD + RiSAWOZ（当前状态） | ~6/15 | ⭐⭐ 良好（DST 为主） | 基础水平，需要补充 |
| + SGD 集成 | ~10/15 | ⭐⭐⭐ 较好（增加 API 调用评测）| 强烈推荐，优先级最高 |
| + Golden Trajectory（业务场景）| ~13/15 | ⭐⭐⭐⭐ 好（增加 pass@1）| 必须建立 |
| + 系统日志监控 | 15/15 | ⭐⭐⭐⭐⭐ 完整 | 最终目标 |

---

## 七、分阶段实施路线图

### 阶段 0（立即，0-1 周）：激活已有能力

**不需要任何新数据集，利用系统日志**：

```
行动 1：在 execution_engine.py 中添加 NONE() 调用日志
  - 记录：调用时间、当前对话 ID、用户输入、当前 intent_context 内容
  - 输出：none_rate（按意图、按场景分类）

行动 2：在 prompts.py 中添加 token 统计
  - 在每次 prompt 构建后统计：system_tokens, user_tokens, total_tokens
  - 输出：tokens_per_turn 的实时监控

行动 3：在 tracker.py 中添加 API 调用追踪
  - 记录：每次调用的 API 名称、传入参数、是否在 intent_context 中存在
  - 输出：privilege_excess（未使用的 API 签名比例）
```

**数据需求**：零（从系统自身产生日志）

### 阶段 1（2-4 周）：集成 SGD，建立 AP 评测基线

```
行动 1：完成 SGD 集成（benchmark/runners/run_pytod_sgd.py）
  - 将 SGD 的 API 调用格式转换为 ContextMind 的 PyTOD 格式
  - 实现 API 调用准确率计算逻辑

行动 2：建立 AP 评测基线
  - 在 SGD 的 5 个核心领域上运行评测
  - 记录：intent_accuracy, slot_fill_completeness, none_rate
  - 这些数字是 ContextMind 首个公开发布的评测基线

行动 3：构建第一批 Golden Trajectory（基于 SGD）
  - 将 200 条 SGD 对话转换为 ContextMind Golden Trajectory 格式
  - 建立 pass@1 计算框架（ContextMindEvaluator）
```

**数据需求**：SGD（免费，git clone 即可使用）

### 阶段 2（1-2 月）：构建业务场景评测集

```
行动 1：对业务对话数据运行 DDC 分析
  - 用无标注业务数据构建初始 KB
  - 运行 ContextMind，收集 NONE() 分布
  - 识别 Top 20 高频未覆盖意图

行动 2：LLM 辅助标注第二批 Golden Trajectory
  - 从 TransferTOD 挑选 100 条代表性对话
  - LLM 辅助添加 API 调用标注，人工审核 30%
  - 计算中文场景的 pass@1 基线

行动 3：构建第三批 Golden Trajectory（业务场景）
  - 从无标注业务数据挑选 100-200 条典型对话
  - 完整标注（含 policy_constraints）
  - 这是最重要的业务评测数据，直接反映产品价值
```

**数据需求**：TransferTOD（已有）+ 业务对话数据（已有）+ LLM API（约 $50-100 费用）

### 阶段 3（持续）：建立评测体系的持续运营

```
行动 1：每次 KB 更新后自动运行回归评测
  - 用已建立的 Golden Trajectory 计算 pass@1
  - 与上次基线对比，报告 Δpass@1

行动 2：DDC 循环的量化跟踪
  - 每个 DDC 循环记录：new_intent_count, none_rate_change, kb_coverage_rate
  - 判断 KB 是否达到 DDC 的"收敛条件"（连续 3 轮新增 < 2 个意图）

行动 3：定期更新 Golden Trajectory（业务数据漂移）
  - 每季度对新的业务对话运行 LLM 标注
  - 检测是否出现新的意图类型（分布漂移）
```

---

## 八、关键决策点与权衡分析

### 8.1 数据集语言的权衡

| 选择 | 优势 | 劣势 | 建议 |
|------|------|------|------|
| **只用中文数据集**（TransferTOD + RiSAWOZ）| 语言一致，直接相关 | 缺少 API 调用标注，无法评测 AP | 作为 DST 评测主力 |
| **只用英文数据集**（SGD + τ-Banking）| API 标注完整，学术基准完整 | 语言差距，中文业务场景覆盖不足 | 作为 AP 评测主力 |
| **两者结合（推荐）** | 互补覆盖 | 需要维护两套适配器 | **实际执行方案** |

### 8.2 合成数据 vs 真实标注数据的权衡

| 维度 | 合成数据 | 真实标注数据 |
|------|---------|------------|
| **成本** | 低（LLM API 费用）| 高（人工时间）|
| **速度** | 快（数小时）| 慢（数周）|
| **覆盖度** | 高（可系统生成所有意图组合）| 有限（真实场景才有代表性）|
| **真实性** | 低（LLM 生成的"完美对话"，缺乏真实噪声）| 高（真实用户行为）|
| **偏差风险** | 高（LLM 自我验证）| 低（独立标注）|
| **推荐用途** | 快速原型验证、覆盖度测试 | 对外报告、正式基准 |

**结论**：先合成后真实——在等待真实标注完成的过程中，用合成数据快速迭代开发，最终以真实标注数据做最终验证。

### 8.3 评测频率 vs 评测成本的权衡

| 评测类型 | 频率建议 | 数据需求 | 成本 |
|---------|---------|---------|------|
| **实时监控**（none_rate, tokens）| 每次对话 | 系统日志 | ≈0 |
| **组件评测**（DST 准确率等）| 每次 KB 更新 | TransferTOD/RiSAWOZ | 低 |
| **AP 评测**（intent_accuracy）| 每次 Schema 更新 | SGD Golden Traj | 低 |
| **端到端评测**（pass@1）| 每次重大版本 | 业务 Golden Traj | 中 |
| **全面质量审计** | 每季度 | 全部 | 高 |

---

## 九、结论与优先级总结

### 核心结论

1. **TransferTOD 和 RiSAWOZ 能覆盖 DST 层评测，但无法覆盖 AP 调用评测和 pass@1 评测**。现有集成已到达当前数据集的能力上限。

2. **SGD 是最高优先级的集成工作**。它是唯一公开、免费、有 API 调用序列标注的数据集，能够直接支撑 intent_accuracy、slot_fill_completeness 等核心 AP 指标。当前"待完成"状态是评测体系最大的技术债务。

3. **pass@1 的评测必须通过构建 Golden Trajectory 实现**，没有任何公开数据集可以直接使用。Golden Trajectory 构建是一次性投入（80-120 小时），但它产出的是整个评测体系的基础数据。

4. **无标注业务数据最有商业价值，但需要系统性策略处理**。DDC 方法论（运行-失败-分析-按需补充）是处理无标注数据最具成本效益的方式，应该作为 KB 完整性评测的主要方法。

5. **大量评测指标不依赖外部数据集**（none_rate、tokens_per_turn、cache_efficiency、variable_reference_accuracy），这些指标可以立即通过在现有代码中添加日志采集来实现，成本接近零。

### 行动优先级（按价值/成本比排序）

| 优先级 | 行动 | 成本 | 产出 |
|-------|------|------|------|
| 🥇 **P0** | 系统日志监控（none_rate, token stats）| ≈0（几行代码）| 立即获得免费评测信号 |
| 🥇 **P0** | 集成 SGD 数据集 | 低（1-2周工程）| 首个 AP 调用准确率基线 |
| 🥈 **P1** | 基于 TransferTOD + LLM 辅助的 Golden Trajectory（100条）| 中（20-30h）| 中文场景 pass@1 基线 |
| 🥈 **P1** | 业务数据 DDC 分析（无标注）| 低（自动化）| KB 覆盖率热图，指导改进 |
| 🥉 **P2** | 业务场景 Golden Trajectory（100-200条真实标注）| 高（80-120h）| 最有商业价值的评测数字 |
| 🔵 **P3** | τ-Banking 数据集调研和集成 | 中（取决于开源状态）| 与学术界对标能力 |
| 🔵 **P3** | 合规规则定义（policy_constraints）| 中（业务梳理）| AutoHarness/合规评测能力 |

---

*文档生成于 2026-04-14。基于 docs/research/ 中所有 16 篇论文分析文档及 ContextMind 代码库的综合分析。*
