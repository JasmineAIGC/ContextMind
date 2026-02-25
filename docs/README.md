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
- [意图评测](intent-evaluation.md) - 意图识别评测使用指南
- [上下文工程](context-engineering.md) - DST 和 FnCTOD 评测对上下文工程的意义

### 数据集文档

- [RiSAWOZ 数据集](datasets/risawoz.md) - RiSAWOZ 数据集文件与目录结构说明
- [TransferTOD 数据集](datasets/transfertod.md) - TransferTOD 数据集文件与目录结构说明
- [对话数量差异说明](datasets/dialogue-count.md) - DST 与 FnCTOD 评测对话数量不同的原因

### 开发指南

- [API 参考](api-reference.md) - 完整的 API 文档
- [扩展场景](extending-scenarios.md) - 添加新场景的指南
- [贡献指南](CONTRIBUTING.md) - 如何参与贡献

### 帮助和支持

- [故障排查](troubleshooting.md) - 常见问题和解决方案
- [更新日志](changelog.md) - 版本变更历史

---

## 🚀 快速链接

### 新手入门

1. [安装 ContextMind](quick-start.md#安装)
2. [配置 API Key](quick-start.md#配置)
3. [运行第一个示例](quick-start.md#第一个示例)
4. [理解三种模式](modes.md)

### 常见任务

- [如何使用 DST 模式](api-reference.md#dst-模式-api)
- [如何使用 FnCTOD 模式](api-reference.md#fnctod-模式-api)
- [如何使用 Evolve 模式](api-reference.md#evolve-模式-api)
- [如何添加新场景](extending-scenarios.md)
- [如何自定义配置](configuration.md)
- [如何评测 RiSAWOZ 数据集](datasets/risawoz.md#在-contextmind-中使用)
- [如何评测 TransferTOD 数据集](datasets/transfertod.md#在-contextmind-中使用)

### 遇到问题？

1. 查看 [故障排查指南](troubleshooting.md)
2. 搜索 [GitHub Issues](https://github.com/Jasmine66Bloom/ContextMind/issues)
3. 提交新的 Issue

---

## 🎯 学习路径

### 初级用户

1. 阅读 [快速开始](quick-start.md)
2. 运行 [示例代码](examples.md)
3. 理解 [三种模式](modes.md)
4. 查看 [API参考](api-reference.md)

### 中级用户

1. 学习 [配置指南](configuration.md)
2. 探索更多 [示例代码](examples.md)
3. 了解 [目录结构](directory-structure.md)
4. 尝试 [扩展场景](extending-scenarios.md)

### 高级用户

1. 深入研究 [目录结构](directory-structure.md)
2. 学习 [评测指标](metrics-explanation.md)
3. 查看数据集文档（[RiSAWOZ](datasets/risawoz.md) / [TransferTOD](datasets/transfertod.md)）
4. 贡献代码（参考 [贡献指南](CONTRIBUTING.md)）

---

## 📂 文档结构

```
docs/
├── README.md                  # 文档索引（本文件）
├── quick-start.md             # 快速开始
├── examples.md                # 示例代码
├── directory-structure.md     # 项目目录结构
├── modes.md                   # 三种对话模式对比
├── configuration.md           # 配置指南
├── api-reference.md           # API 参考
├── metrics-explanation.md     # 评测指标说明
├── intent-evaluation.md       # 意图评测指南
├── context-engineering.md     # 上下文工程意义
├── extending-scenarios.md     # 扩展场景
├── troubleshooting.md         # 故障排查
├── changelog.md               # 更新日志
├── CONTRIBUTING.md            # 贡献指南
└── datasets/                  # 数据集文档
    ├── risawoz.md             # RiSAWOZ 数据集说明
    ├── transfertod.md         # TransferTOD 数据集说明
    └── dialogue-count.md      # 对话数量差异说明
```

文档命名规范：使用小写字母，单词间用连字符 `-` 分隔，扩展名 `.md`。

---

## 🔗 相关链接

- [主项目 README](../README.md)
- [GitHub 仓库](https://github.com/Jasmine66Bloom/ContextMind)
- [问题追踪](https://github.com/Jasmine66Bloom/ContextMind/issues)
- [RiSAWOZ 数据集](https://github.com/terryqj0107/RiSAWOZ)
- [TransferTOD 数据集](https://github.com/KongLongGeFDU/TransferTOD)

---

## 📝 贡献文档

如果你想贡献文档，请：
1. 在 `docs/` 目录下创建或修改 markdown 文件
2. 遵循命名规范（kebab-case）
3. 更新本 README.md 的文档导航
4. 提交 Pull Request

详见 [贡献指南](CONTRIBUTING.md)。

---

## 💡 提示

- 所有代码示例都经过验证，可以直接运行
- 文档中的路径都是相对于项目根目录
- 使用 Ctrl+F 快速查找内容
- 建议按照学习路径循序渐进

---

**最后更新**: 2026-02-25 | **版本**: 0.2.1
