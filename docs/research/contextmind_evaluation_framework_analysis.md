# ContextMind 上下文质量评测体系深度分析

> **任务背景**：ContextMind 能够提取上下文结果（KB、prior_dataflow、API 签名、对话历史等），但目前缺乏系统性评价机制。本文档从 `docs/research/` 中所有论文分析文档出发，提炼适用于 ContextMind 的评测方式和评测指标。

---

## 一、ContextMind 输出的上下文结构：评测对象分析

在设计评测体系之前，必须首先明确"被评测的对象"是什么。ContextMind 产出的上下文由以下多层组件构成：

### 1.1 离线构建阶段的上下文产出

| 上下文组件 | 文件/位置 | 内容类型 |
|-----------|----------|---------|
| **ServiceSchema（意图+槽位定义）** | `schema_builder/` → `schema.json` | 结构化：服务的 API 能力描述 |
| **KnowledgeBase（知识库）** | `knowledge/` → `kb.json` | 结构化：服务意图、示例对话 |
| **PyTOD API 函数代码** | `schema_builder/pytod/` → `*_pytod_apis.py` | 代码：可执行的 API 函数实现 |
| **discovery_raw（发现记录）** | `knowledge/` → `discovery_raw.json` | 元数据：实体来源追踪 |

### 1.2 运行时构建的上下文（每轮对话）

| 上下文组件 | 构建位置 | 内容类型 |
|-----------|---------|---------|
| **AP System Message** | `modes/pytod/prompts.py` | 权威定义 + API 函数签名 |
| **prior_dataflow** | `modes/pytod/tracker.py` | 已执行 API 的返回值字典 |
| **对话历史（dialogue history）** | `modes/pytod/prompts.py` | 多轮对话文本 |
| **意图上下文（intent context）** | `modes/pytod/prompts.py` | 当前可用意图描述 |
| **current_state** | `modes/pytod/tracker.py` | 已完成意图的状态字典 |
| **DM System Message** | `modes/pytod/prompts.py` | 对话管理指令 |
| **say() 传递的信息** | `modes/pytod/tracker.py` | AP→DM 的信息桥接 |

### 1.3 当前评测基础（已有 benchmark/ 目录）

ContextMind 已在 `benchmark/` 目录下构建了初步评测能力：
- **DST 模式**：`benchmark/runners/run_dst_risawoz.py`、`run_dst_transfertod.py`
- **FnCTOD 模式**：`benchmark/runners/run_fnctod_transfertod.py`
- **意图评测器**：`benchmark/shared/intent_evaluator.py`（slot 变化推断意图，多维度指标）
- **数据集适配**：RisaWOZ、TransferTOD 数据集

**核心差距**：现有 benchmark 评测的是**下游任务表现**（槽位填充准确率、意图识别率），但没有直接评测**上下文本身的质量**（上下文是否相关、是否充分、是否经济）。这是本分析要填补的空白。

---

## 二、各论文提供的评测思想与指标体系（逐一分析）

### 2.1 τ-Knowledge：端到端任务成功率框架

**论文**：`tau_knowledge_analysis.md`（arXiv:2603.04370）

#### 核心评测设计

τ-Knowledge 是迄今为止与 ContextMind 场景最接近的评测论文（金融客服 + 知识检索 + 工具调用）。它的形式化基于 Dec-POMDP（去中心化部分可观测马尔可夫决策过程），要求 Agent 同时具备：
1. 从非结构化文档中检索知识的能力
2. 执行符合政策约束的 API 调用的能力

#### 可直接迁移到 ContextMind 的指标

| τ-Knowledge 指标 | 定义 | 适用 ContextMind 组件 | 计算方式 |
|-----------------|------|---------------------|---------|
| **pass@1** | 首次对话中完整完成任务的成功率 | 整体 Agent（AP+DM）| 与 golden trajectory 对比 |
| **pass@k** | k 次试验中至少一次成功的概率 | 整体 Agent | $1 - (1 - pass@1)^k$ |
| **intent_accuracy** | 意图识别准确率 | AP 的 API 调用决策 | 与 ground truth API 调用对比 |
| **slot_fill_rate** | 槽位填充完整率 | AP 的参数传递 | 必填槽位填充数 / 必填槽位总数 |
| **illegal_action_rate** | 非法 API 调用率 | AP 的 NONE() 调用 | NONE() 调用次数 / 总 AP 决策次数 |
| **policy_compliance** | 业务合规率 | AP 调用顺序是否符合业务流程 | 违反前置条件的 API 调用次数 |
| **retrieval_precision** | 知识检索精确率 | KB 检索（当引入文档检索后）| 检索正确文档 / 检索总文档 |

#### 关键发现对 ContextMind 的警示

τ-Knowledge 发现**最好的 LLM 在金融客服场景的 pass@1 仅 25.5%**，且随对话轮数增加而急剧下降。这意味着：如果 ContextMind 不建立评测，用户无法知道 Agent 在真实场景中的可靠程度。

#### 评测 ContextMind 上下文质量的关键应用

```
context_quality_impact = pass@1(with_better_context) - pass@1(with_baseline_context)
```

通过对比不同上下文配置下的 pass@1，可以量化"上下文工程改进"的实际价值。这是最直接的上下文质量评价方法。

---

### 2.2 Vishnyakova 五准则：上下文质量维度框架

**论文**：`ce_multiagent_analysis.md`（arXiv:2603.09619）

#### 五大质量准则作为评测维度

Vishnyakova 提出的五个质量准则是目前文献中最系统的上下文质量评测框架，每个准则都可以转化为具体的 ContextMind 评测指标：

| 准则 | 定义 | ContextMind 对应评测方式 | 量化指标 |
|------|------|------------------------|---------|
| **Relevance（相关性）** | 上下文与当前任务的匹配程度 | 评测 AP 的 intent_context 是否包含了被成功调用的 API | 有效 API 调用率（调用的 API 在当前上下文中存在的比例）|
| **Sufficiency（充分性）** | 上下文提供了任务所需的所有信息 | 评测 NONE() 调用是否由上下文不足导致 | 上下文不足导致的 NONE() 率 vs 总 NONE() 率 |
| **Isolation（隔离性）** | 不同 Agent 的上下文不相互干扰 | 评测 AP 和 DM 的上下文重叠程度 | AP 上下文 ∩ DM 上下文 / AP 上下文 ∪ DM 上下文 |
| **Economy（经济性）** | 最小化上下文体积同时保持质量 | 评测各组件的 token 效率 | pass@1 / total_tokens（每 token 的任务成功价值）|
| **Provenance（溯源性）** | 追踪上下文信息的来源和可信度 | 评测 prior_dataflow 中数据项的来源标注率 | 有来源标注的数据项 / 总数据项 |

#### 五准则的评测分数计算方式

```python
# Vishnyakova 准则评分（简化版，0-1 区间）
class ContextQualityScore:
    relevance_score: float     # 有效 API 调用率
    sufficiency_score: float   # 1 - (insufficiency_none_rate / total_none_rate)
    isolation_score: float     # 1 - 上下文重叠比例
    economy_score: float       # pass@1 / (total_tokens / reference_token_budget)
    provenance_score: float    # 来源标注覆盖率
    
    @property
    def composite_score(self) -> float:
        # 加权综合分（可调权重）
        weights = [0.3, 0.3, 0.1, 0.2, 0.1]
        scores = [self.relevance_score, self.sufficiency_score, 
                  self.isolation_score, self.economy_score, self.provenance_score]
        return sum(w * s for w, s in zip(weights, scores))
```

#### 深度洞察：Sufficiency 作为上下文诊断工具

Sufficiency 准则最有价值的应用是**诊断 NONE() 调用的根本原因**：

- **NONE() 的两种来源**：
  1. 上下文充分但 LLM 推理失败（模型能力问题）→ 无法通过上下文工程解决
  2. 上下文不足导致 LLM 无法找到合适 API（上下文问题）→ 可以通过上下文工程解决

- **评测价值**：将 NONE() 按来源分类，确定"通过改进上下文可挽回的失败率"，这直接量化了上下文工程的改进上限（ceiling effect）。

---

### 2.3 Tokalator：信息论量化框架

**论文**：`tokalator_analysis.md`（arXiv:2604.08290）

#### Quality Score 公式

Tokalator 提出的质量评分模型是迄今最具可操作性的上下文质量量化方法：

```
Q = α·Relevance + β·Density - γ·Redundancy

其中：
- Relevance：上下文与当前任务的相关性（0-1），可用关键词覆盖率或 TF-IDF 相似度
- Density：信息密度 = 关键信息 token / 总 token（0-1）
- Redundancy：冗余度 = 重复信息比例（0-1）
- 默认权重：α=0.4, β=0.4, γ=0.2
```

#### 适用于 ContextMind 各组件的 Quality Score 计算

| 上下文组件 | Relevance 计算 | Density 计算 | Redundancy 检测 |
|-----------|--------------|-------------|----------------|
| **prior_dataflow** | 被实际引用的变量 / 总变量数 | 关键字段 token / 总 token | 相同 API 被调用多次 |
| **API 函数签名** | 实际被调用的 API 签名 / 总签名 | 函数名+参数 token / 总签名 token | 槽位描述中的重复词语 |
| **对话历史** | 最终用于 API 参数推断的轮次 / 总轮次 | 用户话语 token / 全部历史 token | 用户重复请求的次数 |
| **意图上下文** | 被调用意图 / 展示的意图总数 | 描述性 token / 格式化 token | 跨意图的相似描述 |

#### Cache Efficiency（缓存效率）指标

Tokalator 引入了 Prompt Caching 的效率评测，这对 ContextMind 的成本评估至关重要：

```
cache_efficiency = stable_prefix_tokens / total_tokens_per_turn

其中：
- stable_prefix_tokens：system message + 固定内容的 token 数
- total_tokens_per_turn：每轮总 token 数

目标：cache_efficiency > 0.5（超过一半 token 可以被缓存）
```

ContextMind 当前的缓存效率估算：AP system message（API 签名）约占总 token 的 30-40%，还有提升空间。

#### Signal-to-Noise Ratio（信噪比）

```
SNR = relevant_tokens / (total_tokens - relevant_tokens)
    = Density / (1 - Density)

评分标准：
- SNR > 2.0：优秀（超过 2/3 的 token 是有用信息）
- SNR 1.0-2.0：良好
- SNR < 1.0：需要优化（超过一半 token 是噪声）
```

---

### 2.4 McMillan 实证研究：格式影响评测框架

**论文**：`structured_ce_file_native_analysis.md`（arXiv:2602.05447）

#### 实验设计的可迁移性

McMillan 等进行了 9649 次实验，评测 4 种格式（YAML/Markdown/JSON/TOON）对 11 个模型的影响。这个实验框架对 ContextMind 具有直接的方法论价值：

**格式影响评测指标**：

| 评测维度 | 在 ContextMind 中的实现 | 测量方式 |
|---------|----------------------|---------|
| **Schema Accuracy（Schema 准确率）** | AP 生成的 API 调用参数是否正确 | 参数类型/值与预期匹配率 |
| **Navigation Accuracy（导航准确率）** | AP 在多 API 依赖链中的正确顺序调用率 | 调用顺序与 golden trajectory 的 edit distance |
| **Format Robustness（格式鲁棒性）** | 同一任务在不同格式下的准确率方差 | std(accuracy across formats) |
| **Token Efficiency per Format** | 不同格式下完成同等任务的 token 消耗比 | tokens(format_A) / tokens(format_B) |

#### ContextMind 的格式对比实验框架

参考 McMillan 的实验设计，ContextMind 可以构建如下格式对比实验：

```
实验变量：prior_dataflow 的格式
A: 当前自定义格式（x1 = {"key": "value", ...}）
B: YAML 格式（x1:\n  key: value）
C: TOON 格式（x1 [intent_name]: key=value | ...）
D: Semantic View 格式（意图执行摘要：...）

评测指标：
1. AP 对 prior_dataflow 变量的正确引用率（Schema Accuracy 类比）
2. 每轮总 token 数（Token Efficiency）
3. 整体 pass@1（下游任务成功率）

实验规模：每种格式至少 100 次完整对话，跨 3 个以上场景
```

---

### 2.5 ACE 框架：自我改进评测与 Playbook 质量评测

**论文**：`ace_analysis.md`（arXiv:2510.04618）

#### Evolving Context 的质量评测

ACE 框架将上下文视为"evolving playbooks"，其核心评测问题是：**上下文（Playbook）随时间改善的速度和上限**。

| ACE 评测指标 | 在 ContextMind 中的含义 | 量化方式 |
|------------|----------------------|---------|
| **Improvement Rate** | KB 或 Playbook 更新后的性能提升 | Δpass@1 per update cycle |
| **Convergence Speed** | 上下文收敛到稳定高质量状态的迭代次数 | 与 DDC 的"收敛循环数"协同 |
| **Failure Pattern Coverage** | NONE() 失败模式被 KB 覆盖的比例 | covered_failure_types / total_failure_types |
| **Playbook Staleness** | Playbook 中过时信息的比例 | 过时条目（基于时间戳或版本）/ 总条目 |

#### 关键洞察：通过 NONE() 追踪上下文质量改善

ACE 最重要的测量是 NONE() 调用率随时间的变化曲线。这个指标对 ContextMind 的上下文质量评测有直接价值：

```
context_quality_improvement_index(t) = 1 - (NONE_rate_at_t / NONE_rate_at_t0)

其中：
- NONE_rate_at_t：在时间 t 的 NONE() 调用率
- NONE_rate_at_t0：初始基线 NONE() 调用率
- 指数越接近 1.0，表示上下文质量改善越显著
```

这个指标可以直接用于评估：
1. KB 更新是否有效降低了 NONE() 率
2. 不同上下文工程策略的效果对比
3. 上下文质量是否持续改善（ACE 的进化效果）

---

### 2.6 DT-MDP-CE：奖励函数学习框架

**论文**：`dt_mdp_ce_analysis.md`（arXiv:2603.22083）

#### 上下文工程的 MDP 视角评测

DT-MDP-CE 的核心思想是：上下文工程决策（选择哪些信息放入 prompt）是一个 MDP 中的动作，其质量可以用奖励函数评测。

**状态-动作-奖励的评测框架**：

| MDP 组件 | ContextMind 对应 | 评测意义 |
|---------|-----------------|---------|
| **State（状态）** | ContextMindState（completed_intents, filled_slots, none_calls, turn_count）| 上下文决策时的输入 |
| **Action（动作）** | ContextAction（哪些 API 签名，prior_dataflow 策略）| 被评测的上下文工程选择 |
| **Reward（奖励）** | 对话是否成功完成（+1/-1）| 上下文工程决策的质量信号 |

**Contrastive IRL 评测（最重要的贡献）**：

DT-MDP-CE 指出，通过对比成功轨迹（τ+）和失败轨迹（τ-），可以学习上下文质量的代理奖励函数：

```
reward_score(trajectory) ∝ similarity_to_success_patterns - similarity_to_failure_patterns

在 ContextMind 中：
- τ+ = "人工校验" 标签的对话（chat_test_*.json 中已有）
- τ- = NONE() 调用密集的对话、未完成对话
```

这个对比奖励分数可以作为**上下文工程策略的质量代理指标**，无需人工逐一标注每个上下文选择的好坏。

**Policy Improvement（策略改进）评测**：

```
policy_quality = E[reward | policy_π] - E[reward | policy_baseline]

baseline = 当前硬编码的上下文构建规则
policy_π = 改进的上下文工程策略（如引入 top_k_intents、格式优化等）

正值 → 策略改进有效
负值 → 改进方向错误
```

---

### 2.7 Context Cartography：操作效果量化框架

**论文**：`context_cartography_analysis.md`（arXiv:2603.20578）

#### 七个制图操作符的效果评测

Context Cartography 提出的七个操作符（Reconnaissance、Selection、Simplification、Aggregation、Projection、Displacement、Layering）每个都有可量化的评测维度：

| 操作符 | ContextMind 对应实现 | 评测指标 | 测量方式 |
|--------|---------------------|---------|---------|
| **Reconnaissance** | `_score_intents_for_query()`（top_k 意图选择）| 意图召回率 @k = 实际被调用 API 在 top_k 中的比例 | 召回率计算 |
| **Selection** | `_format_prior_dataflow()`（变量过滤）| 变量引用准确率 = 被 AP 实际使用的变量 / 注入的变量总数 | 使用率统计 |
| **Simplification** | `compact=True` 模式 | Token 减少率（compact vs full）× 准确率保持率 | A/B 对比 |
| **Aggregation** | 当前缺失，待实现 | 聚合后 Token 减少率 + pass@1 保持率 | 实现后评测 |
| **Projection** | `_build_api_signatures()` | 函数签名的可读性评分（人工评测）+ AP 调用准确率 | 对比评测 |
| **Displacement** | `_is_stub_only_result()` 过滤 | Displacement 精确率（被移除的变量中真正不需要的比例）| 人工标注验证 |
| **Layering** | System/User msg 分离 | prior_dataflow 位置对 AP 注意力的影响 | 位置实验 |

#### "Lost in the Middle"评测

Context Cartography 强调的 Lost in the Middle 效应对 ContextMind 尤其重要，因为 `prior_dataflow` 当前放在 User message 末尾——这是 LLM 最容易忽视的位置。

**量化 Lost in the Middle 的评测方法**：

```
定义实验：
- 变量组 A：prior_dataflow 放在 User message 开头
- 变量组 B：prior_dataflow 放在 User message 末尾（当前）

评测指标：
- variable_reference_accuracy: AP 正确引用 prior_dataflow 变量的准确率
- position_sensitivity_score = accuracy(A) - accuracy(B)

若 position_sensitivity_score > 0.05，则证明当前位置不优，需要调整 Layering。
```

#### 三区域可见度量化

```
information_visibility_score = Σ(relevance_weight_i × position_weight_i) / Σ(relevance_weight_i)

其中 position_weight 基于"Primacy/Recency effect"：
- 开头位置权重：1.0
- 中间位置权重：0.6
- 结尾位置权重：0.8
（基于 Lost in the Middle 论文的发现）

ContextMind 应最大化每个重要信息组件的 information_visibility_score。
```

---

### 2.8 DDC：知识完整性与收敛评测框架

**论文**：`ddc_analysis.md`（arXiv:2603.14057）

#### KB 完整性评测

DDC 提供了知识库"完整性"的评测框架，解决了一个关键问题：**怎么知道 KB 什么时候"足够好"了？**

| DDC 评测指标 | 含义 | ContextMind 计算方式 |
|------------|------|---------------------|
| **KB Coverage Rate（KB 覆盖率）** | 已知失败模式被 KB 覆盖的比例 | 有对应 API 的失败意图 / 总失败意图 |
| **Convergence Rate（收敛率）** | 每个 DDC 循环新增实体数的下降趋势 | 相邻循环的 new_entities 差值 |
| **KB Density（KB 密度）** | 每个意图的平均槽位数（过稀疏 → 信息不足）| Σ(slots_per_intent) / total_intents |
| **Failure Reduction Rate（失败率下降率）** | KB 更新后 NONE() 率的改善 | (NONE_rate_before - NONE_rate_after) / NONE_rate_before |

#### 收敛判断的量化标准

DDC 的"收敛假设"（约 20-30 个循环收敛）对 ContextMind 可以具体化为：

```
收敛条件：
1. 连续 3 个 DDC 循环的新增意图数 < 2
2. NONE() 调用率的变化 < 1%（相邻两次 KB 更新之间）
3. 覆盖率 > 85%（已知失败意图的 85% 有对应 KB 覆盖）

当上述 3 个条件同时满足，判定 KB 达到"工作点"（working point）。
```

#### 失败-知识关联度评测

```
failure_knowledge_coupling = 
    correlation(NONE_rate_by_intent, kb_coverage_by_intent)

含义：NONE() 调用率高的意图，是否恰好也是 KB 覆盖少的意图？
- 高相关性（> 0.6）：说明知识缺失是主要失败原因，上下文工程应重点补充 KB
- 低相关性（< 0.3）：说明失败主要来自模型能力，改进上下文效果有限
```

---

### 2.9 ALARA：最小权限与上下文精简评测

**论文**：`alara_agents_analysis.md`（arXiv:2603.20380）

#### 最小权限原则的量化评测

ALARA 原则（最低合理可行）要求 Agent 获取的信息量应在合理可行的范围内降到最低。其评测核心是：**每单位上下文信息带来了多少任务成功价值？**

| ALARA 评测指标 | 定义 | 计算公式 |
|--------------|------|---------|
| **Context Efficiency（上下文效率）** | 每 token 带来的任务成功率 | pass@1 / tokens_per_turn |
| **Privilege Excess（权限过剩度）** | 注入但从未被使用的 API 签名比例 | unused_api_sigs / total_api_sigs |
| **Field Excess（字段过剩度）** | prior_dataflow 中从未被引用的字段比例 | unused_fields / total_fields |
| **Temporal Excess（时间过剩度）** | 超过必要历史窗口的对话轮次占比 | extra_turns / total_history_turns |

#### 最小权限测试（Ablation Study）

ALARA 的最重要评测方法是**消融实验**：逐步移除上下文组件，观察准确率的变化：

```
实验设计（移除实验）：
1. Full Context：全量 API 签名 + 全量 prior_dataflow + 全量历史
2. Minus Completed APIs：移除已调用 API 的签名
3. Minus Stale Dataflow：移除 3 轮前的 prior_dataflow
4. Minus Old History：只保留最近 5 轮对话历史

评测结果表（示例）：
| 配置 | pass@1 | tokens/turn | efficiency |
|------|--------|------------|------------|
| Full | 0.72   | 1850       | 0.00039    |
| -Completed APIs | 0.71 | 1520 | 0.00047  |
| -Stale Dataflow | 0.72 | 1650 | 0.00044  |
| -Old History | 0.70 | 1380 | 0.00051   |

ALARA 建议采用 efficiency 最高且 pass@1 损失 < 2% 的配置。
```

---

### 2.10 Practitioner Methodology：结构化质量审计框架

**论文**：`practitioner_methodology_analysis.md`（arXiv:2604.04258）

#### 五角色审计（Auditor 阶段评测）

Practitioner Methodology 的 Auditor 阶段提供了一套上下文质量的结构化检查清单，每个检查项都可以转化为定量评测：

| 角色 | 审计问题 | 量化评测指标 |
|------|---------|------------|
| **Authority** | Agent 的身份和职责是否明确？ | authority_completeness = required_authority_elements / present_authority_elements |
| **Exemplar** | 是否提供了 few-shot 示例？ | exemplar_coverage = intents_with_examples / total_intents |
| **Constraint** | 是否覆盖了所有关键行为约束？ | constraint_coverage = covered_constraints / required_constraints |
| **Rubric** | 是否定义了响应质量标准？ | rubric_present = 1 if rubric_defined else 0 |
| **Metadata** | 会话元数据是否完整且最新？ | metadata_freshness = 1 - (stale_metadata_fields / total_metadata_fields) |

#### 信息论指标

Practitioner Methodology 引入了信息论量化方法，对 ContextMind 的上下文设计有直接指导价值：

```
mutual_information(context, task) = I(C; T)
    ≈ Σ P(c, t) × log(P(c,t) / P(c)P(t))
    （可用 TF-IDF 相关性近似）

redundancy(context) = Σ_i H(c_i | c_{-i})
    ≈ 重复 n-gram 比例（计算简单版本）

information_density = I(C; T) / |C|
    ≈ task_relevant_tokens / total_tokens

最优上下文 = 高 I(C;T) + 低 redundancy + 高 density
```

#### Constraint 失效模式评测（FMEA 视角）

基于可靠性工程 FMEA（失效模式与影响分析）方法，可以对 ContextMind 的上下文失效模式进行系统评测：

| 失效模式 | 检测方式 | 严重程度 |
|---------|---------|---------|
| Authority 缺失 → AP 行为不可预测 | system message 长度 < 阈值 | 高 |
| Constraint 模糊 → AP 越权调用 | illegal_api_call_rate 上升 | 高 |
| Exemplar 不足 → 输出格式不稳定 | response_format_error_rate | 中 |
| Rubric 缺失 → 质量不一致 | response_quality_variance | 中 |
| Metadata 过时 → 基于错误状态决策 | stale_dataflow_usage_rate | 高 |

---

### 2.11 HYVE：视图质量与信息抽象评测

**论文**：`hyve_analysis.md`（arXiv:2604.05400）

#### 混合视图的质量评测

HYVE 框架将上下文中的数据组织为三种视图（聚合视图、关联视图、语义视图）。对每种视图的质量评测方法：

| 视图类型 | 质量评测标准 | 量化指标 |
|---------|------------|---------|
| **Aggregation View（聚合视图）** | 是否正确聚合了关键统计信息，是否有信息损失 | 聚合保真度 = 基于聚合的任务成功率 / 基于原始数据的任务成功率 |
| **Semantic View（语义视图）** | 自然语言摘要是否包含了所有关键事实 | 事实覆盖率 = 摘要覆盖的关键事实 / 原始数据关键事实总数 |
| **Relational View（关联视图）** | 实体关系是否正确表示 | 关系准确率 = 正确关联的实体对 / 总关联实体对 |

#### Token 压缩率评测（HYVE 核心贡献）

```
compression_ratio = original_tokens / view_tokens
quality_retention = task_success_with_view / task_success_with_original

view_efficiency = quality_retention × compression_ratio

目标：view_efficiency > 1.0（即压缩后质量保持率 × 压缩比 > 1）
当 view_efficiency > 1.5，认为视图转换高度有效。
```

对 ContextMind 的具体应用：评测 prior_dataflow 中 API 返回值的"语义视图化"效果（原始 JSON vs 自然语言摘要的对比）。

---

### 2.12 Meta CE：上下文工程策略的进化效果评测

**论文**：`meta_ce_skill_evolution_analysis.md`（arXiv:2601.21557）

#### Skill 参数空间的性能景观

Meta CE 的进化框架需要评测**不同上下文工程配置（Skill）的性能**，这直接提供了一套超参数评测方法：

| Skill 参数 | 评测范围 | 最优化目标 |
|-----------|---------|----------|
| `intent_selection_k` (0, 3, 5, 10, 全量) | AP API 调用准确率 | 最大化准确率同时最小化 token |
| `dataflow_format` (custom/yaml/toon/semantic) | 变量引用准确率 | 最大化引用准确率 |
| `history_max_turns` (3, 5, 10, 全量) | pass@1 vs token 数 | Pareto 最优边界 |
| `dataflow_staleness_threshold` (2, 3, 5, 7) | token 减少率 vs 信息损失率 | 最大化 token 减少同时限制信息损失 < 5% |
| `api_sig_format` (text/yaml/json) | 函数签名的 AP 理解准确率 | 最大化参数提取准确率 |

#### 适应度函数（Fitness Function）设计

Meta CE 的进化搜索需要一个评测适应度的函数，对 ContextMind 可以设计如下：

```python
def context_engineering_fitness(config: SkillConfig, test_dialogues) -> float:
    """
    ContextMind 上下文工程配置的适应度函数。
    综合多个指标，权重可调。
    """
    results = run_evaluation(config, test_dialogues)
    
    fitness = (
        0.40 * results.pass_at_1 +              # 任务成功率（最重要）
        0.25 * (1 - results.none_rate) +          # NONE() 减少（直接质量信号）
        0.20 * results.economy_score +             # token 效率
        0.10 * results.slot_fill_rate +            # 槽位填充完整性
        0.05 * results.format_consistency          # 格式一致性
    )
    return fitness
```

---

## 三、综合评测指标体系（从研究论文提炼）

### 3.1 第一层：任务成功指标（Outcome Metrics）

**来源**：τ-Knowledge、ACE、DT-MDP-CE

| 指标 | 定义 | 计算公式 | 数据来源 |
|------|------|---------|---------|
| **pass@1** | 首次对话成功率 | 成功对话数 / 总对话数 | benchmark 场景运行 |
| **pass@k** | k 次试验成功率 | 1 - (1-pass@1)^k | 统计推断 |
| **task_completion_rate** | 完整任务流程完成率 | 完成全部意图的对话 / 总对话 | 对话轨迹分析 |
| **none_rate** | NONE() 调用率 | NONE() 调用次数 / 总 AP 决策次数 | AP 调用日志 |
| **illegal_action_rate** | 非法 API 调用率 | 调用未注册/越权 API 次数 / 总调用次数 | EE 错误日志 |
| **recovery_rate** | NONE() 后的恢复成功率 | NONE() 后最终成功 / NONE() 总次数 | 对话轨迹分析 |

### 3.2 第二层：上下文过程指标（Context Process Metrics）

**来源**：Vishnyakova 五准则、Context Cartography、Practitioner Methodology

| 指标 | 定义 | 计算公式 | 数据来源 |
|------|------|---------|---------|
| **context_relevance** | 上下文相关性 | 有效 API 签名数 / 注入的总 API 签名数 | AP prompt 分析 |
| **context_sufficiency** | 上下文充分性 | 1 - (知识不足导致的 NONE() / 总 NONE()) | NONE() 原因分析 |
| **variable_reference_accuracy** | 变量引用准确率 | AP 正确引用 prior_dataflow 变量的次数 / 尝试引用次数 | AP 调用日志 |
| **slot_fill_completeness** | 槽位填充完整率 | 已填充必填槽位 / 总必填槽位 | 对话状态追踪 |
| **intent_recall_at_k** | 意图召回率@k | 被调用的 API 在 top_k 意图中的比例 | intent_context 分析 |
| **information_visibility** | 信息可见度分数 | Σ(重要性 × 位置权重) / Σ 重要性 | 基于 Primacy/Recency |
| **context_isolation** | 上下文隔离度 | 1 - (AP∩DM context tokens / AP∪DM context tokens) | prompt 内容分析 |
| **provenance_coverage** | 溯源标注覆盖率 | 有来源标注的数据项 / 总数据项 | prior_dataflow 统计 |

### 3.3 第三层：效率指标（Efficiency Metrics）

**来源**：Tokalator、ALARA、Context Cartography、Terminal Coding Agents

| 指标 | 定义 | 计算公式 | 数据来源 |
|------|------|---------|---------|
| **tokens_per_turn** | 每轮对话总 token 消耗 | system_tokens + user_tokens | token 计数 |
| **token_efficiency** | Token 效率 | pass@1 / (tokens_per_turn / budget) | 综合计算 |
| **cache_efficiency** | 缓存效率 | stable_prefix_tokens / total_tokens | prompt 结构分析 |
| **context_quality_score** | Tokalator 质量分 | 0.4×Relevance + 0.4×Density - 0.2×Redundancy | prompt 分析 |
| **signal_to_noise_ratio** | 信噪比 | relevant_tokens / (total_tokens - relevant_tokens) | token 分析 |
| **privilege_excess** | 权限过剩度 | unused_api_sigs / total_api_sigs | AP 调用追踪 |
| **dataflow_utilization** | 变量利用率 | used_variables / total_variables_injected | prior_dataflow 追踪 |
| **compression_efficiency** | 压缩效率 | quality_retention × compression_ratio | 对比实验 |

### 3.4 第四层：知识库质量指标（Knowledge Base Metrics）

**来源**：DDC、ACE、τ-Knowledge、Generative Ontology

| 指标 | 定义 | 计算公式 | 数据来源 |
|------|------|---------|---------|
| **kb_coverage_rate** | KB 覆盖率 | 有对应 API 的用户意图类型 / 总意图类型 | KB 分析 + 失败日志 |
| **kb_convergence_rate** | KB 收敛率 | 新增意图数的每轮下降趋势 | DDC 循环记录 |
| **failure_knowledge_gap** | 失败-知识缺口率 | NONE() 率高但 KB 覆盖少的意图比例 | 交叉分析 |
| **kb_density** | KB 密度 | 平均每意图的槽位数 | schema.json 分析 |
| **exemplar_coverage** | 示例覆盖率 | 有示例的意图 / 总意图 | KB 检查 |
| **intent_redundancy** | 意图冗余度 | 语义相似意图对数 / 总意图数 | embedding 相似度 |

### 3.5 第五层：安全与合规指标（Safety & Compliance Metrics）

**来源**：ALARA、AutoHarness、τ-Knowledge、Practitioner Methodology

| 指标 | 定义 | 计算公式 | 数据来源 |
|------|------|---------|---------|
| **policy_compliance_rate** | 业务合规率 | 符合前置条件的 API 调用 / 总 API 调用 | 调用顺序验证 |
| **constraint_violation_rate** | 约束违反率 | 违反 Constraint 规则的响应 / 总响应 | 响应内容检查 |
| **sensitive_field_exposure** | 敏感字段暴露率 | 不应注入但被注入的敏感字段数 / 总字段数 | prior_dataflow 检查 |
| **privilege_minimality** | 最小权限遵守率 | 仅访问必要 API 的调用 / 总调用 | ALARA 规则检查 |
| **authority_completeness** | 权威定义完整率 | 包含必要元素的 system message / 总 system message | prompt 审计 |

---

## 四、评测框架架构建议

### 4.1 评测层次模型

基于上述分析，ContextMind 的评测应分为四个层次：

```
L4：系统级评测（System-Level Evaluation）
    - pass@1, pass@k, task_completion_rate
    - 对应：τ-Knowledge 的端到端框架
    - 频率：每次 KB 更新或策略变更后

L3：上下文质量评测（Context Quality Evaluation）
    - Vishnyakova 五准则分数
    - Tokalator Quality Score
    - Context Cartography 操作符效果
    - 频率：每次 prompt 结构变更后

L2：组件级评测（Component-Level Evaluation）
    - 各上下文组件的 token 效率
    - 变量引用准确率
    - 意图召回率@k
    - 频率：日常监控

L1：知识库评测（KB-Level Evaluation）
    - kb_coverage_rate, kb_convergence_rate
    - failure_knowledge_gap
    - 频率：每次 KB 构建/更新后
```

### 4.2 核心评测流程

```
Step 1：准备 Golden Trajectories（参考 τ-Knowledge 的方法）
  - 为每个场景手工标注"标准对话轨迹"（golden_trajectory）
  - 包含：正确的 API 调用序列、正确的槽位填充、合规的对话流程

Step 2：运行系统（baseline）
  - 使用当前 ContextMind 配置运行 golden_trajectory 中的场景
  - 记录所有指标（pass@1、NONE() 率、token 数等）

Step 3：分析上下文质量
  - 对每个对话的 AP prompt 计算 Tokalator Quality Score
  - 检查 Vishnyakova 五准则合规情况
  - 统计 Context Cartography 各操作符的效果

Step 4：定位问题
  - 高 NONE() 率 + 低 kb_coverage → DDC 改进 KB
  - 高 token 数 + 低 cache_efficiency → Tokalator/ALARA 优化
  - 低 variable_reference_accuracy → Context Cartography Layering 调整
  - 低 context_relevance → ALARA 最小权限 API 暴露

Step 5：A/B 评测改进
  - 基于 McMillan 实证框架进行格式 A/B 测试
  - 基于 Meta CE 的适应度函数评测配置变更
  - 计算 context_quality_improvement_index（ACE 指标）
```

### 4.3 指标优先级与实施路线

#### 第一优先级（立即可实施，无需代码大改）

| 指标 | 实施难度 | 需要数据 | 预期价值 |
|------|---------|---------|---------|
| **none_rate** | ★☆☆ | AP 调用日志（已有）| 直接反映上下文充分性 |
| **tokens_per_turn** | ★☆☆ | prompt 文本（已有）| 量化效率基线 |
| **privilege_excess** | ★☆☆ | AP 调用 + API 列表（已有）| ALARA 第一步 |
| **kb_coverage_rate** | ★☆☆ | KB + 失败日志（需要 FailureCollector）| DDC 完整性评测 |
| **context_relevance** | ★☆☆ | AP prompt + 调用记录（已有）| Vishnyakova 相关性 |

#### 第二优先级（需要 Golden Trajectory 准备）

| 指标 | 实施难度 | 需要数据 | 预期价值 |
|------|---------|---------|---------|
| **pass@1** | ★★☆ | Golden trajectories（需标注）| 最核心的系统级指标 |
| **slot_fill_completeness** | ★★☆ | Golden trajectories | 任务完整性 |
| **policy_compliance_rate** | ★★☆ | 业务规则 + Golden trajectories | 合规性保证 |
| **variable_reference_accuracy** | ★★☆ | AP 调用 + 变量注入记录 | Cartography Selection 效果 |

#### 第三优先级（需要实验框架建设）

| 指标 | 实施难度 | 需要数据 | 预期价值 |
|------|---------|---------|---------|
| **context_quality_score (Tokalator)** | ★★★ | 需要实现 Quality Model | 综合质量量化 |
| **failure_knowledge_gap** | ★★★ | FailureCollector + KB 分析 | DDC 知识缺口定位 |
| **information_visibility** | ★★★ | 需要 Primacy/Recency 实验 | Cartography Layering 优化 |
| **contrastive_reward_score** | ★★★★ | 成功/失败轨迹对 | DT-MDP-CE 策略评测 |

---

## 五、关键发现与核心洞察

### 5.1 最重要的评测空白

通过对所有论文的系统分析，ContextMind 当前最关键的评测空白是：

**1. 缺少端到端任务成功率（pass@1）的基准测量**

τ-Knowledge 告警：金融客服场景最好模型的 pass@1 仅 25.5%。ContextMind 没有任何等效的端到端评测，无法知道当前系统的基线表现，也无法量化任何改进的实际价值。这是最需要优先建立的评测指标。

**2. 缺少上下文组件的效用归因**

Context Cartography 和 ALARA 都指出：大量注入的上下文信息中，只有一小部分真正被使用。ContextMind 没有追踪"哪些上下文信息被 AP 实际使用"的能力，导致无法判断哪些组件在贡献价值，哪些在消耗 token。

**3. 缺少 NONE() 的根因分类**

当 AP 调用 NONE() 时，ContextMind 没有区分是"上下文不足"还是"模型能力不足"导致的。Vishnyakova 的 Sufficiency 准则指出，这个区分对于评估上下文工程的改进上限至关重要。

**4. 缺少 KB 完整性的量化**

DDC 分析指出，ContextMind 没有评测 KB 是否"足够"覆盖了真实用户意图的能力。KB 构建了多少个意图不等于 KB 覆盖了多少比例的用户需求。

### 5.2 研究论文提供的最可操作的评测方案

以下三个方案可以最快落地，无需大量代码改动：

**方案 A：NONE() 率监控仪表盘（基于 ACE + DDC）**

立即可实施：在 `execution_engine.py` 中记录 NONE() 调用事件，输出仪表盘：
- 总 NONE() 率
- 按意图分类的 NONE() 率
- NONE() 后恢复成功率
- NONE() 率随时间的变化趋势（评估上下文改进效果）

**方案 B：Token 效率分解报告（基于 Tokalator + ALARA）**

立即可实施：在 `prompts.py` 的 prompt 构建后，统计各组件 token 数：
- AP system message：authority + API signatures + guidelines
- AP user message：history + intent context + prior_dataflow
- 各组件的 privilege_excess（未被使用的比例）
- 整体 cache_efficiency

**方案 C：格式 A/B 测试框架（基于 McMillan）**

快速实施：为 prior_dataflow 实现 3 种格式（current/yaml/semantic），对相同场景运行对比测试，输出：
- 各格式的变量引用准确率
- 各格式的 token 数
- 格式切换对 pass@1 的影响

### 5.3 论文评测方法的适用性矩阵

| 论文 | 评测方法 | 适用阶段 | 实施优先级 | 核心贡献 |
|-----|---------|---------|----------|---------|
| τ-Knowledge | pass@1/k 端到端框架 | 系统级 | 🥇 最高 | 建立量化基线的唯一方法 |
| Vishnyakova | 五准则评分体系 | 上下文级 | 🥇 最高 | 上下文质量的多维度框架 |
| Tokalator | Quality Score | 上下文级 | 🥈 高 | 可操作的量化公式 |
| Context Cartography | 操作符效果量化 | 组件级 | 🥈 高 | 定位"哪个组件有问题" |
| ALARA | 消融实验 / 权限过剩度 | 组件级 | 🥈 高 | 最直接的效率优化方向 |
| DDC | 收敛评测 / KB 覆盖率 | KB 级 | 🥈 高 | KB 完整性量化 |
| McMillan | 格式 A/B 测试 | 上下文级 | 🥉 中 | 格式选择的数据支持 |
| ACE | Playbook 改进曲线 | 系统级 | 🥉 中 | 自改进效果的长期跟踪 |
| DT-MDP-CE | 对比奖励函数 | 策略级 | 🥉 中 | 策略选择的理论基础 |
| Practitioner Methodology | Auditor 审计 | 上下文级 | 🥉 中 | 结构化质量检查 |
| HYVE | 视图效率评测 | 组件级 | 🔵 低 | 数据视图质量（先改进再评测）|
| Meta CE | 适应度函数 | 策略级 | 🔵 低 | 超参数优化的评测支持 |
| AutoHarness | 非法动作率 | 安全级 | 🔵 低 | 约束合规性验证 |

---

## 六、结论

### 核心结论

1. **现有研究论文提供了完整的评测体系框架**，可以分层应用到 ContextMind 的不同评测需求。从端到端任务成功率（τ-Knowledge）到上下文质量量化（Tokalator, Vishnyakova）再到 KB 完整性（DDC），形成了完整的评测层次。

2. **ContextMind 最紧迫的评测需求是建立"端到端基线"**，即通过标注 golden trajectories 并运行 pass@1 评测，建立当前系统的量化性能基线。没有这个基线，任何上下文工程改进都无法被量化验证。

3. **上下文质量的评测核心是"有用信息密度"**，Tokalator 的 Quality Score（Q = α·Relevance + β·Density - γ·Redundancy）是目前最可操作的单一综合评测指标，结合 ALARA 的权限过剩度和 Context Cartography 的变量利用率，可以构建完整的效率评测体系。

4. **NONE() 调用率是免费的上下文质量信号**，它已经存在于 ContextMind 的 execution_engine 中，但没有被系统收集和利用。建立 NONE() 监控仪表盘是成本最低、价值最高的第一步。

5. **KB 评测与上下文运行时评测必须联动**，DDC 的失败-知识关联分析和 ACE 的 NONE() 改善曲线，都要求将 KB 质量指标与运行时失败率指标进行交叉分析。孤立评测任何一方都不完整。

### 最小可行评测集（MVP Metrics）

以下 5 个指标构成 ContextMind 的最小可行评测集，可以在 1-2 周内建立：

```
1. none_rate（AP 层）= NONE() 次数 / 总 AP 决策次数
2. tokens_per_turn（效率层）= system_tokens + user_tokens（每轮）
3. privilege_excess（ALARA 层）= unused_api_sigs / total_api_sigs
4. context_relevance（Vishnyakova 层）= 有效 API 签名 / 注入 API 签名总数
5. kb_coverage_rate（DDC 层）= 有 API 覆盖的失败意图类型 / 总失败意图类型
```

这 5 个指标不需要 golden trajectories，可以从现有日志和代码中直接计算，是建立评测体系的最低起点。在此基础上，再逐步建立 pass@1 等需要更多准备工作的高层指标。

---

*文档生成于 2026-04-14。基于 docs/research/ 中所有 16 篇论文分析文档的综合提炼。*
