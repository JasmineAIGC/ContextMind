# ContextMind v0.4.1

**通用、可扩展、易集成的上下文工程框架**

基于 [google-adk](https://github.com/google/adk-python) 的 Agent 层，专注于对话系统的上下文工程实现。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-0.4.1-green.svg)](https://github.com/Jasmine66Bloom/ContextMind)

---

## 🎯 核心特性

### 1. 基于 ADK-Python 的 Agent 层

- ✅ **底层 Agent**: 完全基于 `google.adk.agents.Agent`
- ✅ **LLM 调用**: 通过 `google.adk.models.openai.OpenAI`
- ✅ **无重复造轮子**: 充分利用 ADK 的成熟能力

### 2. 自研上下文工程

- ✅ **专注领域**: ADK 不提供上下文工程功能，我们自研实现
- ✅ **两种模式**: DST（对话状态追踪）和 Evolution（记忆进化）
- ✅ **核心算法**: Pipeline、槽位提取、状态追踪、记忆进化

### 3. 通用框架设计

- ✅ **可扩展**: 灵活的场景配置系统
- ✅ **易集成**: 标准化接口，易于集成到现有系统
- ✅ **多场景**: 支持闲聊、客服、保险等多种应用场景

---

## 📊 架构层次

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
└── OpenAI (配置为 Qwen API - OpenAI 兼容接口)
```

**详细架构**: 查看 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## 🚀 两种上下文工程模式

### DST 模式 (`dst/`)

**对话状态追踪** - 基于 ACL 2023 论文

- **ADK 负责**: Agent 框架、LLM 调用
- **自研实现**: 槽位提取算法、Prompt 工程、状态追踪
- **适用场景**: 结构化任务（订票、客服）
- **特点**: 轻量、高效

### Evolution 模式 (`evolution/`)

**基于进化的记忆优化** - 完整的上下文工程方案

- **ADK 负责**: Agent 框架、LLM 调用
- **自研实现**: Pipeline 算法、记忆库、记忆进化系统
- **适用场景**: 开放域对话、个性化交互
- **特点**: 完整、智能

---

## ⚡ 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

**核心依赖**:
- `google-adk>=1.23.0` - ADK Agent 框架
- `openai>=1.0.0` - OpenAI SDK（Qwen 兼容）

### 2. 配置

编辑 `.env` 文件：

```ini
# LLM 配置（Qwen API - OpenAI 兼容接口）
QWEN3_API_KEY=your-api-key
QWEN3_BASE_URL=http://your-endpoint/v1
QWEN3_MODEL=Qwen2.5-7B-Instruct

# Embedding 配置（用于记忆检索，不是 LLM）
EMBEDDING_MODEL_PATH=/path/to/bge-large-zh-v1.5
EMBEDDING_MODEL=bge-large-zh-v1.5
```

详细配置说明: [docs/configuration.md](docs/configuration.md)

### 3. 运行示例

#### Web UI（Gradio）

```bash
python gradio_demo.py
# 访问 http://localhost:7860
# 界面中选择场景（chat/callcenter/insurance）和模式（Evolution/DST）
```

#### 命令行（Interactive）

```bash
# Evolution 模式 + 闲聊场景
python interactive_demo.py --scenario chat --mode evolution

# DST 模式 + 客服场景
python interactive_demo.py --scenario callcenter --mode dst

# Evolution 模式 + 保险场景
python interactive_demo.py --scenario insurance --mode evolution
```

---

## 💻 API 使用

### Evolution 模式示例

```python
from evolution import EvolutionAgent, EvolutionEngine

# 1. 创建 Evolution Agent（基于 google-adk）
agent = EvolutionAgent()

# 2. 创建引擎
engine = EvolutionEngine(
    app_name="my_app",
    user_id="user_123",
    llm_client=agent
)

# 3. 优化上下文
context = await engine.optimize("你好，我想了解保险产品")
print(f"优化后的上下文: {context}")

# 4. 生成回复
response = await agent.generate_async("基于上下文生成回复")
```

### DST 模式示例

```python
from dst import DSTAgent, DialogueStateTracker

# 1. 创建 DST Agent（基于 google-adk）
agent = DSTAgent()

# 2. 创建状态追踪器
tracker = DialogueStateTracker(llm_client=agent)

# 3. 追踪对话状态
state = await tracker.track_turn(
    system_utterance="您好，有什么可以帮您的？",
    user_utterance="我想订明天去北京的机票"
)

# 4. 查看提取的槽位
print(f"意图: {state.get('intent')}")
print(f"槽位: {state.get('slots')}")
```

---

## 📖 文档

### 核心文档

- **[架构说明](docs/ARCHITECTURE.md)** - 详细的框架架构和设计原则
- **[快速开始](docs/quick-start.md)** - 5分钟快速上手
- **[配置指南](docs/configuration.md)** - 详细的配置说明
- **[模式对比](docs/modes.md)** - DST 和 Evolution 两种模式的详细对比

### 专题文档

- **[DST 论文实现](docs/paper-DST.md)** - ACL 2023 论文的实现细节
- **[DST 优化](docs/dst-optimizations.md)** - DST 模式的优化技巧

完整文档索引: [docs/README.md](docs/README.md)

---

## 🏗️ 项目结构

```
ContextMind/ v0.4.1
├── dst/                    # DST 模式（对话状态追踪）
│   ├── adk_agent.py       # DST Agent（基于 google-adk）
│   ├── dialogue_state_tracker.py  # 状态追踪核心
│   ├── prompt_manager.py  # Prompt 工程
│   └── response_parser.py # 响应解析
│
├── evolution/             # Evolution 模式（记忆进化）
│   ├── agent.py          # Evolution Agent（基于 google-adk）
│   ├── engine.py         # Evolution 引擎
│   ├── pipeline/         # 上下文工程 Pipeline
│   ├── memory/           # 记忆管理系统
│   └── evolution/        # 进化系统
│
├── scenarios/            # 场景配置
│   ├── chat_scenario.py      # 闲聊
│   ├── callcenter_scenario.py # 客服
│   └── insurance_scenario.py  # 保险
│
├── apps/                 # 应用层
│   ├── chat_app.py
│   ├── callcenter_app.py
│   └── insurance_app.py
│
├── utils/                # 工具
│   ├── adk_config.py    # ADK 配置
│   ├── logger.py        # 日志
│   └── embedding.py     # Embedding
│
├── docs/                 # 文档
├── gradio_demo.py       # Web UI
├── interactive_demo.py  # CLI
└── requirements.txt     # 依赖
```

---

## 🌟 核心价值

### 为什么选择 ContextMind？

1. **专业的上下文工程**
   - 不只是简单的对话管理
   - 提供专业的上下文理解、管理和优化
   - 两种模式覆盖不同需求场景

2. **基于成熟框架**
   - 底层 Agent 基于 google-adk
   - 避免重复造轮子
   - 专注于上下文工程本身

3. **通用性和可扩展性**
   - 场景配置系统，轻松适配新场景
   - 标准化接口，易于集成
   - 可切换不同的 LLM

4. **生产就绪**
   - 完整的错误处理
   - 详细的日志系统
   - 经过实际项目验证

---

## 📝 许可证

MIT License

---

## 🤝 贡献

欢迎贡献！请查看贡献指南。

---

**版本**: v0.4.1  
**核心**: 基于 ADK-Python 的上下文工程框架  
**定位**: 通用、可扩展、易集成
