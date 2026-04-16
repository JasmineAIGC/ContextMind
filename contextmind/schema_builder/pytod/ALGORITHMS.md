# PyTOD 代码生成器算法说明

本文档详细介绍 ContextMind PyTOD 代码生成系统中四种生成策略（`loop`、`alpha`、`sstar`、`ctree`）的算法原理、流程设计和关键参数。

---

## 目录

1. [整体框架](#1-整体框架)
2. [Loop — 基础五阶段流水线](#2-loop--基础五阶段流水线)
3. [Alpha — ACIA 自适应迭代修复](#3-alpha--acia-自适应迭代修复)
4. [SStar — S* 并行采样与区分性选择](#4-sstar--s-并行采样与区分性选择)
5. [CTree — CodeTree UCB 引导树搜索](#5-ctree--codetree-ucb-引导树搜索)
6. [四种策略对比](#6-四种策略对比)

---

## 1. 整体框架

所有四种生成器共享同一套输入/输出协议，并复用公共模块：

### 1.1 公共数据模型

```
TestCaseItem
├── input_slots:     Dict[str, Any]   # 调用时传入的槽位值
├── expected_keys:   List[str]        # 返回字典中必须包含的键
├── expected_values: Dict[str, Any]   # 部分字段的预期计算值（场景3/5填写）
└── description:     str              # 用例描述

FuncValidation
├── intent_name: str
├── total:       int                  # 总用例数
├── passed:      int                  # 通过用例数
├── failures:    List[Dict]           # 失败详情（最多5条）
├── iterations:  int                  # 实际迭代轮次
├── error:       Optional[str]        # 编译级错误
└── pass_rate    → passed / total     # 通过率属性
```

### 1.2 验证逻辑（`validator.py`）

每条测试用例验证以下四点：
1. 函数调用无异常
2. 返回值为 `dict`
3. 返回值中 `status == "success"`
4. `expected_keys` 中所有键均存在于返回值中
5. `expected_values` 中指定字段的值与预期匹配（使用 `_values_match` 宽松比较）

### 1.3 生成流程总览

所有生成器均在同一个五阶段外壳中运行，生成器差异仅体现在 Phase 3（初始生成）和 Phase 4（迭代优化）：

```
Phase 1  解析 schema（提取意图、槽位定义）
Phase 2  LLM 生成测试用例（TestCaseItem × N）
Phase 3  LLM 初始函数体生成
Phase 4  验证 + 迭代修复（各生成器算法核心）
Phase 5  组装输出文件（.py + 可选 validation_report.json）
```

---

## 2. Loop — 基础五阶段流水线

**目录：** `loop/`  
**参数：** `--generator loop`（默认）  
**适用场景：** 一般场景，资源有限时的基准方案

### 2.1 算法原理

Loop 是最简单的生成策略，使用线性的"生成 → 验证 → 修复"循环：

```
初始代码  ──→  验证  ──→  [通过率 ≥ 阈值] ──→ 返回
               │
               │  [未达阈值]
               ↓
         LLM 修复（提供当前代码 + 失败用例信息）
               │
               ↓ [通过率提升或持平]
         更新最优代码
               │
               ↓
         下一轮  ────→ 最多 max_iterations 轮
```

### 2.2 关键设计：probe 推进机制

修复循环维护两个指针：

- **`best_code` / `best_validation`**：历史最优结果，仅在通过率≥上一轮时更新，用于最终输出。
- **`probe_code` / `probe_validation`**：始终推进到最新一次修复结果，无论是否有改善。每轮修复以 `probe_code` 和 `probe_validation.failures` 作为 LLM 输入。

此设计避免了"重复修复相同状态"的死循环：即使某轮修复没有提升通过率，下一轮 LLM 也会看到不同的代码状态和不同的失败用例，从而产生不同的修复结果。

### 2.3 流程伪代码

```python
func_code = llm.generate(intent, test_cases)          # Phase 3 初始生成
validation = validate(func_code, test_cases)           # 初始验证

probe_code, probe_validation = func_code, validation  # probe 初始化

for iteration in range(1, max_iterations + 1):
    if validation.pass_rate >= threshold:
        break

    repaired = llm.repair(
        current_code=probe_code,          # 始终用 probe，不是 best
        failures=probe_validation.failures,
    )
    new_val = validate(repaired, test_cases)

    probe_code, probe_validation = repaired, new_val   # probe 无条件前进

    if new_val.pass_rate >= validation.pass_rate:      # best 仅在改善时更新
        func_code, validation = repaired, new_val

return func_code, validation
```

### 2.4 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_iterations` | 3 | Phase 4 最大修复轮次 |
| `pass_rate_threshold` | 0.9 | 通过率阈值（达到即停止） |
| `max_test_cases_per_intent` | 5 | Phase 2 每意图最多测试用例数 |

---

## 3. Alpha — ACIA 自适应迭代修复

**目录：** `alpha/`  
**参数：** `--generator alpha`  
**灵感来源：** [AlphaCodium](https://arxiv.org/abs/2401.08500)（2024）  
**适用场景：** 需要较强鲁棒性、倾向于全面探索不同实现思路时

### 3.1 算法原理

ACIA（AlphaCodium-Inspired Adaptive repair）在 Loop 的基础上增加了三个关键机制：

1. **Phase R（反思）**：生成前先让 LLM 分析函数的业务语义，生成"反思 JSON"，作为生成函数体的先验知识。
2. **Phase A（失败分析）**：每轮修复前，先让 LLM 分析失败模式（而非直接修复），明确问题根因后再定向修复。
3. **收敛重启**：连续 `_NO_IMPROVE_THRESHOLD`（默认2）轮无提升时，完全抛弃当前代码，从头重新反思并生成，跳出局部最优。

### 3.2 完整流程

```
Phase R  反思（业务语义分析 → reflection JSON）
    ↓
Phase G  骨架约束生成（函数体初始版本）
    ↓
    验证
    ↓
┌─ [pass_rate ≥ threshold] ──────────────────────────────→ 返回
│
│  [未达阈值，循环开始]
│
│  ┌─ [连续 ≥ 2 轮无提升：收敛重启]
│  │    重新 reflect() → 重新 generate_body()
│  │    probe 重置为重启结果
│  │    no_improve_streak = 0  →  continue
│  │
│  │  [正常修复]
│  │  Phase A：失败模式分析（基于 probe_code）
│  │     ↓
│  │  Phase F：定向修复（基于 probe_code + 分析结果）
│  │     ↓
│  │  probe 无条件推进到修复结果
│  │  如果改善 → 更新 best；否则 no_improve_streak += 1
│  └──────────────────────────────────────────────────────
│
└──  返回 best_code, best_validation
```

### 3.3 probe 推进 + 收敛重启的交互

- **probe** 记录最新修复状态，确保每轮 LLM 看到不同的失败场景。
- **收敛重启**后，probe 同步重置为新生成的代码（而非旧的 `best_code`），确保后续修复从新起点出发。
- `best_code` 始终保留历史最优，作为最终输出。

### 3.4 流程伪代码

```python
reflection = reflect(intent)                          # Phase R
body = generate_body(intent, reflection)              # Phase G
validation = validate(body, test_cases)

best_code, best_val = body, validation
probe_code, probe_val = body, validation
no_improve_streak = 0

for iteration in range(max_iterations):
    if best_val.pass_rate >= threshold:
        break

    if no_improve_streak >= NO_IMPROVE_THRESHOLD:     # 收敛重启
        reflection = reflect(intent, hint="换一种思路")
        new_body = generate_body(intent, reflection)
        new_val = validate(new_body, test_cases)
        if new_val.pass_rate > best_val.pass_rate:
            best_code, best_val = new_body, new_val
        probe_code, probe_val = new_body, new_val     # probe 重置
        no_improve_streak = 0
        continue

    analysis = analyze_failures(probe_code, probe_val)    # Phase A
    repaired = repair_body(probe_code, probe_val, analysis)  # Phase F
    new_val = validate(repaired, test_cases)

    probe_code, probe_val = repaired, new_val         # probe 无条件前进
    if new_val.pass_rate > best_val.pass_rate:
        best_code, best_val = repaired, new_val
        no_improve_streak = 0
    else:
        no_improve_streak += 1

return best_code, best_val
```

### 3.5 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_iterations` | 10 | 最大修复轮次（跨 A+F 轮次） |
| `pass_rate_threshold` | 0.9 | 通过率阈值 |
| `_NO_IMPROVE_THRESHOLD` | 2 | 触发收敛重启的连续无改善轮数 |

---

## 4. SStar — S* 并行采样与区分性选择

**目录：** `sstar/`  
**参数：** `--generator sstar`  
**论文来源：** Dacheng Li et al., *"S\*: Test Time Scaling for Code Generation"*, [arXiv:2502.14382](https://arxiv.org/abs/2502.14382), 2025  
**适用场景：** 高质量要求场景，愿意消耗更多 LLM 调用以获得更优结果

### 4.1 算法核心思想

S* 的关键创新在于 **"区分性测试输入"（Discriminating Inputs）**：

> 当两个候选函数通过率相近、难以区分优劣时，让 LLM 生成一个"能区分这两个函数行为的输入"，实际执行后根据执行结果选择更合理的候选。

这避免了仅靠固定测试集通过率来选择候选函数的局限性（固定测试集可能无法覆盖两函数的差异点）。

### 4.2 完整四阶段流程

#### Phase P — 并行草稿生成

以 N 种不同"思维模式"并行生成 N 个候选实现（默认 N=3）：

| 模式 | 核心倾向 |
|------|----------|
| 思维模式 0 | 分析业务逻辑，关注语义正确性 |
| 思维模式 1 | 关注边界条件与错误处理 |
| 思维模式 2 | 关注性能与代码简洁性 |

不同思维模式通过 prompt 中的 `thinking_mode` 和 `thinking_mode_detail` 字段注入，引导 LLM 从不同角度生成实现。

#### Phase D — 执行追踪驱动修复（LDB 风格）

对每个草稿独立进行修复，修复时提供**实际执行追踪（execution traces）**而非仅错误信息：

```
for each draft:
    for round in range(k_per_draft):     # 默认 k=3
        traces = collect_execution_traces(draft, failing_cases)
        repaired = llm.repair(draft, traces)  # 提供实际执行输出
        probe 无条件推进到 repaired
        if improved: update best
```

执行追踪提供的信息包括：实际返回值、抛出的异常、中间状态等，比仅提供"期望值 vs 实际值"更利于 LLM 定位 bug。

#### Phase S — 区分性测试选择（锦标赛模式）

S* 核心阶段：

```
champion = 通过率最高的候选
for each challenger in remaining_candidates:
    disc_input = llm.generate_discriminating_input(champion, challenger)
    champion_output = execute(champion, disc_input)
    challenger_output = execute(challenger, disc_input)
    winner = llm.judge(champion, challenger, disc_input, 
                        champion_output, challenger_output)
    if winner == challenger:
        champion = challenger   # 冠军被挑战者击败，更换冠军
```

**判断依据**：LLM judge 综合考虑：
- 两个候选在区分性输入上的实际输出
- 哪个输出更符合函数的业务语义

#### Phase R — 最优候选精炼

对 Phase S 选出的最优候选，用剩余预算继续执行 Phase D 风格的修复（probe 推进机制同上）。

### 4.3 预算分配

所有阶段共享一个总迭代预算 `max_iterations`：

```
总预算 = max_iterations
Phase P 消耗 = len(candidates)        # 每个草稿生成算1轮
Phase D 消耗 = sum(各草稿实际修复轮数)
Phase S 消耗 = len(candidates) - 1   # 每对比赛消耗1轮
Phase R 消耗 = remaining             # 剩余全部预算
```

### 4.4 流程伪代码

```python
# Phase P
candidates = [generate(intent, mode=i) for i in range(N)]
candidates.sort(by=pass_rate, descending=True)
remaining = max_iterations - N

# Phase D
for draft in candidates:
    repaired, val = repair_with_traces(draft, max_rounds=k, remaining=remaining)
    remaining -= val.iterations
candidates.sort(by=pass_rate, descending=True)

# Phase S（锦标赛）
champion = candidates[0]
for challenger in candidates[1:]:
    disc_input = generate_discriminating_input(champion, challenger)
    winner = judge(champion, challenger, disc_input)
    if winner is challenger:
        champion = challenger
    remaining -= 1

# Phase R
if remaining > 0:
    champion = repair_with_traces(champion, max_rounds=remaining)

return champion
```

### 4.5 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `_n_drafts` | 3 | Phase P 生成草稿数 |
| `_k_per_draft` | 3 | Phase D 每草稿最大修复轮数 |
| `max_iterations` | 10 | 总迭代预算（跨所有阶段） |
| `pass_rate_threshold` | 0.9 | 通过率阈值 |

---

## 5. CTree — CodeTree UCB 引导树搜索

**目录：** `ctree/`  
**参数：** `--generator ctree`  
**论文来源：** *"CodeTree: Agent-guided Tree Search for Code Generation with Large Language Models"*, [arXiv:2411.04329](https://arxiv.org/abs/2411.04329), 2024/2025  
**适用场景：** 复杂函数生成，存在多个互不干扰的失败原因时效果最佳

### 5.1 算法核心思想

CodeTree 将代码修复问题建模为**树搜索问题**：

- **节点**：每个节点存储一个候选函数实现及其测试验证结果。
- **扩展**：针对父节点的每个失败测试用例，**独立**生成一个专用修复分支（子节点）。每条分支只解决一个失败用例，避免修复一个用例时破坏其他用例。
- **选择**：使用 **UCB（Upper Confidence Bound）** 算法在整棵树中选择下一个待扩展节点，平衡"利用"（通过率高的节点）和"探索"（访问次数少的节点）。

### 5.2 UCB 评分公式

```
UCB(node) = pass_rate(node) + C × sqrt( ln(parent_visits + 1) / (node_visits + 1) )
```

| 项 | 含义 |
|----|------|
| `pass_rate(node)` | 该节点的测试通过率（利用项，倾向于高通过率节点） |
| `C` | 探索系数（默认 `C = 1.4 ≈ √2`） |
| `parent_visits` | 父节点（或根节点）被选中扩展的次数 |
| `node_visits` | 该节点自身被选中扩展的次数 |
| 探索项 | 访问次数少的节点获得更高分，防止搜索集中在单一路径 |

这是 [UCT（UCB applied to Trees）](https://link.springer.com/chapter/10.1007/11871842_29) 算法在代码搜索场景的直接应用，与 AlphaGo 等博弈树搜索使用的核心公式相同。

### 5.3 完整流程

```
Phase G  根节点生成（初始候选函数）
    ↓
    验证（根节点 pass_rate）
    ↓
[pass_rate ≥ threshold] ─────────────────────────────→ 返回根节点

[循环：最多 max_iterations 轮扩展]
    │
    Phase S  UCB 选择 → 选出得分最高的叶节点
    │          跳过：已耗尽节点（exhausted=True）
    │          跳过：无失败用例的节点
    │
    Phase E  树扩展 → 针对最多 _max_children 个失败用例生成子节点
    │          每个子节点专注修复一个失败用例
    │          扩展失败（LLM返回None）→ 节点标记 exhausted=True
    │
    [任意子节点 pass_rate ≥ threshold] ─────────────→ 停止搜索，返回
    │
    └──  继续下一轮
    
返回整棵树中 pass_rate 最高的节点
```

### 5.4 树节点结构

```
_TreeNode
├── func_code:   str              # 候选函数完整代码
├── validation:  FuncValidation  # 测试结果
├── depth:       int              # 节点深度（根=0）
├── visits:      int              # 被 UCB 选中的次数
├── exhausted:   bool             # True = 扩展失败，不再被选中
├── parent:      _TreeNode | None
├── children:    List[_TreeNode]
└── target_case: Dict | None     # 导致此节点生成的目标失败用例
```

### 5.5 与 ACIA/S* 的本质区别

| 特性 | Loop / Alpha | S* | CodeTree |
|------|-------------|-----|---------|
| 修复结构 | 线性链 | 平铺并行 | 树形分支 |
| 单次修复目标 | 所有失败用例 | 所有失败用例 | **单个失败用例** |
| 分支间关系 | 无（单链） | 无（并行采样） | **树形，共享父节点代码** |
| 搜索策略 | 贪心（接受改善） | 最优候选选择 | **UCB 平衡探索/利用** |

### 5.6 树搜索示意图

```
              根节点（pass_rate=0.6）
             /             \
    失败用例A的修复        失败用例B的修复
    (pass_rate=0.8)       (pass_rate=0.7)
       /      \
  失败用例C   失败用例D
  (0.9)       (0.85)
```

UCB 会倾向于继续扩展高通过率的节点（`0.9` 的子节点），同时给访问少的分支适当的探索机会（`失败用例B`的子树还未充分扩展）。

### 5.7 exhausted 标记机制

当某节点的所有扩展尝试（`_expand_node`）均返回 `None`（LLM 调用失败或无法提取函数体）时，该节点被标记为 `exhausted=True`，UCB 选择器在后续轮次中永久跳过此节点，避免反复发送无效的相同 prompt。

### 5.8 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `_UCB_C` | 1.4 | UCB 探索系数（约等于 √2） |
| `_MAX_EXPAND_CHILDREN` | 2 | 每次扩展最多处理的失败用例数 |
| `max_iterations` | 10 | 最大扩展轮次（含根节点生成） |
| `pass_rate_threshold` | 0.9 | 通过率阈值 |

---

## 6. 四种策略对比

### 6.1 算法特性对比

| 特性 | Loop | Alpha（ACIA） | S* | CodeTree |
|------|------|----------|-----|---------|
| **迭代结构** | 线性循环 | 线性循环 + 重启 | 并行 + 选择 | 树形搜索 |
| **多样性机制** | probe 推进 | probe + 收敛重启 | 多思维模式 | 分支扩展 |
| **候选选择** | 接受改善 | 接受改善 | 区分性测试 | UCB 评分 |
| **修复粒度** | 全部失败 | 全部失败 | 全部失败 | 单个失败用例 |
| **LLM 调用数（典型）** | 低 | 中 | 高 | 中偏高 |
| **对复杂函数效果** | 一般 | 较好 | 好 | 最好 |

### 6.2 推荐使用场景

| 场景 | 推荐策略 |
|------|---------|
| 快速生成，对质量要求不高 | `loop` |
| 普通复杂度，需要较好鲁棒性 | `alpha` |
| 高质量要求，可接受更多 LLM 调用 | `sstar` |
| 函数逻辑复杂，存在多个独立失败点 | `ctree` |

### 6.3 共同的 probe 机制

`loop`、`alpha`、`sstar` 三种策略均在修复循环中使用"probe 推进"模式（`ctree` 通过树结构天然避免了重复问题）：

```
best_code       ←  只在改善时更新，用于最终输出
probe_code      ←  无条件推进，每轮修复的实际输入
```

这是修复循环能够持续产生多样性修复结果的关键：即使某轮修复未能提升通过率，下一轮 LLM 也会收到不同的代码状态和不同的失败用例，从而打破重复相同 prompt 的死循环。



各算法各自的关键点
Loop（基础）

关键：probe 无条件推进，防止重复修同一状态。仅此一点就比"纯重试"高出很多。
Alpha（ACIA）

关键1：先反思再生成——生成前让 LLM 分析函数业务语义（reflection JSON），避免生成偏离意图的代码。
关键2：先分析失败模式再修复——每次修复前多一步失败分析（Phase A），明确根因后再定向修复，而非盲目改代码。
关键3：收敛重启——连续2轮没改善就完全丢弃当前代码，换一种思路从头生成，跳出局部最优。
S*（SStar）

关键1：多思维模式并行——同时用3种不同角度（语义/边界/性能）生成3个候选，起点多样性远超单一生成。
关键2：执行追踪辅助修复——修复时提供实际运行轨迹（返回值、异常、中间状态），而不仅仅是"期望值 vs 实际值"，LLM 定位 bug 准确得多。
关键3：区分性测试选择最优候选——两个候选通过率相近时，让 LLM 专门生成一个"能区分这两个函数行为差异的输入"，实际执行后再判断哪个更正确，避免固定测试集的覆盖盲区。
CTree（CodeTree）

关键1：每次修复只针对单个失败用例——传统做法是把所有失败用例一起丢给 LLM，容易顾此失彼。CTree 针对每个失败用例独立生成一个修复分支，修好这个不破坏那个。
关键2：UCB 平衡探索与利用——用 UCB 公式选择下一个扩展节点，高通过率的路径优先扩展（利用），访问次数少的分支也能获得机会（探索），不会把所有 LLM 预算全押在一条路径上。
一句话总结
通过率提升的本质：从"盲目重试"变成"有据可依的定向修复"——测试用例驱动、失败信息精准、修复方向多样、不重复同一死局。


