# AutoHarness × ContextMind 集成分析

> **参考论文**：Xinghua Lou, Miguel Lázaro-Gredilla, Antoine Dedieu, Carter Wendelken, Wolfgang Lehrach, Kevin P. Murphy (Google DeepMind)  
> *"AutoHarness: Improving LLM Agents by Automatically Synthesizing a Code Harness"*  
> arXiv:2603.03329 (2026)

---

## 一、AutoHarness 核心算法解析

### 1.1 动机

LLM Agent 在结构化环境（游戏、自动化工作流）中的失败有两类：

- **策略失败**：选错了合法行动
- **约束失败**：执行了**非法行动**（违反环境规则）

Kaggle GameArena 实测数据：Gemini-2.5-Flash **78% 的输局来自非法动作**，而非策略失误。传统方案是人工编写 harness（守卫函数），但不可扩展。

### 1.2 核心算法

AutoHarness 包含两种模式：

**模式一：Action-Verifier（动作验证器）**

```
给定环境规则文档 → LLM 生成 is_legal_action(state, action) → bool
                       ↓
           在实际环境中执行并收集非法动作样本
                       ↓
           若仍有非法动作 → LLM 迭代修复代码
                       ↓
           收敛后：所有动作先经过 harness 过滤
```

**模式二：Policy-as-Code（策略编译为代码）**

```
LLM 的策略 → 蒸馏为纯 Python 决策函数 → 推理时无需 LLM 调用
```

**搜索机制**：使用 **Thompson Sampling 树搜索**探索候选 harness 实现，平均 **< 15 次迭代**收敛。

**关键结果**：

- 145 个 TextArena 游戏：**零非法动作**
- Gemini-2.5-Flash + harness > Gemini-2.5-Pro（无 harness）
- Policy-as-Code 代码智能体在 1-player 游戏中超越 GPT-5.2-High

---

## 二、AutoHarness 概念与 ContextMind 现有机制对照

| AutoHarness 概念 | ContextMind 现有对应 | 当前差距 |
|-----------------|---------------------|---------|
| **Harness（动作约束函数）** | `ExecutionEngine._call_registered()` + fuzzy match | EE 只做名称纠错，**不验证参数合法性、业务约束** |
| **is_legal_action(state, action)** | 无直接对应 | ContextMind 无槽位值合法性校验层 |
| **迭代修复循环** | `schema_builder` Phase 4（`validate_function` + `repair_function`，最多 3 轮）| **已有！** 但仅在离线代码生成阶段，不在运行时 |
| **测试用例驱动验证** | `TestCaseItem` + `validate_function()` via `exec()` | **已有！** 但覆盖率有限（每意图最多 5 个） |
| **Thompson Sampling 探索** | 无 | 当前修复是线性迭代，无树搜索 |
| **Policy-as-Code 蒸馏** | `schema_builder` 生成的 `*_pytod_apis.py` | 已有代码化策略，但未做决策蒸馏（只是 mock/stub API） |
| **环境反馈闭环** | 无在线反馈机制 | 当前所有验证在离线生成阶段，运行时无约束保障 |
| **非法动作率指标** | 无 | 无 AP 幻觉率量化追踪 |

**核心发现**：ContextMind 的 `schema_builder` Phase 4 已经实现了 AutoHarness 的**基本循环思想**（生成→测试→修复），但在以下三个方向存在根本性差距：

1. **深度**：AutoHarness 的 harness 约束的是**运行时动作合法性**；ContextMind 的验证约束的是**离线生成阶段代码正确性**
2. **搜索策略**：AutoHarness 用 Thompson Sampling 做树搜索；ContextMind 是线性重试（性价比低）
3. **测试覆盖**：AutoHarness 用真实环境执行反馈；ContextMind 用静态构造的 `TestCaseItem`（LLM 生成，可能有盲点）

---

## 三、集成机会分析（由浅入深）

### 机会 A：为 PyTOD EE 增加运行时 Harness 层 ⭐⭐ 最高价值

**问题**：当前 PyTOD AP 生成的程序被 EE 直接执行。AP 可能：

1. 调用函数时传入**值类型错误**的参数（如 `account_id="张三"` 而实际需要数字 ID）
2. 在**业务约束不满足**时仍调用 API（如未验证身份就查余额）
3. 重复调用同一 API（AP 循环）

**方案**：在 EE 的 `_call_registered()` 调用前插入 harness 校验层。

```python
# contextmind/modes/pytod/harness.py（新增）

class ActionHarness:
    """
    运行时动作合法性验证器。
    
    每个 API 函数可注册若干 HarnessRule，EE 在调用前执行所有规则。
    规则来源：
      1. 自动从 schema.json 的 required_slots 推断（类型规则）
      2. SchemaDataBuilder 生成阶段同步生成（业务约束规则，见机会 C）
    """
    
    def check(self, func_name: str, kwargs: dict, state: dict) -> HarnessResult:
        """返回 (is_legal: bool, reason: str)"""
        ...
```

**对应 EE 改动（约 30 行）**：

```python
# execution_engine.py _call_registered() 调用前
harness_result = self.harness.check(func_name, kwargs, self.var_values)
if not harness_result.is_legal:
    # 不执行 API，返回约束错误，让 DM 引导用户提供正确信息
    return {"status": "constraint_violation", "reason": harness_result.reason}
```

**价值**：这是 AutoHarness Action-Verifier 模式在对话 Agent 的直接移植，无需 LLM 调用，纯确定性守卫。

---

### 机会 B：Schema Builder Phase 4 → 多候选并行修复 ⭐⭐ 高价值

**问题**：当前 Phase 4 是线性迭代（Round 1 修复 → Round 2 修复…），每轮只有一个候选，无搜索。AutoHarness 的核心创新之一是**树搜索 + Thompson Sampling** 选出最优候选。

**当前代码的限制**（`contextmind/schema_builder/pytod/builder.py`）：

```python
# 当前线性修复
for iteration in range(1, max_iterations + 1):
    if validation.pass_rate >= pass_rate_threshold:
        break
    repaired_code = llm_generator.repair_function(...)  # 只生成 1 个候选
    new_validation = validate_function(...)
    if new_validation.pass_rate >= validation.pass_rate:
        func_code = repaired_code  # 接受唯一候选
```

**AutoHarness 启发的改进**：每轮修复生成 **N 个候选**（N=3～5），全部执行测试，选择通过率最高的。

```python
# 改进后的 Phase 4（概念）
for iteration in range(1, max_iterations + 1):
    if validation.pass_rate >= pass_rate_threshold:
        break
    
    # 并行生成 N 个候选（temperature sampling）
    candidates = [
        llm_generator.repair_function(..., temperature=0.7 + 0.1*i)
        for i in range(n_candidates)
    ]
    
    # 全部验证，选最优
    best_code, best_validation = max(
        ((c, validate_function(intent, c, test_cases, SHARED_HELPERS)) 
         for c in candidates if c is not None),
        key=lambda x: x[1].pass_rate,
        default=(func_code, validation),
    )
    
    if best_validation.pass_rate >= validation.pass_rate:
        func_code, validation = best_code, best_validation
```

**改动范围**：

- `contextmind/schema_builder/pytod/builder.py`：Phase 4 循环（约 40 行修改）
- `contextmind/schema_builder/pytod/generator.py`：`repair_function()` 增加 `temperature` 参数

**预期效果**：函数通过率从当前的线性修复（3轮×1候选=3次尝试）提升为并行搜索（3轮×3候选=最多9次尝试），理论上通过率上限显著提高。

---

### 机会 C：SchemaDataBuilder 同步生成 Harness 规则 ⭐ 中等价值

**问题**：当前 `SchemaDataBuilder` 只生成 API 函数代码（`*_pytod_apis.py`），不生成这些函数的**约束规则**。

**方案**：在 Phase 3/5 中，为每个意图额外生成一组 HarnessRule：

```json
// 新增：*_harness_rules.json

{
  "query_account_balance": {
    "preconditions": [
      {"slot": "account_id", "type": "str", "pattern": "^\\d{10,16}$"},
      {"required_before": "verify_identity"}
    ],
    "slot_constraints": {
      "amount": {"type": "float", "min": 0.01, "max": 500000}
    }
  }
}
```

这些规则由 LLM 根据 schema 描述生成，供 `ActionHarness`（机会 A）在运行时使用。

**意义**：把 AutoHarness 的"让 LLM 自己写约束代码"思想映射到 ContextMind 的离线生成阶段，让每个部署的 Agent 自带量身定制的运行时守卫。

---

### 机会 D：AP 程序合法性验证（对话版 is_legal_action） ⭐ 中等价值

**问题**：AP 生成的程序有时包含**语法正确但语义非法**的调用序列，例如：

- 在 `x1 = verify_identity(...)` 之前就调用 `x2 = query_balance(...)` （顺序错误）
- 把 x1 的字符串字段传给需要整数的参数

**方案**：在 EE 解析完程序文本、执行前，用轻量级规则检查调用序列合法性：

```python
# 新增：execution_engine.py
def _validate_program_sequence(
    self, 
    statements: List[ProgramStatement],
    schema: Optional[ServiceSchema],
) -> List[str]:
    """
    检查 AP 程序的调用顺序合法性。
    返回违规描述列表（空=全部合法）。
    
    规则来源：schema 的 intent 依赖关系（harness_rules.json 或 policy_fields）
    """
    ...
```

这是 AutoHarness `is_legal_action` 的对话域适配版：不是检查棋盘动作合法性，而是检查 **API 调用序列合法性**。

---

### 机会 E：Policy-as-Code 蒸馏 → 优化 `*_pytod_apis.py` 生成质量 ⭐ 长期价值

**AutoHarness 模式二**的思想：把 LLM 的决策策略编译为纯代码，运行时零 LLM 调用。

ContextMind 的 `*_pytod_apis.py` 已经是这个方向的雏形——但当前生成的函数都是 mock 实现（返回 `{"status": "success"}`），没有真实业务逻辑。

**长期集成方向**：

1. 在 Phase 3 中，让 LLM 基于 **schema + 对话数据** 生成带真实决策逻辑的函数（不只是 mock）
2. 用多候选搜索（机会 B）+ 测试用例筛选找到最好的实现
3. 最终实现：部分意图（如简单查询类）可以在 EE 执行时**完全不调用外部 API**，而是运行生成的决策代码

**与机会 B 关系**：机会 B 提升搜索质量，机会 E 提升代码深度——两者组合效果最佳。

---

## 四、综合评估矩阵

| 机会 | AutoHarness 对应思想 | ContextMind 目标 | 实现难度 | 外部依赖 | 预期效果 | 优先级 |
|------|---------------------|-----------------|---------|---------|---------|-------|
| **A** 运行时 Harness 层 | Action-Verifier 模式 | 减少 AP 非法调用 | ⭐⭐ | 无 | 运行时零非法 API 调用 | 🥇 P1 |
| **B** 多候选并行修复 | Thompson Sampling 搜索 | 提升 SchemaBuilder 生成质量 | ⭐⭐ | 无 | 函数通过率 +20~40% | 🥇 P1 |
| **C** Harness 规则生成 | LLM 自动写约束代码 | Schema 同步生成约束 | ⭐⭐⭐ | 无 | 运行时守卫有据可依 | 🥈 P2 |
| **D** 程序序列校验 | is_legal_action 对话版 | 拦截非法调用顺序 | ⭐⭐ | 无 | 减少 AP 顺序幻觉 | 🥈 P2 |
| **E** Policy-as-Code 蒸馏 | Policy-as-Code 模式 | API 函数真实化 | ⭐⭐⭐⭐ | 无 | 长期：部分意图无需外部 API | 🥉 P3 |

---

## 五、与 ContextMind 现有架构的精准映射

```
AutoHarness 框架                    ContextMind 对应层
────────────────────────────────────────────────────────
环境规则文档                    →   schema.json（意图/槽位定义）
is_legal_action(state, action)  →   ActionHarness.check()【新增，机会A】
LLM 生成 harness 代码           →   SchemaDataBuilder Phase 3（已有）
环境执行反馈（真实/非法）       →   validate_function() via exec()（已有）
迭代修复（当前：线性）          →   Phase 4 repair loop（已有，机会B优化）
Thompson Sampling 多候选        →   并行 repair + 选最优【改进，机会B】
Policy-as-Code                  →   *_pytod_apis.py（已有雏形，机会E深化）
```

**最重要的洞察**：ContextMind 的 `schema_builder` 已经**独立发现**并实现了 AutoHarness 的核心思想（生成→测试→修复循环）。AutoHarness 的贡献是把这个循环做得更**系统**（树搜索、Thompson Sampling）并延伸到**运行时**（不只是离线生成阶段）。ContextMind 可以在两个方向从 AutoHarness 获益：

1. **向左延伸**（运行时方向）：增加 ActionHarness 运行时守卫（机会 A、D）
2. **向内优化**（离线生成方向）：把线性修复升级为多候选搜索（机会 B）

---

## 六、推荐实施路径

### Phase 1（2 周，零新依赖）

- 实现机会 B（多候选并行修复）：修改 `contextmind/schema_builder/pytod/builder.py` Phase 4 + `contextmind/schema_builder/pytod/generator.py` 的 `repair_function()` 支持 `n_candidates` 参数
- 无需新文件，影响范围极小

### Phase 2（3 周）

- 实现机会 A（ActionHarness 运行时层）：新增 `contextmind/modes/pytod/harness.py`，EE 注入约 30 行
- 实现机会 D（程序序列校验）：EE 在执行前调用 `_validate_program_sequence()`

### Phase 3（4 周，可选）

- 实现机会 C（Harness 规则自动生成）：SchemaDataBuilder Phase 5 生成 `*_harness_rules.json`
- 实现机会 E（Policy-as-Code 深化）：Phase 3 生成含真实决策逻辑的函数

---

## 七、不适合移植的部分

| AutoHarness 组件 | 原因 | ContextMind 处理方式 |
|-----------------|------|---------------------|
| **TextArena 游戏环境** | ContextMind 是对话 Agent，不是游戏 Agent | 用 API 调用合法性替代棋盘动作合法性 |
| **真实环境执行反馈** | 对话场景无法像游戏一样在沙盒中无限试错 | 用 `validate_function()` exec 验证代替 |
| **完整 Thompson Sampling 树** | 增加了搜索复杂度，对话场景迭代次数已足够 | 用平行多候选（并行 3 次 LLM 调用）替代完整树搜索 |

---

## 八、结论

AutoHarness 和 ContextMind 在核心机制上存在**令人惊讶的高度相似性**（都是 生成→测试→修复 循环）。最具价值的集成是：

- **机会 B**（多候选搜索，直接提升 SchemaDataBuilder 生成质量，改动极小）
- **机会 A**（运行时 ActionHarness，从根本上解决 AP 非法调用问题）

两者合计约 3~4 周工作量，**零新外部依赖**。

AutoHarness 的最大启发不是某个具体算法，而是一个工程哲学：**"让 Agent 自己为自己的行为写守卫"**。ContextMind 的 schema_builder 已经走到了这条路的一半，AutoHarness 指明了另一半的方向——把约束从离线代码生成延伸到运行时执行保障。
