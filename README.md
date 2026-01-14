# ContextMind v3.1

**专业的上下文优化框架** - 通用、可扩展、高鲁棒性的上下文工程模块，可接入任意对话系统。

[![Version](https://img.shields.io/badge/version-3.1.0-blue.svg)](https://github.com/Jasmine66Bloom/ContextMind)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## ✨ 核心特性

### v3.1 新特性 🚀

- 🔌 **通用适配器层**: 支持接入任意对话系统（OpenAI、LangChain、自定义等）
- 📊 **性能监控**: 全面的性能追踪和分析
- 🎨 **上下文可视化**: 多格式上下文展示（文本/JSON/Markdown）
- 🔔 **事件系统**: 发布-订阅模式实现组件解耦
- ⚙️ **配置管理**: 集中化配置加载和验证
- 🎣 **钩子机制**: 在关键流程点注入自定义逻辑

### v3.0 基础特性 ⭐

- 🏗️ **四层架构**: 清晰的层次分离（应用/引擎/流水线/策略）
- 🧠 **智能记忆**: 短期会话 + 长期记忆双重管理
- 🔄 **完整流水线**: 输入处理 → 收集 → 整合 → 优化 → 提取
- 🎯 **策略模式**: 10+ 可插拔策略实现
- 💪 **类型安全**: 全面的数据类和类型提示
- ⚡ **异步优先**: 全异步设计，高性能并发

---

## 🏛️ 架构设计

### 多层架构

```
┌─────────────────────────────────────────────┐
│          应用层 (Application Layer)          │
│    BaseApplication, CallCenterApp, etc.    │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│          适配器层 (Adapter Layer)  [v3.1]   │
│   OpenAI, LangChain, Custom Adapters       │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│           引擎层 (Engine Layer)              │
│            ContextEngine                    │
│  ┌───────────────────────────────────────┐  │
│  │   SessionManager  │  MemoryManager   │  │
│  └───────────────────────────────────────┘  │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│         流水线层 (Pipeline Layer)            │
│  Input → Collect → Integrate → Optimize    │
│              → Extract                      │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│          策略层 (Strategy Layer)             │
│  Retrieval │ Integration │ Optimization    │
│              │ Extraction                   │
└─────────────────────────────────────────────┘
                  │
        ┌─────────▼─────────┐
        │  工具层 (Utils)    │  [v3.1]
        │  Monitor │ Config │
        │  Visualizer │ Events │
        └───────────────────┘
```

### 核心组件

**引擎层 (ContextEngine)**
- `optimize()` - 优化上下文
- `update()` - 更新会话历史
- `extract_knowledge()` - 提取知识

**适配器层** (v3.1)
- `OpenAIAdapter` - OpenAI API 兼容
- `LangChainAdapter` - LangChain 框架集成
- `CustomAdapter` - 完全可定制

**流水线层**
- `InputProcessor` - 输入验证和清洗
- `ContextCollector` - 多源上下文收集
- `ContextIntegrator` - 去重和组织
- `ContextOptimizer` - 压缩和优化
- `KnowledgeExtractor` - 知识提取

**策略层**
- 检索策略: Keyword, Vector, Hybrid
- 整合策略: Simple, Priority
- 优化策略: Compression, Reranking
- 提取策略: RuleBased, LLM

**工具层** (v3.1)
- `ConfigManager` - 配置管理
- `PerformanceMonitor` - 性能监控
- `ContextVisualizer` - 上下文可视化
- `EventBus` - 事件系统

---

## 🚀 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/Jasmine66Bloom/ContextMind.git
cd ContextMind

# 安装依赖
pip install -r requirements.txt
```

### 基础使用

```python
from contextmind import ContextEngine, Client
from google.adk.memory import InMemoryMemoryService

# 创建引擎
client = Client()
engine = ContextEngine(
    app_name="my-app",
    user_id="user-123",
    llm_client=client,
    memory_service=InMemoryMemoryService()
)

# 优化上下文
context_result = await engine.optimize("你好")

# 更新会话
await engine.update(
    user_input="你好",
    assistant_response="你好！有什么可以帮助你的？"
)

# 提取知识
knowledge = await engine.extract_knowledge()
```

### 使用适配器 (v3.1)

```python
from contextmind import ContextEngine, OpenAIAdapter

# 创建引擎和适配器
engine = ContextEngine(app_name="chat", user_id="user-123")
adapter = OpenAIAdapter(engine=engine)

# 处理对话
response = await adapter.process(
    user_input="介绍一下 Python",
    context={"style": "简洁"}
)

print(response)
```

### 性能监控 (v3.1)

```python
from contextmind import PerformanceMonitor

# 创建监控器
monitor = PerformanceMonitor()

# 记录性能指标
with monitor.track("optimization"):
    context = await engine.optimize(user_input)

# 查看报告
summary = monitor.get_summary()
print(f"平均优化时间: {summary.avg_optimization_time:.2f}s")
```

---

## 📚 文档

- [**架构文档**](docs/ARCHITECTURE.md) - 详细的架构设计说明
- [**API 参考**](docs/API_REFERENCE.md) - 完整的 API 文档
- [**最佳实践**](docs/BEST_PRACTICES.md) - 使用建议和最佳实践
- [**v3.1 升级指南**](docs/UPGRADE_V3.1.md) - v3.1 新特性和升级说明

---

## 🎯 示例

### 交互式命令行演示

```bash
# 基础模式
python interactive_demo.py

# 禁用会话历史
python interactive_demo.py --no-session

# 启用长期记忆
python interactive_demo.py --use-memory

# 限制最大轮数
python interactive_demo.py --max-events 5
```

### Web 界面演示

```bash
python gradio_demo.py
```

通过 UI 控件实时配置：
- ✅ 会话历史开关
- ✅ 长期记忆开关
- ✅ 最大对话轮数

### 应用层示例

```python
from examples.applications import CallCenterApplication

# 创建客服应用
app = CallCenterApplication(
    context_engine=engine,
    llm_client=client,
    agent_name="小智",
    company_name="优质服务公司"
)

# 处理用户请求
response = await app.process_turn("我想查询订单状态")
```

---

## 🔧 扩展性

### 自定义策略

```python
from contextmind.strategies import RetrievalStrategy

class MyRetrievalStrategy(RetrievalStrategy):
    async def retrieve(self, query: str, **kwargs):
        # 实现自定义检索逻辑
        return results

# 使用自定义策略
engine.context_collector.retrieval_strategy = MyRetrievalStrategy()
```

### 自定义适配器

```python
from contextmind.adapters import CustomAdapter

adapter = CustomAdapter(
    engine=engine,
    message_converter=my_converter,
    response_formatter=my_formatter
)
```

### 钩子函数

```python
adapter = OpenAIAdapter(engine=engine)

# 添加钩子
adapter.register_hook(
    "before_optimize",
    lambda ctx: print(f"优化前: {ctx}")
)

adapter.register_hook(
    "after_generate",
    lambda response: logger.info(f"生成: {response}")
)
```

---

## 📊 项目结构

```
ContextMind/
├── contextmind/              # 核心框架
│   ├── __init__.py          # 包导出
│   ├── engine.py            # 上下文引擎
│   ├── data_models.py       # 数据模型
│   ├── client.py            # LLM 客户端
│   ├── logger.py            # 日志工具
│   │
│   ├── managers/            # 管理器
│   │   ├── session_manager.py
│   │   └── memory_manager.py
│   │
│   ├── pipeline/            # 流水线处理器
│   │   ├── input_processor.py
│   │   ├── context_collector.py
│   │   ├── context_integrator.py
│   │   ├── context_optimizer.py
│   │   └── knowledge_extractor.py
│   │
│   ├── strategies/          # 策略实现
│   │   ├── base.py
│   │   ├── retrieval.py
│   │   ├── integration.py
│   │   ├── optimization.py
│   │   └── extraction.py
│   │
│   ├── adapters/            # 适配器层 [v3.1]
│   │   ├── base.py
│   │   ├── openai_adapter.py
│   │   ├── langchain_adapter.py
│   │   └── custom_adapter.py
│   │
│   └── utils/               # 工具层 [v3.1]
│       ├── config.py
│       ├── monitor.py
│       ├── visualizer.py
│       └── events.py
│
├── examples/                # 示例代码
│   ├── applications/        # 应用层示例
│   │   ├── base.py
│   │   └── callcenter.py
│   └── adapter_integration_demo.py
│
├── docs/                    # 文档
│   ├── ARCHITECTURE.md
│   ├── API_REFERENCE.md
│   ├── BEST_PRACTICES.md
│   └── UPGRADE_V3.1.md
│
├── interactive_demo.py      # 命令行演示
├── gradio_demo.py          # Web 演示
├── requirements.txt        # 依赖
└── README.md              # 本文件
```

---

## 🎉 核心优势

### 1. 通用兼容性 🔌
通过适配器层，可无缝接入任意对话系统：
- OpenAI API
- LangChain 框架
- 自定义对话系统
- 企业内部系统

### 2. 高度模块化 🏗️
- 每个组件职责单一
- 接口清晰明确
- 易于测试和维护

### 3. 完全可扩展 🚀
- 策略模式支持自定义实现
- 钩子机制注入自定义逻辑
- 事件系统解耦组件

### 4. 类型安全 💪
- 全面的类型提示
- 数据类保证数据结构
- IDE 友好，减少错误

### 5. 可观测性 📊
- 性能监控和追踪
- 上下文可视化
- 详细的日志输出

### 6. 高鲁棒性 🛡️
- 完善的错误处理
- 优雅的降级策略
- 异步设计提升性能

---

## 📈 版本历史

### v3.1.0 (2026-01-14)
- ✨ 新增适配器层，支持接入任意对话系统
- ✨ 新增工具层（配置/监控/可视化/事件）
- ✨ 新增钩子机制和事件系统
- 📝 完善文档和示例

### v3.0.0 (2026-01-14)
- 🔥 完全重构，采用四层架构
- 🚀 简化 API，提供 3 个核心方法
- 💪 全面类型安全
- ⚡ 异步优先设计
- 📚 新增完整文档

### v2.0 及更早
- 基于 Pipeline 的单体架构（已废弃）

---

## 🤝 贡献

欢迎贡献代码、报告问题或提出建议！

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

---

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

---

## 🙏 致谢

- Google ADK - 提供会话和记忆服务基础
- 所有贡献者和使用者

---

## 📞 联系方式

- 作者: Jasmine66Bloom
- 项目地址: [https://github.com/Jasmine66Bloom/ContextMind](https://github.com/Jasmine66Bloom/ContextMind)
- 问题反馈: [Issues](https://github.com/Jasmine66Bloom/ContextMind/issues)

---

**ContextMind v3.1** - 让上下文优化变得简单而强大 ✨
