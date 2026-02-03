# ContextMind 文档索引

ContextMind v0.4.1 - 基于 ADK-Python 的上下文工程框架

---

## 📚 核心文档

### 快速开始
- **[quick-start.md](quick-start.md)** - 快速开始指南，5分钟上手

### 配置指南
- **[configuration.md](configuration.md)** - 详细的配置说明

### 模式说明
- **[modes.md](modes.md)** - DST 和 Evolution 两种模式的对比和使用场景

---

## 🔬 DST 相关文档

### DST 论文实现
- **[paper-DST.md](paper-DST.md)** - ACL 2023 论文实现细节

### DST 优化
- **[dst-optimizations.md](dst-optimizations.md)** - DST 模式的优化技巧

---

## 📖 架构说明

### DST 模式 (`dst/`)
- **对话状态追踪**（Dialogue State Tracking）
- 基于 ACL 2023 论文实现
- 专注于槽位提取和意图识别
- **ADK 负责**: Agent 框架、LLM 调用
- **自研部分**: 槽位提取算法、Prompt 工程、状态追踪

### Evolution 模式 (`evolution/`)
- **基于进化的记忆优化**
- 五层 Pipeline 上下文工程
- 记忆库和记忆进化系统
- **ADK 负责**: Agent 框架、LLM 调用
- **自研部分**: Pipeline 算法、记忆库、记忆进化

---

## 🎯 两个模式的关系

```
ContextMind v0.4.1 (直接使用 google.adk)
├── DST 模式 (dst/)
│   ├── DSTAgent - 直接使用 google.adk.agents.Agent
│   ├── 槽位提取 - 自研算法
│   └── 状态追踪 - 自研算法
│
└── Evolution 模式 (evolution/)
    ├── EvolutionAgent - 直接使用 google.adk.agents.Agent
    ├── Pipeline 算法 - 自研（压缩、重排序等）
    └── 记忆进化 - 自研系统
```

---

## 🚀 相关链接

- [主 README](../README.md) - 项目总览和快速开始
- [GitHub 仓库](https://github.com/Jasmine66Bloom/ContextMind)

---

**版本**: v0.4.1  
**更新日期**: 2026-02-03
