# ContextMind 框架总结

ContextMind v0.4.1 - 基于 ADK-Python 的上下文工程框架

---

## 🎯 核心定位

**ContextMind** 是一个**通用、可扩展、易集成的上下文工程框架**。

### 三句话总结

1. **底层基于 adk-python**: Agent 框架和 LLM 调用完全基于 google-adk
2. **自研上下文工程**: ADK 不提供上下文工程功能，我们在 ADK Agent 基础上实现
3. **两种工程模式**: 提供 DST 和 Evolution 两种不同的上下文工程实现

---

## 🏗️ 框架层次

```
┌─────────────────────────────────────────────────────┐
│          应用层 (Applications)                       │
│  gradio_demo, interactive_demo, apps                 │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│       上下文工程层 (Context Engineering)             │
│  ┌─────────────┐          ┌────────────────┐        │
│  │  DST 模式   │          │ Evolution 模式  │        │
│  │  自研实现   │          │  自研实现       │        │
│  └─────────────┘          └────────────────┘        │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│          Agent 层 (基于 google-adk)                  │
│  DSTAgent, EvolutionAgent                            │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│         LLM 层 (google.adk.models)                   │
│  OpenAI (配置为 Qwen API)                            │
└─────────────────────────────────────────────────────┘
```

---

## 🔑 职责划分

### ADK 负责（底层基础设施）

- ✅ Agent 框架和生命周期管理
- ✅ LLM 模型调用和管理
- ✅ 底层通信和错误处理
- ✅ 模型配置和参数管理

### ContextMind 负责（上下文工程）

**DST 模式**:
- ✅ 槽位提取算法
- ✅ 对话状态追踪
- ✅ Prompt 工程
- ✅ 响应解析

**Evolution 模式**:
- ✅ Pipeline 算法（预处理、压缩、重排序、摘要）
- ✅ 记忆库管理
- ✅ 记忆进化系统
- ✅ 会话管理

**共同部分**:
- ✅ 场景配置系统
- ✅ 应用层业务逻辑
- ✅ 用户交互界面

---

## 💡 设计原则

### 1. 职责分离

**原则**: ADK 负责 Agent 和 LLM，ContextMind 负责上下文工程

**实践**:
- 不重复实现 ADK 已有的功能
- 专注于上下文工程算法
- 保持清晰的层次边界

### 2. 最小化本地实现

**原则**: 尽量直接使用 ADK 已有的能力，无需本地实现

**实践**:
- Agent 框架：直接使用 `google.adk.agents.Agent`
- LLM 调用：直接使用 `google.adk.models.openai.OpenAI`
- 本地实现仅限于 ADK 不提供的上下文工程功能

### 3. 可扩展性

**原则**: 框架应该易于扩展和集成

**实践**:
- 场景配置系统：轻松添加新场景
- 标准化接口：易于集成到现有系统
- 模块化设计：可以单独使用某个模式

---

## 📊 两种模式对比

| 维度 | DST 模式 | Evolution 模式 |
|------|---------|----------------|
| **定位** | 对话状态追踪 | 完整上下文工程方案 |
| **技术基础** | ACL 2023 论文 | Pipeline + 记忆进化 |
| **ADK 使用** | Agent + LLM | Agent + LLM |
| **自研核心** | 槽位提取、状态追踪 | Pipeline、记忆系统 |
| **复杂度** | ⭐⭐ 轻量 | ⭐⭐⭐⭐ 完整 |
| **适用场景** | 结构化任务 | 开放域对话 |

---

## 🎨 核心价值

### 为什么使用 ContextMind？

1. **专业的上下文工程**
   - 不只是简单的对话管理
   - 提供专业的上下文理解、管理和优化

2. **基于成熟框架**
   - 底层 Agent 基于 google-adk
   - 避免重复造轮子
   - 专注于上下文工程本身

3. **通用性和可扩展性**
   - 场景配置系统
   - 标准化接口
   - 易于集成

4. **两种模式选择**
   - DST：适合结构化任务
   - Evolution：适合开放域对话

---

## 🚀 快速开始

### 安装

```bash
pip install -r requirements.txt
```

### 配置

```ini
# .env 文件
QWEN3_API_KEY=your-key
QWEN3_BASE_URL=http://your-endpoint/v1
QWEN3_MODEL=Qwen2.5-7B-Instruct
```

### 使用

**DST 模式**:
```python
from dst import DSTAgent, DialogueStateTracker

agent = DSTAgent()
tracker = DialogueStateTracker(llm_client=agent)
state = await tracker.track_turn(system_msg, user_msg)
```

**Evolution 模式**:
```python
from evolution import EvolutionAgent, EvolutionEngine

agent = EvolutionAgent()
engine = EvolutionEngine(llm_client=agent)
context = await engine.optimize(user_input)
```

---

## 📚 文档

- **[架构说明](ARCHITECTURE.md)** - 详细的框架架构
- **[快速开始](quick-start.md)** - 5分钟上手
- **[配置指南](configuration.md)** - 配置说明
- **[模式说明](modes.md)** - 两种模式对比

---

## 🎯 总结

ContextMind 是：

- ✅ **上下文工程框架** - 专注于上下文工程
- ✅ **基于 adk-python** - 充分利用 ADK 的能力
- ✅ **通用可扩展** - 易于集成和扩展
- ✅ **双模式支持** - DST 和 Evolution

**核心价值**: 在 ADK 提供的稳定 Agent 基础上，实现专业的上下文工程能力。

---

**版本**: v0.4.1  
**更新日期**: 2026-02-03
