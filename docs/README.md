# ContextMind 文档中心

## 📚 文档导航

### 入门

| 文档 | 说明 |
|------|------|
| [架构图](architecture.md) | 框架整体架构（Mermaid 图）、模块依赖、数据流、算法流程 |
| [快速开始](quick-start.md) | 安装、配置与第一个程序 |
| [配置指南](configuration.md) | 高级配置与扩展新场景 |
| [API 参考](api-reference.md) | 完整 API 文档 |
| [故障排查](troubleshooting.md) | 常见问题与解决方案 |

### 算法文档

| 算法 | 状态 | 所需步骤 | 论文 | 文档 |
|------|------|---------|------|------|
| DST | ✅ 已实现 | 第三步（第一步可选） | 对话状态追踪（通用技术，无单一论文） | [算法说明](algorithms/dst.md) |
| FnCTOD | ✅ 已实现 | 第三步（第一步可选） | [Large Language Models as Zero-shot Dialogue State Tracker through Function Calling](https://arxiv.org/pdf/2402.10466)（ACL 2024） | [算法说明](algorithms/fnctod.md) |
| PyTOD | ✅ 已实现 | 第三步（第一、二步可选） | [PyTOD: Programmable Task-Oriented Dialogue with Execution Feedback](https://arxiv.org/pdf/2508.15456) | [算法说明](algorithms/pytod.md) |
| Evolve | ✅ 已实现 | 仅第三步 | [ThetaEvolve: Test-time Learning on Open Problems](https://arxiv.org/pdf/2511.23473) | [算法说明](algorithms/evolve.md) |

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

## 🏗️ 三步核心框架

ContextMind 的整体设计围绕三个核心步骤，不同算法对各步骤的依赖各不相同：

| 步骤 | 模块 | 说明 |
|------|------|------|
| **① 建立知识库** | `contextmind.knowledge` | 任意数据集 → SGD `schema.json` |
| **② Schema 数据生成** | `contextmind.schema_builder` | `schema.json` → 算法专用数据（如 PyTOD API 代码） |
| **③ 算法执行** | `contextmind.modes.*` | 对话上下文提取与管理 |

### 算法步骤依赖矩阵

| 算法 | ① 建立知识库 | ② Schema 生成 | ③ 算法执行 |
|------|:-----------:|:------------:|:---------:|
| **DST** | ✅ 可选 | ❌ 不需要 | ✅ 必须 |
| **FnCTOD** | ✅ 可选 | ❌ 不需要 | ✅ 必须 |
| **PyTOD** | ✅ 可选 | ✅ 可选 | ✅ 必须 |
| **Evolve** | ❌ 不需要 | ❌ 不需要 | ✅ 必须 |

---

## 🗂️ 项目结构（概览）

```
ContextMind/
├── contextmind/          # 主包
│   ├── pipeline.py       # ContextPipeline（推荐入口）
│   ├── knowledge/        # ① KnowledgeBaseBuilder（第一步）
│   ├── schema_builder/   # ② SchemaDataBuilder（第二步，API代码生成）
│   ├── modes/            # ③ DST / FnCTOD / PyTOD / Evolve 追踪器（第三步）
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

**最后更新**: 2026-03-31 | **版本**: 0.3.0
