# ContextMind 文档中心

欢迎来到 ContextMind 文档中心！这里包含了使用 ContextMind 所需的所有文档。

## 📚 文档导航

### 入门指南

- [快速开始](quick-start.md) - 安装、配置和第一个程序
- [示例代码](examples.md) - 完整的代码示例集合
- [目录结构](directory-structure.md) - 项目目录结构详解

### 核心概念

- [模式对比](modes.md) - DST / FnCTOD / Evolve 三种对话模式详细对比
- [配置指南](configuration.md) - 高级配置选项
- [评测指标](metrics-explanation.md) - 评测指标详细说明（含常见问题分析）

### 算法文档

- [DST 算法](algorithms/dst.md) - 对话状态追踪算法（已实现）
- [FnCTOD 算法](algorithms/fnctod.md) - 函数调用式任务型对话算法（已实现）
- [pyTOD 算法](algorithms/pytod.md) - 可编程任务型对话算法（已实现，含安逸花双引擎架构说明）
- [Evolve 算法](algorithms/evolve.md) - 演化式上下文优化算法
- [PyTOD vs FnCTOD 对比](algorithms/pytod-vs-fnctod-comparison.md) - 两种框架深度对比分析
- [意图评测](algorithms/intent-evaluation.md) - IntentEvaluator 使用指南
- [上下文工程](algorithms/context-engineering.md) - DST 和 FnCTOD 评测对上下文工程的意义
- [Benchmark 评测框架](benchmark.md) - 四种算法评测框架使用指南

### 数据集文档

- [SGD 数据集](datasets/sgd.md) - Schema-Guided Dialogue 数据集（pyTOD 使用）
- [TransferTOD 数据集](datasets/transfertod.md) - TransferTOD 数据集说明（含数量差异解析）
- [RiSAWOZ 数据集](datasets/risawoz.md) - RiSAWOZ 数据集文件与目录结构说明

### 开发指南

- [API 参考](api-reference.md) - 完整的 API 文档
- [扩展场景](extending-scenarios.md) - 添加新场景的指南
- [贡献指南](CONTRIBUTING.md) - 如何参与贡献

### 帮助和支持

- [故障排查](troubleshooting.md) - 常见问题和解决方案
- [更新日志](changelog.md) - 版本变更历史

---

## 📂 文档结构

```
docs/
├── README.md                      # 文档索引（本文件）
├── quick-start.md                 # 快速开始
├── examples.md                    # 示例代码
├── directory-structure.md         # 项目目录结构
├── modes.md                       # 四种对话模式对比
├── configuration.md               # 配置指南
├── api-reference.md               # API 参考
├── metrics-explanation.md         # 评测指标说明
├── extending-scenarios.md         # 扩展场景
├── troubleshooting.md             # 故障排查
├── changelog.md                   # 更新日志
├── CONTRIBUTING.md                # 贡献指南
├── algorithms/                    # 算法文档
│   ├── dst.md                     # DST 算法（已实现）
│   ├── fnctod.md                  # FnCTOD 算法（已实现）
│   ├── pytod.md                   # PyTOD 算法（已实现，含安逸花双引擎架构说明）
│   ├── pytod-vs-fnctod-comparison.md  # PyTOD vs FnCTOD 深度对比分析
│   ├── intent-evaluation.md       # 意图评测使用指南
│   └── context-engineering.md     # 上下文工程意义
└── datasets/                      # 数据集文档
    ├── sgd.md                     # SGD 数据集（PyTOD 使用）
    ├── transfertod.md             # TransferTOD 数据集（含数量差异解析）
    └── risawoz.md                 # RiSAWOZ 数据集
```

文档命名规范：使用小写字母，单词间用连字符 `-` 分隔，扩展名 `.md`。

---

## 🚀 快速链接

### 推荐入口

| 功能 | 说明 | 文档 | 示例脚本 |
|------|------|------|---------|
| ContextPipeline | 统一流水线（Phase 1+2） | [快速开始](quick-start.md) | `context_pipeline_demo.py` |
| KnowledgeBaseBuilder | 知识库构建（Phase 1） | [API 参考](api-reference.md) | `build_kb_demo.py` |

### 算法评测

| 算法 | 状态 | 数据集 | 文档 | 评测脚本 |
|------|------|--------|------|---------|
| DST | ✅ 已实现 | TransferTOD、RiSAWOZ | [文档](algorithms/dst.md) | `run_dst_transfertod.py` |
| FnCTOD | ✅ 已实现 | TransferTOD | [文档](algorithms/fnctod.md) | `run_fnctod_transfertod.py` |
| pyTOD | ✅ 已实现（评测⏳待完成） | SGD | [文档](algorithms/pytod.md) | — |
| Evolve | ✅ 已实现 | — | [文档](algorithms/evolve.md) | — |

### 数据集

| 数据集 | 语言 | 领域数 | 对话数 | 文档 |
|--------|------|--------|--------|------|
| SGD | 英文 | 16 | 22,825 | [文档](datasets/sgd.md) |
| TransferTOD | 中文 | 30 | ~9,013 | [文档](datasets/transfertod.md) |
| RiSAWOZ | 中文 | 12 | 11,200 | [文档](datasets/risawoz.md) |

### 常见任务

- [安装 ContextMind](quick-start.md#安装)
- [运行 DST 评测](algorithms/dst.md#运行评测)
- [运行 FnCTOD 评测](algorithms/fnctod.md#运行评测)
- [如何添加新场景](extending-scenarios.md)
- [如何自定义配置](configuration.md)

---

## 🔗 相关链接

- [主项目 README](../README.md)
- [GitHub 仓库](https://github.com/JasmineAIGC/ContextMind)
- [RiSAWOZ 数据集](https://github.com/terryqj0107/RiSAWOZ)
- [TransferTOD 数据集](https://github.com/KongLongGeFDU/TransferTOD)
- [SGD 数据集](https://github.com/google-research-datasets/dstc8-schema-guided-dialogue)
- [pyTOD 官方源码](https://github.com/apple/ml-pytod)

---

**最后更新**: 2026-03-30 | **版本**: 0.3.0
