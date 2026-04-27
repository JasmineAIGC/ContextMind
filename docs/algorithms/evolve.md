# Evolve模式（演化式上下文优化）

## 概述

Evolve（Evolutionary Context Optimization，演化式上下文优化）是基于 **ThetaEvolve 算法**的对话管理模式，通过智能记忆管理和上下文优化实现长对话处理。

- **实现状态**: ✅ 已实现
- **论文（ThetaEvolve）**: [ThetaEvolve: Test-time Learning on Open Problems](https://arxiv.org/pdf/2511.23473)

### 三步框架依赖

| 步骤 | 是否需要 | 说明 |
|------|:-------:|------|
| **① 建立知识库** | ❌ 不需要 | Evolve 基于长期记忆，无需外部 schema.json |
| **② Schema 数据生成** | ❌ 不需要 | Evolve 不依赖算法专用代码文件 |
| **③ 算法执行（Evolve）** | ✅ 必须 | 演化式上下文检索、记忆管理与对话生成 |

Evolve 是最独立的算法——完全不依赖第一步和第二步，适合通用聊天、开放域长对话等无需预定义业务 Schema 的场景。

## 架构设计

Evolve模式由以下核心组件构成：

- **EvolveEngine**：核心引擎，协调所有组件
- **Memory 系统**：MemoryBank、MemoryExtractor、MemoryRetriever、MemoryUpdater、fitness.py
- **Pipeline**：InputPreprocessor、ContextRetriever、ContextCompressor、ContextReorderer、Summarizer
- **Evolution**：EvolutionaryMemoryUpdater（updater.py）、FeedbackCollector（feedback.py）
- **Core Framework**：DataModels、Config、Strategies、Registry

## 使用示例

```python
import asyncio
from contextmind.modes.evolve import create_app_for_scenario
from contextmind.infra.llm_client import AdkLLMClient
from contextmind.scenarios import get_chat_scenario

llm_client = AdkLLMClient()
scenario_config = get_chat_scenario()
app = create_app_for_scenario(
    scenario_name="chat",
    llm_client=llm_client,
    scenario_config=scenario_config,
)

async def main():
    response = await app.process_turn("你好，我叫张三")
    print(response)

asyncio.run(main())
```

## 性能特点

### 优势

1. **智能记忆**：记住用户信息和对话上下文
2. **长对话优化**：通过压缩和检索处理长对话
3. **自我演化**：记忆库持续优化
4. **个性化**：基于记忆提供个性化回复

### 适用场景

- ✅ 长期对话（需要记住历史信息）
- ✅ 个性化助手（需要了解用户）
- ✅ 知识积累（需要学习和记忆）
- ✅ 复杂上下文（需要上下文理解）

### 局限性

- ❌ 计算开销较大（检索、压缩等）
- ❌ 需要向量数据库（存储 embeddings）
- ❌ 冷启动时效果一般（记忆库为空）

## 参考资料

- [ThetaEvolve 论文：ThetaEvolve: Test-time Learning on Open Problems](https://arxiv.org/pdf/2511.23473)
- [评测指标说明](../reference/benchmark.md)
- [API 参考](../reference/api-reference.md)
