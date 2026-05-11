# Context Cartography × ContextMind 集成分析

> **论文**：Zihua Wu, Georg Gartner  
> *"Context Cartography: Toward Structured Governance of Contextual Space in Large Language Model Systems"*  
> arXiv:2603.20578 (March 2026)

---

## 一、论文核心思想

### 1.1 问题：简单扩大 Context Window 不够

传统做法是"给 LLM 更多 token"，但产生三个根本问题：

| 问题 | 描述 |
|------|------|
| **Lost in the Middle** | 关键信息在长上下文中部被忽视 |
| **长距离关系退化** | 相距较远的信息之间的推理关系断裂 |
| **熵积累** | 无关信息越来越多，干扰关键推理 |

### 1.2 核心框架：三区域模型（Tripartite Zonal Model）

将 LLM 的上下文空间分为三个区域，类比地图上的"能见度区域"：

```
┌────────────────────────────────────┐
│         Black Fog（黑雾）           │  ← 模型完全未接触的信息
│                                    │
│  ┌──────────────────────────┐      │
│  │     Gray Fog（灰雾）      │      │  ← 已存储但未激活（长期记忆）
│  │                          │      │
│  │  ┌──────────────────┐    │      │
│  │  │  Visible Field   │    │      │  ← 当前活跃的推理区域
│  │  │  （可见区域）      │    │      │     (System + User prompt)
│  │  └──────────────────┘    │      │
│  └──────────────────────────┘      │
└────────────────────────────────────┘
```

### 1.3 七个制图操作符（Cartographic Operators）

管理信息在三个区域之间移动和变换的七种操作：

| 操作符 | 作用 | 方向 |
|--------|------|------|
| **Reconnaissance（侦察）** | 探测黑雾中的可用信息 | 黑→灰 |
| **Selection（选择）** | 从灰雾中挑选相关信息 | 灰→可见 |
| **Simplification（简化）** | 压缩可见区域的冗余信息 | 可见内部 |
| **Aggregation（聚合）** | 合并相关信息减少碎片 | 可见内部 |
| **Projection（投影）** | 将可见信息映射到特定格式 | 可见→输出 |
| **Displacement（位移）** | 将完成处理的信息移出可见区域 | 可见→灰/黑 |
| **Layering（分层）** | 按优先级组织可见区域内的信息 | 可见内部 |

---

## 二、ContextMind 已有的"制图操作"对照

**重要发现**：ContextMind 已经在不知不觉中实现了多个制图操作符！但它们是**零散的、非系统化的**。Context Cartography 提供了统一的理论框架来理解和优化这些现有机制。

### 完整对照表

| Context Cartography 操作符 | ContextMind 现有实现 | 质量评估 |
|---------------------------|---------------------|---------|
| **Reconnaissance（侦察）** | `KnowledgeBaseBuilder.build_dataset()` 发现意图 | ✅ 已实现，覆盖离线阶段 |
| **Selection（选择）** | `_format_prior_dataflow()` 筛选可引用变量；`_is_stub_only_result()` 过滤 stub | ✅ 已实现，但规则硬编码 |
| **Simplification（简化）** | `ExecutionEngine.to_prompt_text(compact=True)` 只显示函数名 | ⚠️ 部分实现，compact 模式粗粒度 |
| **Aggregation（聚合）** | 无 | ❌ 缺失：完成的意图没有被压缩摘要 |
| **Projection（投影）** | `_build_api_signatures()` 生成 AP 的函数签名描述 | ✅ 已实现 |
| **Displacement（位移）** | stub 结果被移出 prior_dataflow（但保留在 current_state）| ⚠️ 部分实现，位移规则单一 |
| **Layering（分层）** | System msg（API 签名）vs User msg（意图上下文）分离 | ⚠️ 两层，但 AP 和 DM 的分层逻辑不同步 |

**三区域与 ContextMind 的映射**：

```
Context Cartography 三区域          ContextMind 对应
──────────────────────────────────────────────────
Black Fog（黑雾）             →   KB 中未被检索到的意图/知识
Gray Fog（灰雾）              →   current_state（已执行但不活跃）
                                  + var_values 中的 stub 结果
Visible Field（可见区域）      →   active system prompt + 当前 user prompt
                                  + prior_dataflow（显式传给 AP 的上下文）
```

---

## 三、集成机会分析

### 机会 A：系统化 Aggregation（聚合已完成意图）⭐⭐ 高价值

**当前问题**：已成功完成的 API 调用结果（如 `x1 = verify_identity(...)` 成功后）会在后续每轮继续占用 prior_dataflow 的 token，即使不再需要引用。

**Context Cartography 的 Aggregation**：将多个零散已完成事实压缩为摘要。

**改进方案**（在 `contextmind/modes/pytod/tracker.py`）：

```python
# 新增 _aggregate_completed_intents()
def _aggregate_completed_intents(
    self,
    var_values: dict,
    current_turn: int,
    staleness_threshold: int = 3,  # 超过 3 轮未引用的视为"已完成"
) -> Tuple[dict, str]:
    """
    对 staleness_threshold 轮内未被新调用引用的 API 结果：
    1. 从 prior_dataflow 移除（Displacement）
    2. 生成简短摘要字符串（Aggregation）：
       "已完成：verify_identity（成功）、query_account_balance（余额=1234.56）"
    3. 摘要作为单行文本保留在 visible field 的末尾（节省 token）
    
    返回：(清理后的 var_values, 聚合摘要文本)
    """
```

**预期效果**：长对话（10+ 轮）的 AP prompt token 数减少 30-50%，缓解"entropy accumulation"问题。

---

### 机会 B：Displacement 规则系统化 ⭐⭐ 高价值

**现状**：`_is_stub_only_result()` 只处理一种 Displacement 场景（stub 占位符）。实际上有更多信息应该被位移出可见区域。

**建立统一的 Displacement 策略**（在 `tracker.py`）：

```python
# 新增：DisplacementPolicy
class DisplacementPolicy:
    """
    统一管理哪些信息应从 visible field 位移到 gray fog。
    对应 Context Cartography 的 Displacement 操作符。
    """
    
    RULES = [
        # 规则1：stub 占位符（已有）
        lambda val: _is_stub_only_result(val),
        
        # 规则2（新增）：已经被 say() 显式传递给 DM 的变量
        # → 信息已到达 DM，不需要继续在 AP 可见区域
        lambda val, var_name, say_names: var_name in say_names,
        
        # 规则3（新增）：超过 staleness_threshold 轮未被引用的结果
        lambda val, last_used_turn, current_turn: 
            current_turn - last_used_turn > 3,
    ]
    
    def should_displace(self, var_name, val, context) -> bool:
        return any(rule(val, ...) for rule in self.RULES)
```

**改动范围**：`tracker.py` 约 40 行，重构 `_format_prior_dataflow()` 中的过滤逻辑。

---

### 机会 C：分层 Prompt 架构（Layering）⭐⭐ 高价值

**Context Cartography 的 Layering**：按优先级和性质组织可见区域内的信息，高优先级信息放在 LLM 最"能看到"的位置（开头/结尾）。

**现状**：AP 的 prompt 结构（`prompts.py`）：

```
System: [API 签名] + [AP 行为规范]
User:   [对话历史] + [意图上下文] + [prior_dataflow]
```

**问题**：根据"Lost in the Middle"效应，`prior_dataflow`（最关键的 API 调用历史）被放在 User msg 末尾，实验表明这是 LLM 最容易忽视的位置。

**改进方案**（调整 `prompts.py` 的 Layering）：

```
Layer 1（System，最高优先级）：
  - API 函数签名（静态，已有）
  - 当前轮次最重要的约束提示（新增）

Layer 2（User 开头，高优先级）：
  - [关键约束] 本轮必须注意的业务约束（新增，基于当前意图）
  - prior_dataflow 关键结果（移到开头！）

Layer 3（User 中部）：
  - 对话历史（当前）

Layer 4（User 末尾）：
  - 完整意图上下文（当前）
  - 已聚合的历史摘要（Aggregation 结果）
```

**关键变化**：将 `prior_dataflow` 从 User msg 末尾**移到开头**，对应 Context Cartography 的 Layering 原则（重要信息放在 visible field 的显著位置）。

**改动范围**：`contextmind/modes/pytod/prompts.py` 约 30 行重排。

---

### 机会 D：Reconnaissance 操作符 — 意图上下文动态检索 ⭐ 中等价值

**Context Cartography 的 Reconnaissance**：在黑雾（未知信息）中探测可用资源，为后续 Selection 做准备。

**ContextMind 的现状**：`_build_intent_context()` 为每轮 AP 生成的意图上下文是**全量静态**的（所有注册的 API 意图描述都出现在 prompt 中）。

**改进**：在每轮生成 AP prompt 时，先做 Reconnaissance——预判当前对话状态可能需要哪些 API，只把相关意图放进 prompt：

```python
# contextmind/modes/pytod/tracker.py

def _reconnaissance_relevant_intents(
    self,
    dialogue_history: List[dict],
    all_intents: List[IntentDef],
    top_k: int = 5,
) -> List[IntentDef]:
    """
    基于当前对话历史，预判最可能被调用的 top_k 个意图。
    方法：
      1. 关键词匹配（快速，无 LLM）
      2. 必要时用 embedding 相似度
    
    将 API 意图数从全量（可能 20+）减少到 top_k（5 个），
    节省 System prompt token，减少 AP 幻觉空间。
    """
```

**注意**：当 schema 意图数 < 10 时意义不大。当意图数 > 15 时此优化显著。

---

### 机会 E：Simplification 操作符 — 对话历史压缩 ⭐ 中等价值

**现状**：AP/DM 的 prompt 中对话历史是**全量追加**（append-only），随对话长度线性增长。

**Context Cartography 的 Simplification**：压缩可见区域的冗余信息，保留语义本质。

**改进**：超过 N 轮的对话历史自动压缩：

```python
# contextmind/modes/pytod/prompts.py

def _simplify_dialogue_history(
    self,
    history: List[dict],
    keep_recent: int = 5,    # 保留最近 5 轮完整对话
    compress_older: bool = True,
) -> Tuple[str, str]:
    """
    返回 (recent_full, older_summary)：
    - recent_full：最近 keep_recent 轮的完整对话文本
    - older_summary：更早的对话的单句摘要（由上一轮 LLM 生成并缓存）
    
    Simplification 策略：不删除历史，而是将其压缩到摘要
    """
```

---

## 四、精准架构映射

```
Context Cartography 框架              ContextMind 现有 / 改进后
──────────────────────────────────────────────────────────────
三区域模型（黑/灰/可见）        →   KB / current_state / active_prompt
Reconnaissance                   →   _reconnaissance_relevant_intents()【D】
Selection                        →   _is_stub_only_result() + prior_dataflow 过滤
Simplification                   →   compact 模式 / 对话历史压缩【E】
Aggregation                      →   _aggregate_completed_intents()【A】
Projection                       →   _build_api_signatures()（已有）
Displacement                     →   DisplacementPolicy 统一管理【B】
Layering                         →   prior_dataflow 移到 User 开头【C】
```

---

## 五、综合评估

| 机会 | 操作符 | 目标 | 难度 | 预期 Token 节省 | 优先级 |
|------|--------|------|------|----------------|-------|
| **A** Aggregation | 聚合已完成意图 | 减少长对话 token | ⭐⭐ | 30-50% | 🥇 P1 |
| **B** Displacement | 统一位移策略 | 清理 gray fog 残留 | ⭐⭐ | 15-25% | 🥇 P1 |
| **C** Layering | 重排 Prompt 结构 | 改善"Lost in Middle" | ⭐ | 间接（准确率↑）| 🥇 P1 |
| **D** Reconnaissance | 动态意图选择 | 减少 API 签名噪音 | ⭐⭐ | 10-30%（意图多时）| 🥈 P2 |
| **E** Simplification | 对话历史压缩 | 减少历史膨胀 | ⭐⭐⭐ | 20-40% | 🥈 P2 |

**机会 A + B + C 无需新依赖，改动最小，收益最直接，建议首期实施。**

---

## 六、ContextMind 独有的洞察补充

### 6.1 AP 和 DM 的双可见区域

ContextMind 的独特之处是有**两个 LLM**（AP 和 DM），各有自己的 visible field。Context Cartography 框架天然支持这种多 Agent 场景：

```
AP 的 Visible Field：
  - API 函数签名（Projection 的结果）
  - prior_dataflow（API 调用历史，Displacement 管理）
  - 当前对话片段（Simplification 管理）

DM 的 Visible Field：
  - say() 传递过来的 API 结果（AP→DM 的跨 Agent Displacement）
  - 完整对话历史（DM 需要语用连贯性）
  - 业务上下文 scenario_context

两者之间的 say() 机制：
  = AP Visible Field → DM Visible Field 的 Displacement 操作
```

**当前 ContextMind 已正确地实现了这个双 Agent Displacement**（say() 把 AP 结果传给 DM，且 AP 的 business context 不经过 say()，直接在 DM 的对话历史中可见）。Context Cartography 理论为这个设计提供了形式化验证。

### 6.2 Gray Fog 的双重利用

`current_state`（已执行 API 结果）在 ContextMind 中是 Gray Fog：
- 对 AP 不可见（已从 prior_dataflow 过滤的 stub）
- 对 DM 可用（通过 say() 显式传递的部分）

这是合理的 Gray Fog 管理策略，但当前实现隐式分散在多个地方。机会 B 的 `DisplacementPolicy` 可以将这些规则显式化，提升可维护性。

---

## 七、不适合直接移植的部分

| Context Cartography 组件 | 原因 | ContextMind 处理方式 |
|--------------------------|------|---------------------|
| **完整的上下文地图可视化** | 论文提出但未有工程实现 | 可以在日志层面添加 debug 输出 |
| **跨多轮 Aggregation 的 LLM 摘要** | 增加 LLM 调用成本 | 用规则摘要（已执行意图列表）替代 |
| **形式化 operator 证明** | 学术级别，工程实现不需要 | 只需实现 operator 的语义 |

---

## 八、结论

Context Cartography 为 ContextMind 提供了一个**统一的理论透镜**，将现有的多个临时机制（stub 过滤、compact 模式、prior_dataflow、say()）纳入系统化框架。

**最重要的工程价值**：

1. **机会 A（Aggregation）**：解决长对话的 token 膨胀问题，这是 ContextMind 在生产环境中的主要性能瓶颈之一
2. **机会 C（Layering）**：解决"Lost in the Middle"问题，将 prior_dataflow 放到 LLM 最容易注意到的位置
3. **机会 B（Displacement 系统化）**：将现有零散的过滤逻辑统一化，提升可维护性

论文的核心贡献是让 ContextMind 的开发者有一个统一的语言来讨论"上下文管理"问题，而不是在代码中零散处理各种 edge case。
