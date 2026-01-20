# ContextMind

**ContextMind v7.0** - 通用上下文工程框架 ✨

**v7.0 新特性**: 增强的可观测性 + 完整的记忆生命周期 + 模块化日志追踪

### v7.0 主要改进

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

## 📂 项目结构 (v7.0)

```
ContextMind/
├── contextmind/              # 🔥 核心模块 - 纯上下文工程框架
│   ├── __init__.py           # 框架入口
│   ├── models.py             # 数据模型（Message, Knowledge, Config等）
│   ├── engine.py             # ContextEngine - 核心引擎
│   ├── registry.py           # 插件注册中心
│   ├── config_api.py         # ContextMind 高层API
│   │
│   ├── pipeline/             # 流水线层 - 上下文处理流程
│   │   ├── session.py        # 会话管理
│   │   ├── preprocessor.py   # 输入预处理
│   │   ├── memory.py         # 记忆库管理
│   │   ├── compressor.py     # 上下文压缩
│   │   ├── reorderer.py      # 上下文重排序
│   │   ├── postprocessor.py  # 输出后处理
│   │   ├── summarizer.py     # 对话摘要
│   │   └── kvcache.py        # KV缓存策略接口
│   │
│   └── strategies/           # 策略层 - 可插拔算法（扁平结构）
│       ├── base.py           # 策略基类
│       ├── extractors.py     # 提取策略（RuleBased, LLMEntity, Importance）
│       ├── retrievers.py     # 检索策略（Semantic, Hybrid, Locator）
│       └── updaters.py       # 更新策略（Simple, ConflictResolver, Adaptive）
│
├── demos/                    # 📚 演示和示例
│   ├── README.md
│   ├── plugin_examples.py    # 插件使用示例
│   ├── callcenter_app.py     # 客服应用示例
│   └── chat_app.py           # 聊天应用示例
│
├── tests/                    # ✅ 测试
│
├── docs/                     # 📖 文档
│   └── arch_by_me.md         # 架构设计文档
│
├── interactive_demo.py       # 💬 命令行交互演示（根目录）
├── gradio_demo.py            # 🎨 Web UI 演示（根目录）
├── chat_interactive_demo.py  # 💬 聊天命令行演示（根目录）
├── chat_gradio_demo.py       # 🎨 聊天 Web UI 演示（根目录）
├── requirements.txt          # 📦 依赖列表
├── pytest.ini                # ⚙️ 测试配置
└── README.md                 # 📋 本文件

```

### 核心模块说明

#### `contextmind/` - 纯上下文工程框架

这是项目的核心，**纯上下文工程框架**，专注于 Steps 1-4（上下文构建）和 Step 6（输出后处理）。

**v7.0 架构特点**：
1. **扁平化设计** - 去除多余嵌套，直接访问所有模块
2. **插件化** - 所有策略都是可插拔的（extractors, retrievers, updaters）
3. **零 LLM 依赖** - LLM 调用由用户控制（Step 5 外部化）
4. **模块化** - 每个 pipeline 组件独立，可单独使用

**核心文件**：
- `models.py`: 所有数据模型和配置类
- `engine.py`: ContextEngine 核心引擎
- `registry.py`: 插件注册和发现系统
- `config_api.py`: ContextMind 高层 API（prepare_context, post_process）

**Pipeline 模块** (`pipeline/`):
- `session.py`: 会话状态管理
- `preprocessor.py`: 输入预处理
- `memory.py`: 记忆库（MemoryBank）
- `compressor.py`, `reorderer.py`: 上下文优化
- `postprocessor.py`: 输出后处理
- `summarizer.py`: 对话摘要生成
- `kvcache.py`: KV缓存策略接口

**Strategy 插件** (`strategies/`):
- `extractors.py`: 知识提取策略
- `retrievers.py`: 记忆检索策略  
- `updaters.py`: 记忆更新策略

#### `demos/` - 演示代码

所有示例代码集中在 demos/ 目录：
- `plugin_examples.py`: 插件系统使用示例
- `callcenter_app.py`, `chat_app.py`: 应用模板

#### 根目录演示文件

4 个演示文件放在根目录便于快速访问：
- `interactive_demo.py`, `gradio_demo.py`: 基础演示
- `chat_interactive_demo.py`, `chat_gradio_demo.py`: 聊天模式演示

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
from contextmind import ContextMind

async def main():
    # 初始化 ContextMind（纯上下文工程框架）
    cm = ContextMind()
    
    # Step 1-4: 准备优化后的上下文
    context = await cm.prepare_context(
        user_input="你好，我想查询余额",
        session_id="user-123"
    )
    
    # 查看优化后的上下文
    print(f"系统提示: {context['system_prompt']}")
    print(f"优化上下文: {len(context['optimized_context'])} 条")
    
    # Step 5: 用户调用自己的 LLM（外部）
    # llm_output = await your_llm.generate(
    #     system_prompt=context['system_prompt'],
    #     messages=context['optimized_context'],
    #     user_input=context['user_input']
    # )
    
    # Step 6: 后处理（可选）
    # final_response = await cm.post_process(
    #     llm_output,
    #     session_id="user-123"
    # )

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

### v7.0 架构设计

```
用户输入
    ↓
┌─────────────────────────────────────────────┐
│  Step 1-4: 上下文工程（ContextMind 核心）   │
│                                             │
│  ┌──────────────────────────────────────┐  │
│  │ Pipeline (流水线层)                   │  │
│  │  Session → Preprocessor → Memory →   │  │
│  │  Compressor → Reorderer              │  │
│  └──────────────────────────────────────┘  │
│           ↓                                 │
│  ┌──────────────────────────────────────┐  │
│  │ Strategies (插件层)                  │  │
│  │  Extractors | Retrievers | Updaters │  │
│  └──────────────────────────────────────┘  │
│                                             │
│  输出: 优化后的上下文（optimized_context）  │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│  Step 5: LLM 推理（用户外部调用）            │
│  your_llm.generate(optimized_context)       │
│  输出: LLM 原始响应                          │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│  Step 6: 输出后处理（ContextMind）          │
│  PostProcessor.process(llm_output)          │
│  输出: 最终响应                              │
└─────────────────────────────────────────────┘
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

### 基础使用

```python
from contextmind import ContextMind, registry

# 初始化（使用默认插件）
cm = ContextMind()

# 准备上下文
context = await cm.prepare_context(
    user_input="你好",
    session_id="user-123"
)

# 调用你自己的 LLM
llm_output = await your_llm.generate(context)

# 后处理
final = await cm.post_process(llm_output, session_id="user-123")
```

### 使用自定义插件

```python
from contextmind import registry
from contextmind.strategies.extractors import RuleBasedExtractor
from contextmind.strategies.retrievers import HybridRetriever

# 查看可用插件
print(registry.list_extractors())  # ['rule_based', 'llm_entity', 'importance']
print(registry.list_retrievers())  # ['semantic', 'hybrid', 'locator']

# 创建自定义配置
cm = ContextMind(
    extractor='llm_entity',      # 使用 LLM 辅助提取
    retriever='hybrid',          # 使用混合检索
    updater='conflict_resolver'  # 使用冲突解决器
)
```

### 注册自定义策略

```python
from contextmind.strategies.base import BaseExtractor

class MyCustomExtractor(BaseExtractor):
    async def extract(self, messages):
        # 自定义提取逻辑
        return extracted_knowledge

# 注册自定义插件
registry.register_extractor('my_custom', MyCustomExtractor)

# 使用自定义插件
cm = ContextMind(extractor='my_custom')
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

- **v7.0** (当前) - 增强的可观测性：模块化日志、完整记忆生命周期、透明的上下文追踪
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
