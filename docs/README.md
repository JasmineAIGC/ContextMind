# ContextMind 文档中心

## 📚 文档导航

### 入门

| 文档 | 说明 |
|------|------|
| [快速开始](quick-start.md) | 安装、配置与第一个程序 |
| [配置指南](configuration.md) | 高级配置与扩展新场景 |
| [API 参考](api-reference.md) | 完整 API 文档 |
| [故障排查](troubleshooting.md) | 常见问题与解决方案 |

### 算法文档

| 算法 | 状态 | 文档 |
|------|------|------|
| DST | ✅ 已实现 | [算法说明](algorithms/dst.md) |
| FnCTOD | ✅ 已实现 | [算法说明](algorithms/fnctod.md) |
| PyTOD | ✅ 已实现 | [算法说明](algorithms/pytod.md) |
| Evolve | ✅ 已实现 | [算法说明](algorithms/evolve.md) |

### 评测与数据集

| 文档 | 说明 |
|------|------|
| [Benchmark 评测框架](benchmark.md) | 评测运行、指标说明与意图评测 |
| [数据集说明](datasets/datasets.md) | SGD / TransferTOD / RiSAWOZ |

### 开发

| 文档 | 说明 |
|------|------|
| [贡献指南](CONTRIBUTING.md) | 如何参与贡献 |
| [更新日志](changelog.md) | 版本变更历史 |

---

## 🗂️ 项目结构（概览）

```
ContextMind/
├── contextmind/          # 主包
│   ├── pipeline.py       # ContextPipeline（推荐入口）
│   ├── knowledge/        # KnowledgeBaseBuilder（Phase 1）
│   ├── schema_builder/   # SchemaDataBuilder（API代码生成）
│   ├── modes/            # DST / FnCTOD / PyTOD / Evolve 追踪器
│   ├── infra/            # AdkLLMClient、配置
│   └── scenarios/        # 场景注册与配置
├── benchmark/            # 评测框架（DST / FnCTOD / RiSAWOZ / TransferTOD）
├── examples/             # 示例脚本
├── resources/            # 静态资源与测试数据
└── docs/                 # 文档（本目录）
```

---

## 🚀 快速链接

- **ContextPipeline 快速上手** → [quick-start.md](quick-start.md)
- **运行 DST 评测** → [algorithms/dst.md](algorithms/dst.md#运行评测)
- **运行 FnCTOD 评测** → [algorithms/fnctod.md](algorithms/fnctod.md#运行评测)
- **添加新场景** → [configuration.md](configuration.md#扩展新场景)

---

**最后更新**: 2026-03-30 | **版本**: 0.3.0
