# Demand-Driven Context (DDC) × ContextMind 集成分析

> **论文**：Raj Navakoti, Saideep Navakoti  
> *"Demand-Driven Context: A Methodology for Building Enterprise Knowledge Bases Through Agent Failure"*  
> arXiv:2603.14057 (March 2026)

---

## 一、论文核心思想

### 1.1 问题定位

企业 LLM Agent 的失败通常不是因为推理能力不足，而是因为缺少**企业特有知识**：

- 公司内部术语（jargon）
- 内部流程和系统依赖关系
- 制度性决策（"部落知识"，tribal knowledge）

传统两种方案各有缺陷：

| 方案 | 缺陷 |
|------|------|
| **自上而下（Top-down）**：预先人工编写所有知识 | 知识库臃肿、更新滞后、未经实战检验 |
| **自下而上（Bottom-up）**：Agent 自主学习 | 无法获取只存在于人脑中的隐性知识 |

### 1.2 DDC 方法论

DDC 借鉴**测试驱动开发（TDD）**思想，以**Agent 失败为主要学习信号**：

```
① 给 Agent 分配真实企业任务
        ↓
② 观察失败 → 定位缺失知识
        ↓
③ 人工补充最小必要知识（按需补充，不过度）
        ↓
④ 验证 Agent 能否成功
        ↓
⑤ 循环（每次只增加证明必要的知识）
```

**收敛假设**：对特定企业角色，约 **20～30 个 DDC 循环**即可覆盖大部分必要知识。

**案例**：零售订单履行（SRE 事件管理），9 个循环后得到 **46 个实体**的可复用知识库。

### 1.3 实体元模型（Entity Meta-Model）

DDC 引入结构化的实体元模型：

- **实体类型**：术语、操作流程、系统依赖、制度决策等
- **关联关系**：实体之间的依赖和引用链接
- **验证属性**：每个实体绑定其被触发的失败案例（可追溯）

---

## 二、与 ContextMind 现有架构对照

| DDC 概念 | ContextMind 现有对应 | 现状与差距 |
|---------|---------------------|-----------|
| **Agent 失败** | PyTOD AP 的 `NONE()` 调用、EE 的 fuzzy match WARNING 日志 | ✅ 失败信号已存在，但**未被收集和利用** |
| **缺失知识识别** | `_check_schema_vs_discovery()` 警告（意图数不匹配） | ⚠️ 只做静态检查，不追踪运行时失败 |
| **按需补充知识** | 无 | ❌ 完全没有"失败驱动的 KB 增量更新"机制 |
| **实体元模型** | `ServiceSchema`（意图/槽位 JSON 结构） | ⚠️ 有结构但无实体追溯链和失败关联 |
| **迭代循环** | `schema_builder` Phase 4（验证+修复循环） | ✅ **已有形式！** 但仅限离线代码生成，不覆盖运行时知识 |
| **知识库构建** | `KnowledgeBaseBuilder.build_dataset()` 用全部对话 | ⚠️ 当前用所有对话均匀处理，未按失败优先级筛选 |
| **收敛判断** | 无 | ❌ 无收敛指标，不知道 KB 什么时候"够用了" |

**核心洞察**：ContextMind 已经有失败信号（AP 的 `NONE()` 调用、EE 的 fuzzy match）和知识库构建管道（`KnowledgeBaseBuilder`），但两者**完全没有连接**。DDC 的价值正是提供了这个连接的方法论。

---

## 三、集成机会分析

### 机会 A：运行时失败日志收集 ⭐⭐ 高价值

**当前代码**（`contextmind/modes/pytod/execution_engine.py`）：

```python
# 已有：fuzzy match 时记录 WARNING
logger.warning(f"Fuzzy matched '{name}' → '{best}' (score={score:.2f})")

# 已有：NONE() 调用时静默返回
# 但这些信号没有被持久化
```

**DDC 启发的改进**：在 EE 层增加失败事件收集器：

```python
# 新增：contextmind/modes/pytod/failure_collector.py

@dataclass
class FailureEvent:
    session_id: str
    turn_idx: int
    failure_type: str          # "NONE_call" | "fuzzy_match" | "constraint_violation"
    attempted_name: str        # AP 尝试调用的函数名
    matched_name: Optional[str]  # fuzzy 匹配到的名称（如有）
    context_slots: dict        # 当时的槽位状态
    dialogue_context: str      # 对话片段（用于知识挖掘）

class FailureCollector:
    def record(self, event: FailureEvent) -> None: ...
    def save_session(self, path: str) -> None: ...  # 写 failure_log.jsonl
```

**改动范围**：`execution_engine.py` 约 15 行（注入 collector），新增 `failure_collector.py`。

---

### 机会 B：失败驱动的 KB 增量发现 ⭐⭐ 高价值

**问题**：`KnowledgeBaseBuilder.build_dataset()` 当前**均等对待所有对话**（不区分成功/失败）。DDC 指出：失败对话包含最多"缺失知识"信息。

**方案**：增加失败优先模式：

```python
# contextmind/knowledge/builder.py 新增参数
def build_dataset(
    self,
    dialogues: list,
    failure_logs: Optional[List[FailureEvent]] = None,  # DDC 新增
    failure_priority: float = 2.0,                      # 失败对话权重倍数
) -> None:
    """
    当 failure_logs 提供时：
    1. 将失败事件关联到对应的对话轮次
    2. 在 discoverer 中对失败轮次提高采样权重
    3. 在 discovery_raw.json 中标记 failure_triggered=True
    """
```

**具体逻辑**：

```
failure_log.jsonl（来自机会 A）
        ↓
failure_driven_discovery():
    对每个失败事件：
        提取 dialogue_context（±2 轮对话窗口）
        调用 discoverer.discover_from_text(context)
        标记发现的实体为 failure_triggered=True
        ↓
    合并到 schema.json（仅新实体，不覆盖已有）
```

**对应 DDC 流程**：这就是 DDC 的核心循环——失败 → 识别缺失知识 → 按需补充。

---

### 机会 C：KB 收敛度量 ⭐ 中等价值

**DDC 收敛假设**：当新 DDC 循环不再产生新实体时，KB 收敛。

**ContextMind 实现方案**：在 `KnowledgeBaseBuilder.save_dataset()` 中增加收敛报告：

```python
# 在 conversion_summary.json 中增加收敛指标
{
    "convergence": {
        "total_cycles": 5,
        "new_intents_per_cycle": [12, 7, 4, 2, 0],
        "converged": true,
        "coverage_estimate": 0.92   # 已知失败中有多少被新实体覆盖
    }
}
```

**意义**：让 KB 构建有明确的"完成"标准，避免无限制的人工投入。

---

### 机会 D：实体追溯链（Failure Provenance） ⭐ 中等价值

DDC 实体元模型的关键特性：**每个实体绑定触发它的失败案例**（可追溯性）。

**当前**：`discovery_raw.json` 已经存储 provenance 字符串（对话来源）。

**增强方向**：将 `FailureEvent` ID 写入实体的 provenance 字段：

```json
// 当前 discovery_raw.json 格式（已有 provenance）
{
  "intent": "query_account_balance",
  "provenance": "session_abc123, turn_5"
}

// DDC 增强后
{
  "intent": "query_account_balance",
  "provenance": "session_abc123, turn_5",
  "failure_triggered": true,
  "failure_event_id": "failure_20260401_003",
  "failure_type": "NONE_call",
  "times_triggered": 3
}
```

**改动**：`contextmind/knowledge/builder.py` save_dataset() 约 20 行。

---

## 四、精准架构映射

```
DDC 方法论                          ContextMind 对应层
─────────────────────────────────────────────────────────
实际企业任务（触发失败）      →   用户对话（触发 AP 推理）
Agent 失败观察               →   execution_engine.py NONE()/fuzzy WARNING
缺失知识识别                 →   failure_collector.py【新增，机会A】
按需知识补充循环             →   KnowledgeBaseBuilder.build_dataset()
                                 + failure_driven_discovery()【机会B】
实体元模型                   →   ServiceSchema（意图/槽位）+ provenance【机会D】
收敛判断                     →   conversion_summary.json 收敛指标【机会C】
人工监督                     →   现有人工校验（"人工校验" label）
```

---

## 五、综合评估

| 机会 | 目标 | 实现难度 | 改动范围 | 预期效果 | 优先级 |
|------|------|---------|---------|---------|-------|
| **A** 失败日志收集 | 连接运行时与 KB 构建 | ⭐ 低 | EE 15行 + 新文件 | 为B/C/D提供数据基础 | 🥇 P1 |
| **B** 失败驱动发现 | KB 按需增量更新 | ⭐⭐ 中 | builder.py 40行 | 减少无效 NONE() 调用 | 🥇 P1 |
| **C** 收敛度量 | KB 建设有明确终点 | ⭐ 低 | builder.py 20行 | 量化 KB 完整性 | 🥈 P2 |
| **D** 失败溯源 | 实体可追溯性 | ⭐ 低 | builder.py 20行 | 便于诊断和维护 | 🥈 P2 |

**总工作量**：约 2 周，零新外部依赖。

---

## 六、与 ContextMind 现有特性的协同

### 与 schema_builder Phase 4（修复循环）的协同

DDC 的大循环（跨 session 的知识迭代）与 schema_builder Phase 4 的小循环（单函数级别的代码修复）形成**双层循环结构**：

```
外循环（DDC，跨 session）：
  失败 → 识别缺失意图/槽位 → KnowledgeBaseBuilder 补充 → schema 更新
                                                              ↓
内循环（Phase 4，单 session）：
  生成函数代码 → 测试 → 修复代码 → 达到通过率阈值
```

这个双层结构比单独的任何一个循环都更完整——外循环补充 **what**（知识内容），内循环改善 **how**（代码实现）。

### 与 `_check_schema_vs_discovery()` 的协同

当前该函数在 schema 意图数 < KB 发现数时发出静态警告。结合机会 A，可以把这个检查从静态（仅在构建时检查）升级为**动态（运行时持续检查）**：

```python
# 每次有新的 failure_log，触发增量检查
if new_failures_from_log:
    new_intents = failure_driven_discovery(failures)
    _check_schema_vs_discovery(schema, discovery_with_new_intents)
```

---

## 七、不适合直接移植的部分

| DDC 组件 | 原因 | ContextMind 处理方式 |
|---------|------|---------------------|
| **人工知识补充会议** | DDC 依赖人工专家在每个循环后填写知识 | ContextMind 用 LLM discoverer 替代，减少人工 |
| **20-30 循环收敛** | DDC 的收敛数字针对全新企业 KB | ContextMind 已有基础 KB，增量循环数应更少 |
| **只针对单角色** | DDC 为特定企业角色构建专属 KB | ContextMind 的 KB 可以跨场景复用 |

---

## 八、结论

DDC 和 ContextMind 解决的是**同一个核心问题**的两面：DDC 解决"怎么知道 KB 需要什么"，ContextMind 解决"怎么把知识转化为对话能力"。

**最关键的贡献**：DDC 提供了一个连接"运行时失败"和"知识库演化"的闭环方法论。ContextMind 已经有两端的实现（EE 失败信号 + KnowledgeBaseBuilder），但中间的连接管道缺失。

**首要行动**：实现机会 A（失败日志收集）+ 机会 B（失败驱动发现），即可完成这个闭环，将 ContextMind 从"一次性 KB 构建"升级为"持续演化的知识系统"。
