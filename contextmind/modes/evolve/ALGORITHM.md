# Evolve — 进化式上下文工程框架

## 1. 设计来源

Evolve 是 ContextMind 的**核心原创算法**，不直接对应某一篇具体论文，而是综合了上下文工程领域多个方向的研究成果：

| 灵感来源 | 对应概念 |
|----------|----------|
| MemGPT（2023）| 分层记忆管理（短期 session + 长期 memory） |
| GRACE（EMNLP 2022）| 检索增强的对话生成 |
| 进化算法（GA/NSGA-II）| 适应度评估 + 精英选择 + 记忆淘汰 |
| Lost in the Middle（2023）| 上下文重排序（相关内容靠近查询端） |
| 对话摘要研究（ACL 2023）| 长对话压缩与摘要 |

核心创新：将**进化计算思想**引入对话记忆管理——记忆不是简单地追加，而是通过「适应度评估 → 精英保留 → 相似合并 → 容量淘汰」持续优化，确保记忆库始终存储最有价值的信息。

---

## 2. 算法原理

### 2.1 整体架构

```
用户话语
    ↓
[Step 1] InputPreprocessor      — 输入预处理与标准化
    ↓
[Step 2] MemoryBank.retrieve()  — 从长期记忆检索相关上下文
    ↓
[Step 3] ContextCompressor      — 压缩冗余上下文（Token 优化）
    ↓    ContextReorderer       — 重排序（相关内容靠近查询端）
    ↓
[Step 4] LLM 生成回复           — system_prompt + 历史 + 检索结果 + 当前话语
    ↓
[Step 5a] SessionManager.update()         — 更新短期会话历史
[Step 5b] EvolveEngine.extract_knowledge() — 后台异步提取知识并更新长期记忆
    ↓
用户回复
```

### 2.2 双层记忆架构

#### 短期记忆：Session（会话级）

基于 Google ADK `InMemorySessionService` 管理：
- 存储当前会话的完整对话历史；
- 每轮自动追加用户话语和 LLM 回复；
- 支持跨会话的会话历史检索（`search_memory()`）；
- 对话结束时自动持久化到 `InMemoryMemoryService`。

#### 长期记忆：MemoryBank（用户级）

跨会话持久化的知识图谱，存储从对话中提取的结构化知识：

```python
class Knowledge:
    content: str         # 知识内容（如"用户喜欢简洁回答"）
    knowledge_type: KnowledgeType  # FACT / PREFERENCE / EVENT
    confidence: float    # 置信度（存储阈值：偏好 ≥ 0.75，事实 ≥ 0.70）
    source: str          # 来源对话 ID
```

### 2.3 进化式记忆更新（`EvolutionaryMemoryUpdater`）

这是 Evolve 模式的核心创新，借鉴进化算法对记忆库进行持续优化：

#### 适应度评估（`FitnessCalculator`）

每条记忆的「适应度」由多维度加权计算：

```python
fitness = (
    w_usage    × usage_score     # 使用频率（越常被检索越有价值）
  + w_recency  × recency_score   # 新鲜度（近期记忆权重更高）
  + w_confidence × confidence    # 置信度（知识提取时的质量评估）
  + w_feedback × feedback_score  # 用户反馈（正向 +，纠正 -）
)
```

#### 进化更新流程

```
新知识到来
    ↓
1. 相似性检测（基于 embedding 余弦相似度，阈值 0.85）
   → 与已有记忆高度相似？合并（保留更高置信度的版本）
    ↓
2. 适应度计算（对新知识和现有记忆）
    ↓
3. 精英保留（保留前 70% 适应度的记忆）
    ↓
4. 容量控制（超出 max_size=100 时淘汰最低适应度记忆）
    ↓
5. 更新记忆库
```

#### 使用次数衰减

随时间推移，未被使用的记忆适应度自然衰减：

```python
decay_factor = 0.95 ^ (days_since_last_use)
```

这确保了记忆库的「新陈代谢」：旧的、不再相关的记忆被逐渐淘汰。

### 2.4 上下文检索优化

#### 语义检索（`SemanticSearchRetriever`）

使用 embedding 相似度从 MemoryBank 检索与当前查询最相关的 top-K 记忆：

```python
similarities = cosine_similarity(query_embedding, memory_embeddings)
top_k_items = sorted(zip(similarities, memories))[-k:]
```

过滤条件：相关性分数 ≥ `RELEVANCE_THRESHOLD`（默认 0.3），避免注入无关噪声。

#### 上下文重排序（`ContextReorderer`）

基于论文「Lost in the Middle」的发现：LLM 对上下文首尾的信息利用率远高于中间。重排序将相关性最高的内容放在靠近查询端（末尾），提升 LLM 的信息利用效率。

#### 上下文压缩（`ContextCompressor`）

当检索到的上下文过长时，压缩冗余信息（合并相似内容、截断低置信度片段），控制注入 Token 数量。

### 2.5 对话摘要（`ConversationSummarizer`）

当对话历史超过阈值（默认 15 轮）时，自动摘要早期历史：

```
[早期对话摘要] + [最近 5 轮完整历史]
```

支持两种摘要策略：
- **LLMBasedSummarizer**：调用 LLM 生成高质量摘要；
- **ConversationSummarizer**：基于模板的轻量摘要（抽取关键状态）。

### 2.6 知识提取（异步后台）

每轮对话结束后，在**后台异步**提取本轮对话中的新知识，不阻塞用户响应：

```python
asyncio.create_task(_bg_extract())
```

`LLMBasedExtractor` 分析最近几轮对话，提取结构化知识：
- 用户偏好（`PREFERENCE`）：如「用户偏好简洁回答」；
- 事实信息（`FACT`）：如「用户所在城市为深圳」；
- 事件记录（`EVENT`）：如「用户于 10 月查询了贷款信息」。

提取结果经置信度过滤后写入 MemoryBank，在后续对话中检索使用。

---

## 3. 代码结构

```
evolve/
├── __init__.py
├── app.py                    # EvolveApplication：五步流水线封装
├── factory.py                # create_app_for_scenario() 工厂方法
│
├── core/
│   ├── engine.py             # EvolveEngine：核心引擎
│   ├── data_models.py        # Message / Knowledge / ContextItem 等数据模型
│   ├── config.py             # 配置类（ExtractionConfig / RetrievalConfig 等）
│   ├── strategies.py         # 策略基类（BaseExtractor / BaseRetriever / BaseUpdater）
│   └── registry.py           # 插件注册表
│
├── memory/
│   ├── bank.py               # MemoryBank：长期记忆存储与检索
│   ├── session.py            # SessionManager：短期会话历史
│   ├── extractor.py          # LLMBasedExtractor：知识提取
│   ├── retriever.py          # SemanticSearchRetriever：语义检索
│   ├── updater.py            # SimpleUpdater：简单记忆更新
│   └── fitness.py            # MemoryFitness + FitnessCalculator
│
├── evolution/
│   ├── updater.py            # EvolutionaryMemoryUpdater：进化式更新
│   └── feedback.py           # FeedbackCollector + ImplicitFeedbackAnalyzer
│
└── pipeline/
    ├── steps.py              # InputPreprocessor / ContextRetriever / ContextCompressor / ContextReorderer
    ├── response_handler.py   # ResponseHandler：LLM 回复生成
    └── summarizer.py         # ConversationSummarizer / LLMBasedSummarizer
```

### 3.1 EvolveEngine（`core/engine.py`）

```python
class EvolveEngine:
    def __init__(self, *, app_name, user_id, llm_client, ...):
        # 自动创建 ADK InMemorySessionService + InMemoryMemoryService
        self.session_manager = SessionManager(...)
        self.memory_bank = MemoryBank(...)
        self.extractor = LLMBasedExtractor(llm_client, ...)

    async def optimize(self, session_id, user_input):
        """检索相关上下文，返回 ContextResult（含记忆检索结果）。"""

    async def update(self, session_id, user_input, response):
        """更新会话历史，持久化 session → memory。"""

    async def extract_knowledge(self, auto_store=True):
        """从最近对话提取知识，写入 MemoryBank。"""
```

### 3.2 EvolveApplication（`app.py`）

```python
class EvolveApplication:
    async def process_turn(self, user_input) -> str:
        # Step 1: 预处理
        processed = await self.preprocessor.process(user_input)
        # Step 2: 检索
        context_result = await self.evolve_engine.optimize(session_id, processed)
        # Step 3: 压缩 + 重排序
        compressed = await self.compressor.compress(context_result)
        reordered  = await self.reorderer.reorder(compressed, processed)
        # Step 4: LLM 生成（system_prompt + 历史 + 检索结果 + 当前话语）
        response = await self._call_llm(processed, reordered)
        # Step 5: 更新（同步 session + 异步知识提取）
        await self.evolve_engine.update(session_id, processed, response)
        asyncio.create_task(self.evolve_engine.extract_knowledge())
        return response
```

### 3.3 MemoryBank（`memory/bank.py`）

```python
class MemoryBank:
    STORAGE_THRESHOLD_PREFERENCE = 0.75  # 偏好类知识存储阈值
    STORAGE_THRESHOLD_FACT = 0.70        # 事实类知识存储阈值

    async def store(self, knowledge_list):
        """过滤低置信度知识，存入 ADK InMemoryMemoryService。"""

    async def retrieve(self, query, top_k=5):
        """语义检索，返回相关性最高的 top-K 上下文项。"""

    async def evolve(self, new_knowledge):
        """触发进化式更新（EvolutionaryMemoryUpdater）。"""
```

### 3.4 EvolutionaryMemoryUpdater（`evolution/updater.py`）

```python
class EvolutionaryMemoryUpdater:
    def __init__(self, max_memory_size=100, elite_ratio=0.7,
                 similarity_threshold=0.85, min_fitness_threshold=0.2):

    async def update(self, memory_cache, new_knowledge):
        """进化式更新：相似合并 → 适应度计算 → 精英保留 → 容量控制。"""
        # 1. 相似性检测，合并高度相似记忆
        # 2. 计算所有记忆的适应度分数
        # 3. 按 elite_ratio 保留高适应度记忆
        # 4. 超出 max_size 时淘汰末尾低质记忆
```

---

## 4. 运行时数据流（完整）

```
用户话语
    ↓
EvolveApplication.process_turn(user_input)
    │
    ├─ Step 1: InputPreprocessor.process()
    │          去空白 → 长度校验 → 多余空格归一化
    │
    ├─ Step 2: EvolveEngine.optimize(session_id, user_input)
    │          ├─ SessionManager.get_recent_history()   ← 短期记忆（当前会话）
    │          └─ MemoryBank.retrieve(user_input, top_k=5) ← 长期记忆（跨会话）
    │
    ├─ Step 3: ContextCompressor → ContextReorderer
    │          压缩冗余 → 相关内容移至末尾
    │
    ├─ Step 4: ResponseHandler.generate()
    │          [system_prompt] + [历史] + [检索结果] + [当前话语]
    │          → LLM → 回复文本
    │
    └─ Step 5: EvolveEngine.update() + asyncio.create_task(extract_knowledge())
               ├─ 同步: SessionManager.add_turn() + persist_session_to_memory()
               └─ 异步: LLMBasedExtractor → MemoryBank.evolve()
                        (不阻塞响应，后台完成知识进化)

return response
```

---

## 5. 与其他模式的定位

| 模式 | 适用场景 | 对话策略 | 记忆机制 |
|------|----------|----------|----------|
| **Evolve** | 开放域对话 / 长期用户关系 | 无结构化策略，LLM 自由生成 | 进化式长期记忆 |
| DST | 结构化槽位追踪 | 累积状态追踪 | 无 |
| FnCTOD | 结构化槽位提取 | 函数调用约束 | 无 |
| PyTOD | 复杂多步业务流程 | 数据流程序 | 无 |
| Genie | 表单填写 / 引导式对话 | Worksheet 状态机 | 无 |

Evolve 是唯一具备**跨对话长期记忆**的模式，适合需要「记住用户偏好」的长期服务场景。

---

## 6. 参考资源

- MemGPT：https://arxiv.org/abs/2310.08560  
- GRACE（检索增强对话）：https://arxiv.org/abs/2211.06924  
- Lost in the Middle：https://arxiv.org/abs/2307.03172  
- Google ADK Memory Service：https://google.github.io/adk-docs/sessions/memory/
