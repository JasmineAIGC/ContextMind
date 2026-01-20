# ContextMind

**ContextMind v6.0** - 通用上下文工程框架 ✨

**v6.0 新特性**: 增强的可观测性 + 完整的记忆生命周期 + 模块化日志追踪

### v6.0 主要改进

1. **增强的日志系统**
   - 模块前缀标识：`[MemoryBank]`, `[Retriever]`, `[ContextEngine]`, `[Extractor]`, `[Prompt]`
   - 阶段分隔符：清晰展示优化流程各个阶段
   - 状态指示器：✓ 成功 / ✗ 失败，一目了然
   - 详细的记忆追踪：记忆库内容、检索结果、相关性分数

2. **完整的记忆生命周期**
   - 知识提取：从对话中提取偏好、事实、事件
   - 记忆存储：自动去重，智能存储
   - 记忆检索：带相关性评分的智能检索
   - 全程可见：每个阶段都有详细日志

3. **改进的可观测性**
   - DEBUG 模式显示完整 Prompt
   - 记忆库状态实时可见
   - 检索过程透明化
   - 上下文优化全程追踪

---

## 📖 项目简介

**ContextMind 是一个独立的、可嵌入的上下文工程框架**，专为 LLM 对话系统设计。它解决了对话系统中的三大核心挑战：

1. **上下文窗口限制** - LLM 有 token 限制（4K/8K/32K）
2. **信息过载** - 不是所有历史都相关，需要智能筛选
3. **多源整合** - 统一管理会话历史、长期记忆、外部知识

### 核心价值

```
用户问题 → [ContextMind 上下文优化] → 精准上下文 → LLM → 高质量回复
```

- 🎯 **精准优化**：从海量历史中提取最相关的上下文
- ⚡ **高性能**：Token 精确计数 + 智能缓存，5-400x 性能提升
- 🔌 **易集成**：独立模块，可嵌入任何对话系统
- 📦 **开箱即用**：提供 OpenAI、LangChain 等适配器

---

## 📂 项目结构

```
ContextMind/
├── contextmind/              # 🔥 核心模块 - 五层清晰架构
│   ├── __init__.py           # 框架入口
│   ├── engine.py             # ContextEngine - 统一接口
│   ├── client.py             # LLM 客户端
│   ├── data_models.py        # 数据模型
│   ├── logger.py             # 日志系统
│   │
│   ├── core/                 # 核心层 - 基础数据结构与服务
│   │   ├── tokenizer.py      # Token 计数服务
│   │   ├── cache.py          # 缓存管理
│   │   ├── vector_client.py  # 向量数据库接口
│   │   └── session_manager.py # 会话管理
│   │
│   ├── pipeline/             # 流水线层 - 上下文处理流程
│   │   ├── preprocessor.py   # 输入预处理
│   │   ├── retriever.py      # 上下文检索
│   │   ├── integrator.py     # 上下文整合
│   │   ├── compressor.py     # 上下文压缩
│   │   ├── reorderer.py      # 上下文重排序
│   │   └── extractor.py      # 知识提取
│   │
│   ├── strategies/           # 策略层 - 可插拔算法
│   │   ├── base.py           # 策略基类
│   │   ├── retrieval.py      # 检索策略
│   │   ├── integration.py    # 整合策略
│   │   ├── optimization.py   # 优化策略
│   │   └── extraction.py     # 提取策略
│   │
│   ├── adapters/             # 适配器层 - 系统集成
│   │   ├── base.py           # 基础适配器
│   │   ├── openai_adapter.py # OpenAI 适配器
│   │   └── langchain_adapter.py # LangChain 适配器
│   │
│   └── utils/                # 工具层 - 辅助功能
│       ├── config.py         # 配置管理
│       ├── monitor.py        # 性能监控
│       ├── context_formatter.py # 格式化工具
│       └── text_builder.py   # 文本构建工具
│
├── examples/                 # 📚 示例应用
│   ├── applications/         # 应用层示例
│   │   ├── base.py           # BaseApplication - 应用基类
│   │   └── callcenter.py     # 客服应用示例
│   └── adapter_integration_demo.py  # 适配器集成示例
│
├── tests/                    # ✅ 测试
│   └── test_core.py          # 核心功能测试（23个测试用例）
│
├── docs/                     # 📖 文档
│   ├── DESIGN_PHILOSOPHY.md  # 设计哲学与架构思想 ⭐
│   ├── ARCHITECTURE.md       # 架构详解
│   ├── API_REFERENCE.md      # API 参考
│   ├── BEST_PRACTICES.md     # 最佳实践
│   ├── FOUNDATION_LAYER.md   # 基础层详解
│   ├── CONTEXT_FLOW_DETAILED.md  # 上下文流程详解
│   └── LOG_ANALYSIS_GUIDE.md     # 日志分析指南
│
├── data/                     # 📁 示例数据
│   ├── callcenter_dialog.txt    # 客服对话示例
│   └── memory_seeds.txt          # 记忆种子数据
│
├── gradio_demo.py            # 🎨 Web UI 演示（Gradio）
├── interactive_demo.py       # 💬 命令行交互演示
├── run.sh                    # 🚀 快速启动脚本
├── requirements.txt          # 📦 依赖列表
├── pytest.ini                # ⚙️ 测试配置
└── README.md                 # 📋 本文件

```

### 核心模块说明

#### `contextmind/` - 独立的上下文工程框架

这是项目的核心，**可以作为独立 Python 包使用**，嵌入到任何对话系统中。

**五层架构 (v6.0)**：
1. **核心层** (`core/`) - 基础数据结构与服务（Token计数、缓存、向量、会话）
2. **流水线层** (`pipeline/`) - 上下文处理流程（预处理、检索、整合、压缩、重排序、提取）
3. **策略层** (`strategies/`) - 可插拔的算法实现（检索、整合、优化、提取策略）
4. **适配器层** (`adapters/`) - 系统集成接口（OpenAI、LangChain等）
5. **工具层** (`utils/`) - 辅助功能（配置、监控、格式化）

**核心文件**：
- `engine.py`: `ContextEngine` 类 - 主要入口点
- `data_models.py`: 所有数据模型定义
- `client.py`: LLM 客户端（支持 OpenAI 兼容 API）
- `logger.py`: 日志系统

#### `examples/` - 示例应用

展示如何使用 ContextMind 构建应用：
- `applications/base.py`: 应用基类，定义标准对话处理模式
- `applications/callcenter.py`: 客服系统示例

#### `tests/` - 测试

- 23 个测试用例，覆盖核心功能
- 包含数据模型、Pipeline、Foundation、Agent Memory System 测试

#### 根目录文件

- `gradio_demo.py`: Web UI 演示（687 行）
- `interactive_demo.py`: 命令行交互演示（205 行）
- `run.sh`: 快速启动脚本

---

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件：

```bash
# API Key（必需）
QWEN3_API_KEY=your-api-key

# 模型配置（可选）
QWEN3_MODEL=Qwen3-32B
QWEN3_BASE_URL=https://api.example.com
QWEN3_TEMPERATURE=0.6
QWEN3_MAX_TOKENS=8192
```

### 3. 基本使用

```python
import asyncio
from contextmind.core import ContextEngine, Client, ClientConfig

async def main():
    # 初始化客户端
    client = Client(config=ClientConfig.from_env())
    
    # 初始化引擎
    engine = ContextEngine(
        app_name="my-app",
        user_id="user-123",
        llm_client=client,
    )
    
    # 优化上下文
    context_result = await engine.optimize("你好")
    
    # 查看优化后的上下文
    print(f"近期对话: {len(context_result.recent_history)} 条")
    print(f"长期记忆: {len(context_result.long_term_memory)} 条")
    
    # 更新会话
    await engine.update(
        user_input="你好",
        assistant_response="你好，有什么可以帮助你的？"
    )

asyncio.run(main())
```

### 4. 运行演示

```bash
# 命令行交互式演示
python interactive_demo.py

# Gradio Web UI 演示
python gradio_demo.py

# 或使用快速启动脚本
./run.sh
```

---

## 🎯 核心特性

### 1. 多源上下文整合

- **会话历史** (Session History): 短期对话历史
- **长期记忆** (Long-term Memory): 跨会话的用户信息和偏好
- **外部知识** (External Knowledge): 领域知识库（可扩展）

### 2. 智能上下文优化

- ✅ **去重** - 移除重复内容
- ✅ **排序** - 按相关性和时间排序
- ✅ **压缩** - Token 级别的精确截断
- ✅ **提炼** - 自动提取实体、偏好、状态
- ✅ **分离** - 会话历史与长期记忆分别限制

### 3. 精准 Token 管理

- 使用官方 tokenizer（tiktoken）
- 精确 Token 计数（误差 <1%）
- Token 级别截断，杜绝上下文溢出

**对比**：
| 方法 | 准确率 | 溢出风险 |
|------|--------|---------|
| 字符估算 | ±40% | 高 ❌ |
| TokenizerService | <1% | 无 ✅ |

### 4. 高性能缓存

- LRU 缓存策略 + TTL 自动过期
- 多层缓存（Embedding、检索、摘要）
- 5-400x 性能提升

### 5. 可插拔策略

四类策略，支持自定义：
- **RetrievalStrategy** - 检索策略
- **IntegrationStrategy** - 整合策略
- **OptimizationStrategy** - 优化策略
- **ExtractionStrategy** - 提取策略

---

## 📚 文档

### 核心文档（必读）
- [📐 设计哲学与架构思想](docs/DESIGN_PHILOSOPHY.md) ⭐ 
- [🏗️ 架构文档](docs/ARCHITECTURE.md)
- [📚 API 参考](docs/API_REFERENCE.md)
- [✨ 最佳实践](docs/BEST_PRACTICES.md)

### 专题文档
- [🔧 基础层详解](docs/FOUNDATION_LAYER.md)
- [🔍 日志分析指南](docs/LOG_ANALYSIS_GUIDE.md)
- [📊 上下文流程详解](docs/CONTEXT_FLOW_DETAILED.md)

---

## 🏗️ 架构设计

### 五层架构 (v6.0)

```
┌─────────────────────────────────────────┐
│         核心层 (Core)                    │  ← contextmind/core/
│    Token计数 | 缓存 | 向量 | 会话       │
└─────────────────────────────────────────┘
                 ↑
┌─────────────────────────────────────────┐
│       流水线层 (Pipeline)                │  ← contextmind/pipeline/
│    预处理 → 检索 → 整合 →                │
│    压缩 → 重排序 → 提取                  │
└─────────────────────────────────────────┘
                 ↑
┌─────────────────────────────────────────┐
│       策略层 (Strategies)                │  ← contextmind/strategies/
│    可插拔算法实现                        │
└─────────────────────────────────────────┘
                 ↑
┌─────────────────────────────────────────┐
│      适配器层 (Adapters)                 │  ← contextmind/adapters/
│    OpenAI | LangChain | Custom         │
└─────────────────────────────────────────┘
                 ↑
┌─────────────────────────────────────────┐
│        工具层 (Utils)                    │  ← contextmind/utils/
│    配置 | 监控 | 格式化                  │
└─────────────────────────────────────────┘
```

### 设计原则

1. **模块化** - 每个组件职责单一，可独立替换
2. **分层设计** - 清晰的层次结构，向上依赖
3. **委托模式** - Pipeline 委托给 Strategy，避免重复
4. **数据驱动** - 强类型数据模型
5. **异步优先** - 全面使用 async/await
6. **代码复用** - 组合优于继承

---

## 🔌 集成示例

### 使用 OpenAI 适配器

```python
from contextmind.core import ContextEngine, Client
from contextmind.adapters import OpenAIAdapter

# 初始化
engine = ContextEngine(app_name="my-app", user_id="user-123")
client = Client(config=ClientConfig.from_env())
adapter = OpenAIAdapter(engine=engine)

# 处理对话
response = await adapter.process("你好", context=None)
print(response.content)
```

### 使用 LangChain 适配器

```python
from contextmind.adapters import LangChainAdapter

adapter = LangChainAdapter(engine=engine)
response = await adapter.process("你好", context=None)
```

### 自定义策略

```python
from contextmind.strategies import IntegrationStrategy

class MyStrategy(IntegrationStrategy):
    async def integrate(self, context):
        # 自定义整合逻辑
        return context

# 使用自定义策略
from contextmind.pipeline import ContextIntegrator
integrator = ContextIntegrator(strategy=MyStrategy())
```

---

## ✅ 测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行特定测试
python -m pytest tests/test_core.py::TestDataModels -v
```

测试覆盖：
- ✅ 数据模型（8 个测试）
- ✅ Pipeline 组件（4 个测试）
- ✅ Foundation 服务（5 个测试）
- ✅ Agent Memory System（6 个测试）

---

## 📊 性能

### Token 计数准确性

| 方法 | 英文误差 | 中文误差 | 溢出风险 |
|------|---------|---------|---------|
| 字符估算 | ±20% | ±40% | 高 ❌ |
| TokenizerService | <1% | <1% | 无 ✅ |

### 缓存性能提升

| 场景 | 无缓存 | 有缓存 | 提升 |
|------|--------|--------|------|
| Embedding 计算 | 500ms | 5ms | 100x ✅ |
| 向量检索 | 100ms | 10ms | 10x ✅ |
| LLM 摘要 | 2000ms | 5ms | 400x ✅ |

---

## 🎨 项目状态

- ✅ **代码质量**: 无重复代码，单一真实来源
- ✅ **测试覆盖**: 23/23 测试通过
- ✅ **安全验证**: CodeQL 0 告警
- ✅ **文档完善**: 完整的设计文档和 API 参考
- ✅ **架构清晰**: 六层架构，职责分离

---

## 📈 版本历史

- **v6.0** (当前) - 增强的可观测性：模块化日志、完整记忆生命周期、透明的上下文追踪
- **v5.2** - 代码质量提升 + 结构优化 + 完全通用化（零场景硬编码）
- **v5.1** - 五层架构重构：core/pipeline/strategies/adapters/utils 清晰分层
- **v4.0** - 架构优化版：消除代码冗余（~240行），统一文本格式化，完善文档
- **v3.2** - 新增 Foundation Layer、Control Layer、增强数据模型
- **v3.1** - 重构引擎层，优化 API 设计
- **v3.0** - 完全重构，引入六层架构

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

在提交 PR 前，请确保：
- ✅ 所有测试通过
- ✅ 代码符合项目风格
- ✅ 添加必要的文档

---

## 📄 许可证

MIT License

---

## 🔗 相关链接

- 设计文档: [DESIGN_PHILOSOPHY.md](docs/DESIGN_PHILOSOPHY.md)
- 架构详解: [ARCHITECTURE.md](docs/ARCHITECTURE.md)
- API 参考: [API_REFERENCE.md](docs/API_REFERENCE.md)
- 最佳实践: [BEST_PRACTICES.md](docs/BEST_PRACTICES.md)

---

**ContextMind** - 让上下文优化变得简单而强大 ✨
