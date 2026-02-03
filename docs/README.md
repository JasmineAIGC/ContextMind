# ContextMind 文档索引

ContextMind v0.4.1 - 基于 ADK-Python 的上下文工程框架

---

## 🎯 ContextMind 是什么？

**ContextMind** 是一个**通用、可扩展、易集成的上下文工程框架**，专为基于大语言模型的对话系统设计。

### 核心特性

1. **底层基于 adk-python**
   - Agent 框架完全基于 `google.adk.agents.Agent`
   - 充分利用 ADK 的成熟能力

2. **自研上下文工程**
   - ADK 不提供上下文工程功能
   - 我们在 ADK Agent 基础上实现上下文工程

3. **两种工程模式**
   - DST 模式: 对话状态追踪
   - Evolution 模式: 基于进化的记忆优化

---

## 📚 核心文档

### 入门指南

- **[快速开始](quick-start.md)** ⭐
  - 5分钟快速上手
  - 安装、配置、运行

### 架构与设计

- **[架构说明](ARCHITECTURE.md)** ⭐⭐⭐
  - 框架定位和核心特性
  - 详细的架构层次
  - 设计原则和数据流
  - **强烈推荐阅读**

### 配置与使用

- **[配置指南](configuration.md)** ⭐⭐
  - 环境变量配置
  - LLM 配置
  - Embedding 配置
  - 场景配置

- **[模式说明](modes.md)** ⭐⭐
  - DST 和 Evolution 两种模式的详细对比
  - 使用场景和选择指南
  - API 使用示例

---

## 🔬 专题文档

### DST 相关

- **[DST 论文实现](paper-DST.md)**
  - ACL 2023 论文实现细节
  - 槽位提取和状态追踪原理

- **[DST 优化](dst-optimizations.md)**
  - DST 模式的优化技巧
  - 性能调优建议

---

## 📖 文档导读

### 如果你是新用户

**推荐阅读顺序**:
1. [快速开始](quick-start.md) - 5分钟上手
2. [架构说明](ARCHITECTURE.md) - 理解框架设计
3. [模式说明](modes.md) - 选择适合的模式
4. [配置指南](configuration.md) - 详细配置

### 如果你想深入了解 DST 模式

**推荐阅读顺序**:
1. [模式说明](modes.md) - DST 模式概览
2. [DST 论文实现](paper-DST.md) - 实现细节
3. [DST 优化](dst-optimizations.md) - 优化技巧

### 如果你想了解架构设计

**推荐阅读**:
1. [架构说明](ARCHITECTURE.md) - 完整的架构文档
   - 框架定位
   - 层次职责
   - 设计原则
   - 数据流

---

## 🎯 快速导航

### 按主题

- **入门**: [快速开始](quick-start.md)
- **架构**: [架构说明](ARCHITECTURE.md)
- **配置**: [配置指南](configuration.md)
- **模式**: [模式说明](modes.md)
- **DST**: [DST 论文](paper-DST.md) | [DST 优化](dst-optimizations.md)

### 按角色

- **开发者**: [架构说明](ARCHITECTURE.md) → [配置指南](configuration.md)
- **研究者**: [DST 论文实现](paper-DST.md) → [架构说明](ARCHITECTURE.md)
- **用户**: [快速开始](quick-start.md) → [模式说明](modes.md)

---

## 📊 架构概览

```
应用层 (gradio_demo, interactive_demo, apps)
    ↓
上下文工程层 (ContextMind 自研)
├── DST 模式: 槽位提取、状态追踪、Prompt 工程
└── Evolution 模式: Pipeline 算法、记忆库、记忆进化
    ↓
Agent 层 (基于 google-adk)
└── DSTAgent, EvolutionAgent (google.adk.agents.Agent)
    ↓
LLM 层 (google.adk.models)
└── OpenAI (配置为 Qwen API)
```

详见: [架构说明](ARCHITECTURE.md)

---

## 🚀 相关链接

- [主 README](../README.md) - 项目总览和快速开始
- [GitHub 仓库](https://github.com/Jasmine66Bloom/ContextMind)

---

**版本**: v0.4.1  
**更新日期**: 2026-02-03  
**核心**: 基于 ADK-Python 的上下文工程框架
