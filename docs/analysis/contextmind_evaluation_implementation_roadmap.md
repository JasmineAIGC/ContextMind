# ContextMind 评测实施路径

> **文档目的**：综合 `contextmind_evaluation_framework_analysis.md`（评测指标体系）与 `contextmind_dataset_strategy_analysis.md`（数据集策略）两份分析文档，给出**在评测这个任务上，我的具体实施路径是什么、每一步对应的工作是什么**。
>
> **分析日期**：2026-04-14

---

## 总览：四阶段实施路径

```
阶段 0（第 1 周）：激活免费评测信号
  └── 在现有代码中插入日志，零数据集成本，立即获得 5 个基础指标

阶段 1（第 2-4 周）：建立 AP 调用评测基线
  └── 集成 SGD 数据集，完成 intent_accuracy / slot_fill_completeness 首次计算

阶段 2（第 1-2 月）：建立端到端评测能力（pass@1）
  └── 构建 Golden Trajectory，打通 pass@1 计算链路

阶段 3（持续）：评测体系运营
  └── 回归测试、DDC 循环跟踪、数据集更新
```

---

## 阶段 0：激活免费评测信号（第 1 周）

### 目标

不引入任何新数据集，只在现有代码路径上添加日志采集，立即启用 5 个最小可行评测指标（MVP Metrics）。

### 5 个目标指标

| 指标 | 含义 | 数据来源 |
|------|------|---------|
| `none_rate` | AP 调用 NONE() 的频率，直接反映上下文充分性 | AP 调用日志 |
| `tokens_per_turn` | 每轮对话消耗的 token 总数，量化成本基线 | prompt 构建日志 |
| `privilege_excess` | 注入但从未被 AP 调用的 API 签名比例 | AP 调用 + API 列表对比 |
| `context_relevance` | 实际被调用的 API 占注入 API 总数的比例 | AP prompt + 调用记录 |
| `kb_coverage_rate` | NONE() 失败中有 KB 覆盖的意图类型比例 | KB + NONE() 日志交叉 |

### 具体工作

**工作 0.1：在 `execution_engine.py` 中记录 NONE() 调用事件**

记录以下字段：
- 调用时间戳
- 当前对话 ID
- 当前轮次的用户输入
- 当前 `intent_context` 中提供的 API 列表
- 对应场景（schema_name）

输出：按意图分类的 `none_rate` 仪表盘，以及 NONE() 后的恢复成功率（`recovery_rate`）。

**工作 0.2：在 `prompts.py` 的 prompt 构建处添加 token 统计**

在每次构建 AP System Message 和 AP User Message 之后，统计：
- `system_tokens`：authority + API 签名 + guidelines 的 token 数
- `user_tokens`：对话历史 + intent context + prior_dataflow 的 token 数
- `total_tokens`：每轮总消耗

输出：`tokens_per_turn` 的实时监控曲线，以及各组件 token 占比分解。

**工作 0.3：在 `tracker.py` 中记录 API 调用追踪**

对每次 AP 决策，记录：
- 调用的 API 名称
- 该 API 是否在本轮的 `intent_context` 中存在
- `prior_dataflow` 中注入的变量列表，以及 AP 实际引用的变量名

输出：
- `privilege_excess` = 未被调用的 API 签名数 / 注入 API 签名总数
- `context_relevance` = 被调用 API 数 / 注入 API 总数
- `variable_reference_accuracy` = AP 正确引用的变量数 / 注入的变量总数

**工作 0.4：构建 KB 覆盖率交叉分析**

将 NONE() 调用日志（工作 0.1 产出）与当前 KB 中的意图列表做交叉比对：

```
kb_coverage_rate = 有对应 KB 意图的 NONE() 失败类型 / NONE() 失败类型总数
```

若一个 NONE() 调用的用户意图在 KB 中有覆盖，说明是 AP 推理问题；若没有覆盖，说明是 KB 缺口。

**交付物**

- `benchmark/monitoring/none_rate_dashboard.py`：NONE() 监控仪表盘
- `benchmark/monitoring/token_stats_reporter.py`：token 效率报告
- `benchmark/monitoring/api_call_tracker.py`：API 调用追踪器
- 第一份 ContextMind 评测快照（JSON 或 Markdown 格式，记录上述 5 个指标的初始基线值）

---

## 阶段 1：建立 AP 调用评测基线（第 2-4 周）

### 目标

集成 SGD（Schema-Guided Dialogue）数据集，建立 ContextMind 首个公开、可复现的 AP 层评测基线：`intent_accuracy`、`slot_fill_completeness`、`none_rate`（SGD 基准下）。

### 为什么是 SGD

SGD 是 PyTOD 的官方数据集，是目前公开数据集中**唯一同时具备 API 调用序列标注**的数据集：
- 22,825 条对话，26 个服务领域
- 每轮记录了 `service_call`（调用了哪个意图）、`slot 参数值`、`API 返回状态`
- 这直接对应 ContextMind AP 的行为，使得 AP 层指标的精确计算成为可能

TransferTOD 和 RiSAWOZ 只有 DST 标注（槽位填充结果），没有 API 调用标注，无法支撑 AP 评测。

### 具体工作

**工作 1.1：完成 SGD 格式适配器**

SGD 的 API 调用格式与 ContextMind 的 PyTOD 格式存在差异，需要编写格式转换器：

```
benchmark/adapters/sgd_adapter.py
  - 将 SGD 的 service_call（{"service": ..., "slot": ...}）
    转换为 ContextMind 的调用格式（intent_name + slot_dict）
  - 将 SGD 的 26 个服务 Schema 转换为 ContextMind 的 schema.json 格式
  - 生成对应的 *_pytod_apis.py 桩函数（用于执行 SGD 场景）
```

**工作 1.2：编写 SGD 评测 Runner**

新建 `benchmark/runners/run_pytod_sgd.py`，功能：
1. 读取 SGD 测试集对话
2. 为每条对话构建 ContextMind 的 AP 上下文（schema + prior_dataflow + 对话历史）
3. 调用 AP，获取 AP 的 API 调用决策
4. 与 SGD 的 ground truth API 调用对比
5. 统计并输出 `intent_accuracy`、`slot_fill_completeness`、`none_rate`

**工作 1.3：首次运行并建立 SGD 基线报告**

在 SGD 的 5 个核心领域（建议选与业务最相近的：Restaurants、Hotels、Flights、Banking、Phone）上运行评测：
- 记录当前 ContextMind 的 `intent_accuracy`（目标：> 0.6 为可用水平）
- 记录 `slot_fill_completeness`（目标：> 0.7）
- 记录各领域的 `none_rate`
- 这些数字是 ContextMind 第一个可量化比较的评测基线

**工作 1.4：构建第一批 Golden Trajectory（基于 SGD）**

从 SGD 中挑选 200 条对话，转换为 ContextMind 的 Golden Trajectory 格式（见下方数据结构定义），用于后续 pass@1 的预热计算。此批 Golden Trajectory 覆盖英文场景，成本接近零（数据格式转换）。

Golden Trajectory 数据结构：

```json
{
  "trajectory_id": "sgd_restaurant_001",
  "scenario_type": "book_restaurant",
  "schema_name": "restaurant_service",
  "difficulty": "easy",
  "dialogue": [
    {
      "turn_id": 1,
      "role": "user",
      "text": "...",
      "ground_truth": {
        "intent": "find_restaurant",
        "slots": {"cuisine": "Italian"},
        "ap_expected": "find_restaurant(cuisine='Italian')"
      }
    }
  ],
  "task_definition": {
    "required_intents": ["find_restaurant", "book_table"],
    "policy_constraints": ["book_table 必须在 find_restaurant 成功后调用"]
  },
  "ground_truth_outcome": {
    "task_completed": true,
    "completion_turn": 6
  }
}
```

**工作 1.5：建立 pass@1 计算框架（ContextMindEvaluator）**

新建 `benchmark/evaluator/context_mind_evaluator.py`，实现：
- 读取 Golden Trajectory 文件
- 在每个 trajectory 上运行 ContextMind
- 判断任务是否完成（对比 `ground_truth_outcome`）
- 统计 `pass@1`（成功的 trajectory 数 / 总 trajectory 数）

**交付物**

- `benchmark/adapters/sgd_adapter.py`：SGD 格式转换器
- `benchmark/runners/run_pytod_sgd.py`：SGD 评测 Runner
- `resources/benchmark/golden_trajectories/v1.0_sgd_adapted/`：第一批 Golden Trajectory（200 条，英文）
- `benchmark/evaluator/context_mind_evaluator.py`：pass@1 计算框架
- SGD 基线评测报告（intent_accuracy / slot_fill_completeness / none_rate 的初始数字）

---

## 阶段 2：建立端到端评测能力（第 1-2 月）

### 目标

建立 ContextMind 的核心评测能力：**中文场景的 pass@1**。这需要构建中文 Golden Trajectory，并完成业务场景的专属评测数据集。

这是整个评测体系中投入最高、价值也最高的阶段。

### 具体工作

**工作 2.1：TransferTOD + LLM 辅助标注（中文 Golden Trajectory 第二批）**

从 TransferTOD 测试集中挑选 100 条代表性中文对话，用 LLM 辅助添加 API 调用标注：

Step 1 — 自动意图识别（LLM 完成）：
```
Prompt: 这是一段客服对话，请识别用户在每一轮的意图（从以下已知意图中选择）：
[已知意图列表：来自 ContextMind 当前 KB]

对话内容：{dialogue_text}

输出格式：[{turn_id: 1, intent: "查询余额", confidence: 0.9}, ...]
```

Step 2 — 槽位值自动提取（LLM 完成）：
```
Prompt: 对于已识别的意图，提取每个槽位的值：
意图：{intent_name}，所需槽位：{required_slots}，对话：{relevant_turns}
输出：{slot_name: slot_value, ...}
```

Step 3 — 任务完成自动判断（LLM 完成）：
```
Prompt: 根据对话结尾，判断用户任务是否成功完成？
输出：{completed: true/false, reason: "..."}
```

Step 4 — 人工审核（30% 抽样，约 15-20 小时工时）：
- 重点审核 confidence < 0.7 的标注
- 修正错误，反馈给提示词

产出：100 条中文 Golden Trajectory（`resources/benchmark/golden_trajectories/v1.1_transfertod_cn/`）

运行 `ContextMindEvaluator` 计算**中文场景 pass@1 基线**，这是 ContextMind 第一个中文端到端基准数字。

**工作 2.2：业务对话数据的 DDC 分析（无标注业务数据处理）**

对无标注的业务对话数据，运行"运行-失败-分析"循环：

```
① 将无标注业务对话喂给 KnowledgeBaseBuilder → 自动提取初始业务 KB
② 对典型用户输入运行 ContextMind，收集所有 NONE() 调用（工作 0.1 的日志）
③ 对 NONE() 调用按意图聚类（LLM 辅助）
④ 识别出 Top 20 高频未覆盖意图
⑤ 输出：业务场景的 kb_coverage_rate 热图
```

这一步无需标注，自动运行，产出：
- 业务意图分布热图（哪些意图最常被请求）
- KB 覆盖缺口清单（哪些意图 ContextMind 无法处理）
- 待补充的 Top 20 高频意图列表

**工作 2.3：补充 KB 缺口（DDC 补充循环）**

对工作 2.2 识别出的 Top 20 高频未覆盖意图：
- 人工确认：这些场景的正确 API 调用是什么？（约 10-15 人工小时）
- 补充到 KB 中（DDC 的"按需补充"原则）
- 重新运行，验证 NONE() 率是否下降
- 记录每个 DDC 循环的 `new_intent_count` 和 `none_rate_change`

收敛判断（参考 DDC 论文的收敛假设，约 20-30 个循环）：
- 连续 3 个循环新增意图数 < 2
- 相邻两次 KB 更新间 NONE() 率变化 < 1%
- `kb_coverage_rate` > 85%

**工作 2.4：构建业务场景 Golden Trajectory（第三批，最核心）**

从无标注业务数据中挑选 100-200 条"任务类型明确、对话完整"的典型对话，进行完整标注：

标注内容：
- 每轮的正确 API 调用（intent + slot values）
- 是否成功完成任务（二值标签）
- 业务合规规则（policy_constraints，如"必须先验证身份才能查询账户"）
- 违规情况标注（如有）

标注流程：LLM 辅助初始标注 + 人工审核（20% 抽样，节省约 70% 标注时间）

预计工时：80-120 小时（含 LLM 辅助）

产出：`resources/benchmark/golden_trajectories/v2.0_business_domain/`（100-200 条业务场景 Golden Trajectory）

**工作 2.5：计算业务场景 pass@1 与合规率**

用工作 2.4 的 Golden Trajectory，运行 `ContextMindEvaluator`，计算：
- **业务 pass@1**（最有商业价值的评测数字，直接反映产品能力）
- **policy_compliance_rate** = 符合 policy_constraints 的 API 调用 / 总 API 调用
- 各场景类型（简单单步、中等多步、复杂跨域）分别的 pass@1

**工作 2.6：运行 Vishnyakova 五准则评分**

基于上述 Golden Trajectory 评测结果，计算 ContextMind 的上下文质量五维度评分：

| 准则 | 计算方式 |
|------|---------|
| Relevance（相关性）| 有效 API 调用率（调用 API 在本轮 intent_context 中存在的比例）|
| Sufficiency（充分性）| 1 - (上下文不足导致的 NONE() / 总 NONE()) |
| Isolation（隔离性）| 1 - (AP 上下文 ∩ DM 上下文 / AP ∪ DM context token 数) |
| Economy（经济性）| pass@1 / (tokens_per_turn / 参考预算) |
| Provenance（溯源性）| 有来源标注的 prior_dataflow 数据项 / 总数据项 |

**交付物**

- `resources/benchmark/golden_trajectories/v1.1_transfertod_cn/`（100 条中文 GT）
- `resources/benchmark/golden_trajectories/v2.0_business_domain/`（100-200 条业务 GT）
- 业务场景 `pass@1` 基线报告（含 policy_compliance_rate）
- 业务 DDC 分析报告（KB 覆盖率热图 + Top 20 缺口清单）
- Vishnyakova 五准则评分报告
- 经过 DDC 补充的更新版业务 KB

---

## 阶段 3：评测体系运营（持续进行）

### 目标

将评测从一次性运行变为持续运营的机制，支撑 ContextMind 每次 KB 更新、Schema 更新、上下文工程策略变更后的回归验证。

### 具体工作

**工作 3.1：建立评测回归机制**

每次 KB 更新或 Schema 变更后，自动触发：
1. 用已建立的 Golden Trajectory（v1.0 + v1.1 + v2.0）重新运行 `ContextMindEvaluator`
2. 对比本次与上次的 `pass@1`，计算 `Δpass@1`
3. 若 `Δpass@1 < -0.02`（下降超过 2%），触发警报

**工作 3.2：DDC 循环的量化跟踪**

每个 DDC 循环记录以下指标，构建 KB 质量演进曲线：
- `new_intent_count`（本轮新增意图数）
- `none_rate_change`（本轮 NONE() 率变化）
- `kb_coverage_rate`（当前 KB 覆盖率）

当满足 DDC 收敛条件时，生成"KB 收敛报告"，标注 KB 到达工作点的时间节点。

**工作 3.3：定期更新 Golden Trajectory（防数据漂移）**

每季度对新的业务对话数据运行 LLM 分析：
- 检测是否出现新的意图类型（分布漂移）
- 若出现漂移，将新意图场景加入 Golden Trajectory（追加到 v2.x）
- 更新业务 `pass@1` 基线

**工作 3.4：A/B 评测驱动的上下文工程优化**

在评测体系建立后，按需运行以下对比实验：

| 实验方向 | 实验变量 | 评测指标 |
|---------|---------|---------|
| prior_dataflow 格式优化 | current / YAML / semantic | 变量引用准确率 + token 数 |
| 意图上下文 top-k 调整 | k=0/3/5/10/全量 | intent_recall@k + tokens |
| 对话历史窗口大小 | 3/5/10/全量轮次 | pass@1 + tokens_per_turn |
| prior_dataflow 位置调整 | User msg 开头 vs 结尾 | 变量引用准确率（Lost-in-the-Middle 测试）|

每个实验至少运行 100 次完整对话，使用已建立的 Golden Trajectory 作为评测基准，输出 `Δpass@1` 和 `Δtokens`。

**工作 3.5：τ-Banking 数据集调研（可选）**

调研 τ-Banking（arXiv:2603.04370，Sierra Research）的开源状态。如果开源，τ-Banking 提供：
- 完整的 API 调用序列 + 任务完成标签 + 合规约束
- 金融客服场景（与 ContextMind 主要应用高度重叠）
- 与论文报告的 pass@1 基线（25.5%）直接对标的能力

如果开源，集成 τ-Banking 可以替代部分 Golden Trajectory 构建工作，提供与学术界对标的基准数字。

---

## 实施路径总览表

| 阶段 | 时间 | 关键交付物 | 解锁的评测能力 |
|------|------|-----------|-------------|
| **阶段 0** | 第 1 周 | 日志监控模块（3 个文件）| none_rate / tokens_per_turn / privilege_excess / context_relevance / kb_coverage_rate |
| **阶段 1** | 第 2-4 周 | SGD 适配器 + Runner + 200 条英文 GT + ContextMindEvaluator | intent_accuracy / slot_fill_completeness / pass@1（英文） |
| **阶段 2a** | 第 5-6 周 | 100 条中文 GT（TransferTOD + LLM 辅助） | pass@1（中文基础场景）|
| **阶段 2b** | 第 7-8 周 | 业务 DDC 分析报告 + KB 补充 | kb_coverage_rate（业务） + NONE() 率下降 |
| **阶段 2c** | 第 2 月 | 100-200 条业务 GT（真实标注）+ 五准则评分 | pass@1（业务场景）+ policy_compliance_rate |
| **阶段 3** | 持续 | 回归机制 + A/B 框架 + GT 更新流程 | 每次变更后的 Δpass@1 追踪 |

---

## 关键决策点

### 1. 何时需要 pass@1（何时启动 Golden Trajectory 构建）

- 如果目标是"内部验证上下文工程改进效果"：阶段 0 的免费指标（none_rate + privilege_excess）已足够，在阶段 1 的 SGD Golden Trajectory 上计算 pass@1 即可
- 如果目标是"对外展示产品能力"或"与竞品对比"：必须构建业务场景 Golden Trajectory（工作 2.4），这是无法绕过的一次性投入

### 2. SGD 英文数据 vs 中文数据集的权衡

- SGD（英文）：唯一有 API 调用标注的公开数据集，是 AP 评测的起点，但不能代表中文业务场景
- TransferTOD + LLM 辅助（中文）：有 DST 标注，LLM 辅助添加 API 标注后可用于 pass@1，是过渡方案
- 业务 GT（中文，真实标注）：最有价值，但成本最高，是最终目标
- **结论**：三者互补，按优先级依次建立，不互相替代

### 3. 合成数据 vs 真实标注的使用边界

- 合成数据（LLM 生成的 Golden Trajectory）：成本低，覆盖度高，但存在 LLM 自我验证偏差——用于**快速原型验证和开发迭代**
- 真实标注数据（工作 2.4 的业务 GT）：成本高，但可信度高——用于**对外报告和正式基准**
- **结论**：先合成后真实，合成数据做内部迭代，真实标注数据做最终验证

---

## 附：各指标对应的数据集来源

| 指标 | 阶段 0（日志）| 阶段 1（SGD）| 阶段 2a（CN GT）| 阶段 2c（业务 GT）|
|------|:-----------:|:-----------:|:--------------:|:---------------:|
| `none_rate` | ✅ | ✅ | ✅ | ✅ |
| `tokens_per_turn` | ✅ | - | - | - |
| `privilege_excess` | ✅ | - | - | - |
| `context_relevance` | ✅ | ✅ | ✅ | ✅ |
| `kb_coverage_rate` | ✅ | ✅ | ✅ | ✅ |
| `intent_accuracy` | - | ✅ 最强 | ✅ | ✅ |
| `slot_fill_completeness` | - | ✅ 最强 | ✅ | ✅ |
| `pass@1` | - | ⚠️ 英文 | ⚠️ 中文基础 | ✅ 业务 |
| `policy_compliance_rate` | - | - | - | ✅ |
| `variable_reference_accuracy` | ✅ | ✅ | ✅ | ✅ |
| `cache_efficiency` | ✅ | - | - | - |

---

*文档生成于 2026-04-14。综合自 `contextmind_evaluation_framework_analysis.md` 与 `contextmind_dataset_strategy_analysis.md`。*
