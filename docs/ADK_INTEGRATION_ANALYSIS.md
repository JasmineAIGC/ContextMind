# Google ADK 集成分析

## 背景

本文档分析了将 Google ADK (Agent Development Kit) 集成到 ContextMind 框架的可行性和实施方案。

## Google ADK 功能概览

### 1. 核心组件

- **google.adk.agents**: Agent 框架和编排
  - `Agent`: 基础 Agent 类
  - `LlmAgent`: LLM-based Agent
  - `SequentialAgent`, `ParallelAgent`: 多 Agent 编排
  
- **google.adk.models**: LLM 模型支持
  - `Gemini`: Google Gemini 模型
  - `Gemma`: Google Gemma 模型
  - `ApigeeLlm`: Apigee-hosted 模型
  - **不支持**: OpenAI 兼容接口

- **google.adk.memory**: 内存系统
  - `InMemoryMemoryService`: 内存中的记忆服务
  - `VertexAiMemoryBankService`: Vertex AI 记忆库
  - **功能**: 主要用于语义搜索，不是传统的会话历史管理

- **google.adk.tools**: 工具系统
  - 函数工具、OpenAPI 工具等

### 2. 限制

1. **模型支持有限**: 
   - 主要支持 Google Gemini 和 Gemma
   - 没有内置的 OpenAI 兼容接口
   - Qwen API 使用 OpenAI 兼容接口，ADK 不直接支持

2. **内存系统设计差异**:
   - ADK memory 专注于语义搜索
   - 我们的 SessionManager 是传统的会话历史管理
   - 功能不完全匹配

3. **Agent 架构复杂度**:
   - ADK Agent 使用 InvocationContext 等复杂概念
   - 我们的需求更简单直接

## 集成方案

### 方案 1: 完全迁移到 ADK（不可行）

**问题**:
- Qwen API 需要 OpenAI 兼容接口，ADK 不支持
- ADK memory 功能与我们需求不匹配
- 迁移成本高，收益低

### 方案 2: 选择性使用 ADK（推荐）

**策略**:
1. **继续使用 openai 包**: 调用 Qwen API（OpenAI 兼容）
2. **保留当前架构**: SessionManager, MemoryBank 等
3. **添加 ADK 依赖**: 为未来可能的功能预留
4. **文档说明**: 解释为什么不使用 ADK 的某些组件

**优点**:
- ✅ 保持系统稳定
- ✅ Qwen API 调用不受影响
- ✅ 代码简洁可维护
- ✅ 为未来迁移预留空间

## 实施细节

### 1. LLM 调用层

**当前实现** (`utils/qwen_client.py`):
```python
from openai import AsyncOpenAI, OpenAI

class QwenClient:
    def __init__(self, config: QwenConfig):
        self.async_client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url
        )
```

**决策**: **保留当前实现**
- ✅ Qwen API 使用 OpenAI 兼容接口
- ✅ google-adk 不直接支持 OpenAI 接口
- ✅ 使用 openai 包是最直接的方案

### 2. Agent 层

**当前实现** (`dst/adk_agent.py`, `evolution/agent.py`):
```python
class DSTAgent:
    def __init__(self, config: QwenConfig = None):
        self.client = QwenClient(config)
    
    async def chat_async(self, messages, **kwargs) -> str:
        return await self.client.chat_async(messages, **kwargs)
```

**决策**: **保留当前实现**
- ✅ 简单直接，符合需求
- ✅ google-adk.agents.Agent 设计更复杂，不适合我们的场景
- ✅ 我们的 Agent 更像是 LLM 客户端的薄封装

### 3. Memory/Session 层

**当前实现** (`evolution/memory/session.py`):
```python
class SessionManager:
    def __init__(self, app_name, user_id):
        self._session_id = str(uuid.uuid4())
        self._messages = []  # 本地消息历史
    
    async def add_message(self, role, content):
        # 添加消息到历史
    
    async def get_recent_history(self, limit):
        # 获取最近的消息
```

**ADK 实现** (`google.adk.memory.InMemoryMemoryService`):
```python
# 仅提供：
# - add_session_to_memory(session)
# - search_memory(app_name, user_id, query)
```

**决策**: **保留当前实现**
- ✅ ADK memory 主要用于语义搜索，不是会话历史
- ✅ 我们需要的是简单的消息历史管理
- ✅ 当前实现满足需求且更简洁

### 4. 自研算法

**保留所有自研算法**:
- ✅ **DST**: 槽位提取、Prompt 工程、状态追踪
- ✅ **Evolution**: Pipeline（压缩、重排序）、记忆进化、适应度计算
- ✅ 这些是我们的核心价值，ADK 不提供

## 最终决策

### 依赖配置

```python
# requirements.txt
google-adk>=1.23.0  # 添加但暂不强制使用，为未来预留
openai>=1.0.0       # Qwen API（OpenAI 兼容接口）
```

### 架构说明

```
ContextMind 框架
├── LLM 层: openai 包（Qwen API）
├── Agent 层: 轻量封装（DSTAgent, EvolutionAgent）
├── Memory 层: 本地实现（SessionManager, MemoryBank）
└── 自研算法层: DST 槽位提取 + Evolution Pipeline
```

**不使用 google-adk 的原因**:
1. Qwen API 使用 OpenAI 兼容接口，ADK 不支持
2. ADK memory 功能与需求不匹配
3. 当前架构更简洁，满足需求

**保留 google-adk 依赖的原因**:
1. 为未来可能的迁移预留
2. 如果切换到 Gemini 模型，可以快速切换
3. 可能使用 ADK 的其他功能（工具系统等）

## 未来可能的 ADK 使用场景

1. **如果切换到 Gemini**: 可以使用 `google.adk.models.Gemini`
2. **多 Agent 编排**: 可以使用 `SequentialAgent`, `ParallelAgent`
3. **工具系统**: 可以使用 `google.adk.tools`
4. **高级内存**: 如果需要语义搜索，可以使用 ADK memory

## 总结

基于当前需求和技术栈：
- ✅ **添加 google-adk 依赖**: 为未来预留
- ✅ **保留当前 LLM 实现**: openai 包 + Qwen API
- ✅ **保留当前 Agent 实现**: 简单轻量的封装
- ✅ **保留当前 Memory 实现**: 满足会话历史需求
- ✅ **保留所有自研算法**: DST 和 Evolution 的核心价值

这个方案在保持系统稳定性的同时，为未来的演进留出了空间。
