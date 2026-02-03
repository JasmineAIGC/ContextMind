# Google-ADK Session 和 Memory 集成

## 概述

本文档说明如何使用 google-adk 的 Session 和 Memory 服务简化 ContextMind 的实现。

## 背景

经过深入分析，发现 google-adk 提供了以下可以直接使用的功能：

1. **Session 管理** (`google.adk.sessions`)
2. **Memory 管理** (`google.adk.memory`)

这些功能可以替代我们从零实现的部分，简化代码并提供更标准的接口。

## 架构变化

### 之前的架构

```
Evolution Mode
├── session.py (~150 行) - 手动实现会话管理
└── bank.py (~200 行) - 手动实现记忆存储
```

### 现在的架构

```
Evolution Mode
├── adk_session.py (~80 行) - 使用 google.adk.sessions ✅
└── adk_memory.py (~120 行) - 使用 google.adk.memory ✅
```

**代码减少**: ~350 行 → ~200 行（减少 43%）

## 使用方法

### 1. ADK Session Manager

```python
from evolution import ADKSessionManager
from evolution.core.data_models import MessageRole

# 创建会话管理器
session_manager = ADKSessionManager(
    app_name="my_app",
    user_id="user_123"
)

# 添加消息
await session_manager.add_message(
    role=MessageRole.USER,
    content="你好"
)

# 获取历史
history = await session_manager.get_recent_history(limit=10)

# 获取 ADK Session 对象（用于 Memory）
session = session_manager.get_session()
```

### 2. ADK Memory Bank

```python
from evolution import ADKMemoryBank
from evolution.core.data_models import Memory, MemoryType

# 创建记忆库
memory_bank = ADKMemoryBank(
    app_name="my_app",
    user_id="user_123"
)

# 存储记忆
memory = Memory(
    content="用户喜欢Python编程",
    memory_type=MemoryType.KNOWLEDGE,
    importance=0.8
)
await memory_bank.store_memory(memory)

# 将会话添加到记忆（使用 ADK）
session = session_manager.get_session()
await memory_bank.add_session_to_memory(session)

# 语义搜索（使用 ADK）
results = await memory_bank.search_memory(
    query="用户的编程偏好",
    top_k=5
)

# 按类型获取记忆（本地缓存）
knowledge = await memory_bank.get_memories_by_type(MemoryType.KNOWLEDGE)
```

## ADK 提供的功能

### google.adk.sessions

**InMemorySessionService**:
- `create_session(app_name, user_id)` - 创建会话
- `get_session(app_name, user_id, session_id)` - 获取会话
- `delete_session(app_name, user_id, session_id)` - 删除会话

**Session**:
- `session_id` - 会话ID
- `state` - 会话状态（Dict）
- `state.update(data)` - 更新状态
- `state.get(key)` - 获取状态

**State**:
- 支持字典操作
- 自动管理状态更新

### google.adk.memory

**InMemoryMemoryService**:
- `add_session_to_memory(session)` - 将会话添加到记忆
- `search_memory(app_name, user_id, query)` - 语义搜索

**特点**:
- 使用向量嵌入进行语义搜索
- 自动索引和检索
- 支持多用户隔离

## 职责划分

### ADK 负责

1. **Session 管理**:
   - 会话的创建和存储
   - 会话状态的管理
   - 会话 ID 的生成

2. **Memory 管理**:
   - 记忆的存储
   - 语义搜索和检索
   - 向量嵌入

### ContextMind 负责

1. **数据模型**:
   - `Message`, `Memory` 等领域模型
   - 类型定义和验证

2. **业务逻辑**:
   - 记忆分类（knowledge, long_term, short_term）
   - 记忆进化算法
   - 适应度计算

3. **上下文工程**:
   - Pipeline 算法
   - DST 槽位提取
   - 所有自研算法

## 集成步骤

### 1. 替换旧的 Session 管理

**之前**:
```python
from evolution.memory.session import SessionManager
```

**现在**:
```python
from evolution import ADKSessionManager
```

### 2. 替换旧的 Memory Bank

**之前**:
```python
from evolution.memory.bank import MemoryBank
```

**现在**:
```python
from evolution import ADKMemoryBank
```

### 3. 更新 EvolutionEngine

在 `evolution/engine.py` 中：

```python
# 使用 ADK Session
self.session_manager = ADKSessionManager(
    app_name=app_name,
    user_id=user_id
)

# 使用 ADK Memory
self.memory_bank = ADKMemoryBank(
    app_name=app_name,
    user_id=user_id
)
```

## 收益

### 1. 代码简化

- Session: 150 行 → 80 行（减少 47%）
- Memory: 200 行 → 120 行（减少 40%）
- 总计: 350 行 → 200 行（减少 43%）

### 2. 功能增强

- ✅ 语义搜索（ADK 的向量检索）
- ✅ 多用户隔离
- ✅ 标准化接口

### 3. 更好的维护性

- ✅ 使用成熟的库
- ✅ 减少自己维护的代码
- ✅ 获得 ADK 的持续更新

### 4. 保留核心价值

- ✅ 上下文工程算法仍是自研
- ✅ 记忆进化逻辑仍是自研
- ✅ ContextMind 的核心价值不变

## 兼容性

### 向后兼容

旧的 `SessionManager` 和 `MemoryBank` 仍然存在（未删除），但推荐使用新的 ADK-based 实现。

### 迁移指南

1. 更新导入语句
2. 代码逻辑无需修改（接口兼容）
3. 测试验证功能

## 限制和注意事项

### google-adk 的限制

1. **不支持 OpenAI 兼容接口**: ADK 主要支持 Gemini，所以 LLM 层仍使用 openai SDK
2. **内存存储**: `InMemoryMemoryService` 是内存存储，重启后数据丢失
3. **语义搜索**: 需要嵌入模型支持

### 保留本地实现的原因

1. **记忆分类**: ADK 不提供按类型分类，所以保留本地缓存
2. **进化逻辑**: ADK 不提供记忆进化，这是我们的核心算法
3. **业务逻辑**: 特定场景的需求 ADK 无法满足

## 未来计划

1. **持久化存储**: 可以使用 `VertexAiMemoryBankService`（需要 GCP）
2. **RAG 支持**: 可以使用 `VertexAiRagMemoryService`（需要 GCP）
3. **更多 ADK 功能**: 探索 ADK 的其他功能（tools, agents 等）

## 总结

通过使用 google-adk 的 Session 和 Memory 服务：

- ✅ **代码简化**: 减少 43% 的基础设施代码
- ✅ **功能增强**: 获得语义搜索等高级功能
- ✅ **保留核心**: 上下文工程算法仍是自研
- ✅ **架构清晰**: ADK 负责基础设施，ContextMind 负责上下文工程

这完美符合 ContextMind 的定位：基于 adk-python 的上下文工程框架。

---

**版本**: v0.4.1  
**更新日期**: 2026-02-03  
**相关文件**: `evolution/memory/adk_session.py`, `evolution/memory/adk_memory.py`
