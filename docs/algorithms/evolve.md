# Evolve模式（演化式上下文优化）

## 概述

Evolve 是 ContextMind 的原创算法，综合了上下文工程领域多个研究方向（MemGPT 分层记忆、GRACE 检索增强生成、进化算法适应度评估、上下文重排序）的核心思想。通过双层记忆架构（短期 Session + 长期 MemoryBank）和进化式更新，实现长对话的智能上下文管理。

- **实现状态**: ✅ 已实现
- **论文（ThetaEvolve）**: [ThetaEvolve: Test-time Learning on Open Problems](https://arxiv.org/pdf/2511.23473)

### 三步框架依赖

| 步骤 | 是否需要 | 说明 |
|------|:-------:|------|
| **① 建立知识库** | ❌ 不需要 | Evolve 基于长期记忆，无需外部 schema.json |
| **② Schema 数据生成** | ❌ 不需要 | Evolve 不依赖算法专用代码文件 |
| **③ 算法执行（Evolve）** | ✅ 必须 | 演化式上下文检索、记忆管理与对话生成 |

Evolve 完全不依赖第一步和第二步，适合通用聊天、开放域长对话等无需预定义业务 Schema 的场景。

---

## 算法架构

### 双层记忆架构

**短期记忆（Session）**：基于 ADK `InMemorySessionService`，存储当前会话的完整对话历史，会话结束后持久化到 `InMemoryMemoryService`。

**长期记忆（MemoryBank）**：跨会话持久化的知识存储，存储从对话中提取的结构化知识：

```python
class Knowledge:
    content: str         # 知识内容（如"用户喜欢简洁回答"）
    knowledge_type: KnowledgeType  # FACT / PREFERENCE / EVENT
    confidence: float    # 置信度（偏好 ≥ 0.75，事实 ≥ 0.70 才存储）
    source: str          # 来源对话 ID
```

### 进化式记忆更新（EvolutionaryMemoryUpdater）

每轮对话结束后**异步**提取知识，通过进化算法持续优化记忆库：

```
新知识到来
    ↓
1. 相似性检测（余弦相似度，阈值 0.85）→ 与已有记忆高度相似则合并
    ↓
2. 适应度计算：fitness = w_usage × 使用频率 + w_recency × 新鲜度
              + w_confidence × 置信度 + w_feedback × 用户反馈
    ↓
3. 精英保留（保留前 70% 适应度的记忆）
    ↓
4. 容量控制（超出 max_size=100 时淘汰最低适应度记忆）
```

### 五步处理流程

```
用户话语
    ↓
Step 1: InputPreprocessor — 去空白、长度校验、归一化
    ↓
Step 2: EvolveEngine.optimize() — 检索短期 Session + 长期 MemoryBank（top-K=5）
    ↓
Step 3: ContextCompressor → ContextReorderer — 压缩冗余，相关内容移至末尾
    ↓
Step 4: LLM 生成回复（system_prompt + 历史 + 检索结果 + 当前话语）
    ↓
Step 5: 同步更新 Session + 异步知识提取（asyncio.create_task）
    ↓
用户回复
```

---

## 代码结构

```
evolve/
├── app.py                    # EvolveApplication：五步流水线封装
├── factory.py                # create_app_for_scenario() 工厂方法
├── core/
│   ├── engine.py             # EvolveEngine：核心引擎（optimize/update/extract）
│   ├── data_models.py        # Message / Knowledge / ContextItem 等数据模型
│   ├── config.py             # 配置类（ExtractionConfig / RetrievalConfig 等）
│   ├── strategies.py         # 策略基类（BaseExtractor / BaseRetriever / BaseUpdater）
│   └── registry.py           # 插件注册表
├── memory/
│   ├── bank.py               # MemoryBank：长期记忆存储与检索
│   ├── session.py            # SessionManager：短期会话历史
│   ├── extractor.py          # LLMBasedExtractor：知识提取
│   ├── retriever.py          # SemanticSearchRetriever：语义检索
│   ├── updater.py            # SimpleUpdater：简单记忆更新
│   └── fitness.py            # MemoryFitness + FitnessCalculator
├── evolution/
│   ├── updater.py            # EvolutionaryMemoryUpdater：进化式更新
│   └── feedback.py           # FeedbackCollector + ImplicitFeedbackAnalyzer
└── pipeline/
    ├── steps.py              # InputPreprocessor / ContextRetriever / ContextCompressor / ContextReorderer
    ├── response_handler.py   # ResponseHandler：LLM 回复生成
    └── summarizer.py         # ConversationSummarizer / LLMBasedSummarizer
```

---

## 使用示例

```python
import asyncio
from contextmind.modes.evolve import create_app_for_scenario
from contextmind.infra.llm_client import AdkLLMClient
from contextmind.scenarios import get_chat_scenario

llm_client = AdkLLMClient()
app = create_app_for_scenario(
    scenario_name="chat",
    llm_client=llm_client,
    scenario_config=get_chat_scenario(),
)

async def main():
    response = await app.process_turn("你好，我叫张三")
    print(response)
    # 后续对话会记住用户名字
    response = await app.process_turn("我喜欢打篮球")
    print(response)

asyncio.run(main())
```

---

## 性能特点

### 优势

1. **智能记忆**：记住用户信息和对话上下文
2. **长对话优化**：通过压缩和检索处理长对话
3. **自我演化**：记忆库通过进化算法持续优化
4. **个性化**：基于记忆提供个性化回复

### 适用场景

- ✅ 长期对话（需要记住历史信息）
- ✅ 个性化助手（需要了解用户）
- ✅ 开放域聊天（无需预定义业务 Schema）

### 局限性

- ❌ 计算开销较大（检索、压缩、异步知识提取）
- ❌ 需要 embedding 支持（语义检索）
- ❌ 冷启动时效果一般（记忆库为空）

---

## 参考资料

- [ThetaEvolve 论文](https://arxiv.org/pdf/2511.23473)
- [Evolve 详细算法说明](../../contextmind/modes/evolve/ALGORITHM.md)
- [API 参考](../reference/api-reference.md)
