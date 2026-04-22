# PyTOD AP 阶段 API 选择算法分析与优化

## 1. 背景与问题定义

PyTOD 三步流程中，**Action Parser (AP)** 是核心步骤：LLM 根据对话历史和可调用 API 列表，生成 Python-like 程序（含函数调用和槽位填充）。

当 `pytod_apis` 数量很多时（例如 20~100 个业务函数），把全部函数签名塞入 prompt 会带来多重问题：

| 问题 | 影响 |
|------|------|
| Token 消耗过大 | 每轮调用成本高，延迟上升 |
| LLM 选择困难 | 函数列表过长导致 AP 精度下降（"lost in the middle"现象） |
| KV-cache 失效 | 动态注入的长 API 列表阻止前缀缓存 |
| 噪声干扰 | 不相关的 API 可能被 LLM 错误调用 |

因此，每轮只把「最相关的 top-K 个 API」放入 AP prompt，是兼顾质量和效率的关键设计决策。

---

## 2. 现有实现分析

### 2.1 当前算法（`_score_intents_for_query`）

**核心思路：多信号 TF-IDF 评分**

```
score(intent, query) = Σ_t [ IDF(t) * field_weight(f) ]  ∀ t ∈ (query_tokens ∩ field_tokens_f)
```

五个信号：
1. **停用词过滤**：剔除中英文功能词，降低噪音
2. **标识符分解**：`query_balance` → `{query, balance}`，解决 snake_case API 名与自然语言的词汇鸿沟
3. **分字段加权**：函数名(×3.0) > 描述(×2.0) > 槽位名(×1.5)
4. **IDF 权重**：稀有词得分更高，常见词得分更低
5. **已调用惩罚**：已成功调用的 API 得分乘以 0.2

**查询构建**：取当前用户话语 + 最近 2 条历史用户话语拼接，扩大语义覆盖范围。

### 2.2 现有方案的局限性

#### 局限一：TF-IDF 的词频线性增长问题
TF-IDF 中词频的贡献是线性的（TF=n 时贡献 n 倍），但在我们的场景中 token 集合（Set）本身就将 TF 限制为 0/1，所以这个问题已部分规避。不过，BM25 在文档长度归一化方面更加精确。

#### 局限二：缺乏对话流依赖建模
当前评分完全基于词汇匹配，没有考虑**对话流中的 API 依赖关系**：
- 若 API_A 已被调用且其 `result_slots` 包含 API_B 的 `required_slots`，则 API_B 是高概率的下一个调用
- 例如：`verify_identity` 已调用后，`confirm_terms`（需要身份验证结果）应被优先展示

#### 局限三：缺乏槽位填充就绪信号
若用户当前话语中显式提及了某个 API 所需的槽位（如"我的借款金额是五千元" → `loan_amount`），该 API 应获得额外加权，但现有方案通过槽位名的 token 匹配只能间接捕获。

#### 局限四：文档长度归一化缺失
当两个 API 的描述长度差异很大时（一个 5 个 token，一个 30 个 token），IDF 加权无法自动归一化这种长度差异，可能导致描述更长的 API 得分系统性偏高。

---

## 3. 相关算法调研

### 3.1 词汇检索算法

#### TF-IDF（当前方案基础）
- 经典信息检索算法
- 词频 × 逆文档频率
- 问题：词频线性增长、无文档长度归一化

#### BM25（Okapi BM25）
- 概率检索框架下的词袋模型
- 关键改进：词频饱和（k1 参数）+ 文档长度归一化（b 参数）
- 公式：
  ```
  BM25(t,D) = IDF(t) × (tf × (k1+1)) / (tf + k1 × (1 - b + b × |D|/avgdl))
  ```
- 典型参数：k1=1.5, b=0.75
- 在信息检索基准上系统性优于 TF-IDF

#### BM25+ / BM25L
- BM25 的改进版，处理更长文档时效果更好
- 引入 δ 参数防止 TF 为零时得分不合理
- 对本场景（文档较短）提升有限

### 3.2 语义检索算法

#### Dense Retrieval（稠密检索）
- 使用预训练语言模型将 query 和 document 编码为向量
- 计算余弦相似度
- 代表模型：DPR、Sentence-BERT、text-embedding-3-small
- 优点：能处理语义同义词（"查余额" ↔ "query_balance"）
- 缺点：需要额外推理调用（延迟增加）、需要安装嵌入模型依赖

#### ColBERT（晚期交互）
- 将 token 级别向量做最大相似度聚合（MaxSim）
- 比 Dense 更精准，但推理成本更高

#### BM25 + 重排序（两阶段）
- 第一阶段：BM25 快速召回 top-N 候选
- 第二阶段：Cross-encoder LLM 对候选做精确重排序
- 对本场景开销过大（已有 AP 调用 LLM，再加重排序是 2 次 LLM 调用）

### 3.3 对话状态感知算法

#### 任务型对话中的 API 选择
在任务型对话系统（TOD）研究中，API/服务选择通常被建模为：
1. **Slot filling 完成度**：已填充槽位越多，API 越接近可执行
2. **API 依赖图**：某些 API 的输入依赖其他 API 的输出（DAG 结构）
3. **对话状态机**：基于当前状态转移概率选择最可能的下一步 API
4. **Intent 序列预测**：基于历史调用序列，用马尔可夫链或 LSTM 预测下一个 intent

#### Schema-guided API Dependency
PyTOD schema 中每个 intent 含 `result_slots`（输出字段），这为构建 API 依赖图提供了结构化信息：
- 若 intent_B 的 `required_slots` ⊆ 已调用 intent_A 的 `result_slots`，则 A→B 存在依赖边
- 已调用 A 后，B 的所需输入已就绪，应提升 B 的优先级

### 3.4 最优方案设计原则

结合本场景特点（实时对话、中小规模 API 集合、中英文混合、无外部嵌入模型依赖）：

**最优方案 = 增强 BM25 + 对话流依赖感知 + 槽位就绪信号的多信号融合**

理由：
1. BM25 是无外部依赖条件下最优的词汇检索算法（学术界和工业界广泛验证）
2. 依赖感知能捕获 TF-IDF 完全忽略的对话流信号（对于链式 API 调用尤为重要）
3. 槽位就绪信号利用了 schema 结构信息，是本领域专属的高质量信号
4. 无需额外 LLM 调用或嵌入模型，推理延迟不受影响

---

## 4. 优化方案设计

### 4.1 信号体系

| 信号 | 类型 | 说明 | 实现 |
|------|------|------|------|
| S1: BM25 词汇分 | 主信号 | 替代 TF-IDF，含长度归一化 | per-field BM25 + 字段权重 |
| S2: 依赖就绪加成 | 乘法因子 | 已调用 API 的输出可满足此 API 的输入 | result_slots ∩ required_slots |
| S3: 槽位提及加成 | 乘法因子 | 当前对话明确提及此 API 的必填槽位 | query_tokens ∩ required_slot_tokens |
| S4: 已调用惩罚 | 乘法因子 | 已成功调用的 API 降权（保留重试能力） | ×0.2 |

### 4.2 评分公式

```
score(intent, query) = BM25(intent, query) × dep_factor × readiness_factor × call_penalty
```

其中：
- `BM25(intent, query) = Σ_field [ w_field × BM25_field(intent, query) ]`
- `dep_factor = 2.0`（所有 required_slots 已就绪）| `1.3`（部分就绪）| `1.0`（未就绪）
- `readiness_factor = 1 + 0.5 × (query_tokens ∩ required_slot_tokens) / |required_slot_tokens|`
- `call_penalty = 0.2`（若已调用）| `1.0`（未调用）

### 4.3 BM25 参数选择

- `k1 = 1.5`：词频饱和系数，典型值范围 1.2~2.0
- `b = 0.75`：文档长度归一化强度，0 = 不归一化，1 = 完全归一化
- 由于 field_tokens 为 Set（TF 为 0/1），公式简化为：

```
tf_weight = (k1 + 1) / (k1 × (1 - b + b × |D| / avg_dl) + 1)
```

### 4.4 兼容性设计

- 函数签名兼容现有调用方（新增参数均带默认值）
- 在 `process_turn()` 中透传 `call_history`，无需修改外部接口
- 当 intents 数量 ≤ top_k 时直接返回全部（与原有行为一致）

---

## 5. 各方案对比

| 方案 | 精准性 | 依赖建模 | 延迟影响 | 实现复杂度 |
|------|--------|----------|----------|----------|
| 全量展示 API | - | 无 | 高（token 多） | 极低 |
| 简单词袋 | 低 | 无 | 无 | 低 |
| **现有 TF-IDF（v1）** | **中** | **无** | **无** | **中** |
| **增强 BM25+依赖（v2，本方案）** | **高** | **有** | **无** | **中** |
| Dense Retrieval | 高 | 无 | 中（推理延迟） | 高 |
| LLM 重排序 | 最高 | 可选 | 高（+1次LLM） | 高 |

---

## 6. 实现细节

### 6.1 核心函数改动

**文件**：`contextmind/modes/pytod/tracker.py`

**改动点**：
1. `_score_intents_for_query()` 内部替换为 BM25 + 三个乘法因子
2. 新增 `call_history: Optional[List[str]]` 参数（向后兼容，默认 None）
3. `process_turn()` 中构建有序调用历史并传入评分函数

### 6.2 BM25 实现要点

由于 field_tokens 使用 `Set[str]` 存储（非词频计数），TF 天然为 0 或 1，BM25 公式退化为：

```python
norm_factor = k1 * (1 - b + b * field_len / avg_field_len)
tf_weight = (k1 + 1) / (norm_factor + 1)  # TF=1 时
score += idf_val * tf_weight * field_weight
```

这与原 TF-IDF 方案的差异：原方案仅用 `idf_val * field_weight`（TF 隐式为 1，无长度归一化），新方案增加了 `tf_weight`（含 BM25 长度归一化因子）。

### 6.3 依赖就绪因子计算

```python
# 收集已调用 API 的输出字段
available_result_slots = set()
for called_name in already_called_names:
    called_intent = intent_map.get(called_name)
    if called_intent:
        available_result_slots.update(called_intent.result_slots)

# 计算每个候选 intent 的依赖就绪度
required = set(intent.required_slots)
if required:
    covered = required & available_result_slots
    if covered == required:     dep_factor = 2.0   # 全部就绪
    elif covered:               dep_factor = 1.3   # 部分就绪
    else:                       dep_factor = 1.0   # 无就绪
else:
    dep_factor = 1.0  # 无依赖约束
```

### 6.4 槽位就绪因子计算

```python
# 将 required_slots 标识符分解为 token
required_slot_tokens = set()
for slot in intent.required_slots:
    required_slot_tokens.update(_split_identifier(slot))

# 计算 query 对 required_slot_tokens 的覆盖比例
if required_slot_tokens:
    mentioned_count = len(query_tokens & required_slot_tokens)
    readiness_factor = 1.0 + 0.5 * mentioned_count / len(required_slot_tokens)
else:
    readiness_factor = 1.0
```

---

## 7. 预期效果

### 7.1 BM25 对 TF-IDF 的改善

| 场景 | TF-IDF 表现 | BM25 表现 |
|------|-------------|-----------|
| 短描述 vs 长描述 API | 长描述得分系统偏高 | 长度归一化后公平比较 |
| 高频词（如"用户"）命中 | 得分虚高 | IDF 降权 + TF 饱和抑制 |
| 稀有词精确命中 | 正确提升 | 正确提升（一致） |

### 7.2 依赖就绪加成的场景收益

典型对话流程示例（贷款服务）：
```
轮1: 用户 "我想查询账户信息"
  → verify_identity 被调用（result_slots 含 account_id）
  
轮2: 用户 "我要申请借款"
  → apply_loan 的 required_slots 包含 account_id
  → 依赖就绪加成 × 2.0，apply_loan 排名提升
  → 即使词汇匹配度一般，也能出现在 top-K 中
```

### 7.3 槽位就绪加成的场景收益

```
用户: "我的借款金额大概是五千元"
  → query_tokens 包含 "借款", "金额"
  → inquire_amount_discrepancy 的 required_slots 包含 loan_amount 
  → slot token "amount" 命中 → readiness_factor ≈ 1.5
  → 该 API 在 top-K 中优先展示
```

---

## 8. 未来扩展方向

1. **嵌入模型集成**：当部署环境提供向量化能力时，用稠密向量相似度替代/补充 BM25
2. **对话状态机建模**：基于历史对话数据学习 API 转移矩阵
3. **动态 top_k**：根据 query 的不确定性动态调整 K 值（高置信度时 K 可更小）
4. **API 调用成功率加权**：将历史执行失败的 API 降权，优先展示成功率高的 API
5. **LLM 辅助重排序**：在 BM25 召回的候选集上，用轻量级 LLM 做精确排序（仅适用于非实时场景）
