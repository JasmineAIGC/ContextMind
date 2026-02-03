# ContextMind 架构说明

ContextMind v0.4.1 - 基于 ADK-Python 的上下文工程框架

---

## 框架定位

**ContextMind** 是一个**通用、可扩展、易集成的上下文工程框架**，专为基于大语言模型的对话系统设计。

### 核心特性

1. **底层基于 adk-python**
   - Agent 框架完全基于 `google.adk.agents.Agent`
   - LLM 调用通过 `google.adk.models.openai.OpenAI`
   - 充分利用 ADK 的成熟能力

2. **自研上下文工程**
   - ADK 不提供上下文工程功能
   - 我们在 ADK Agent 基础上实现上下文工程
   - 专注于对话上下文的理解、管理和优化

3. **两种工程模式**
   - **DST 模式**: 对话状态追踪（Dialogue State Tracking）
   - **Evolution 模式**: 基于进化的记忆优化

4. **通用框架设计**
   - 可扩展的场景配置系统
   - 易于集成到现有对话系统
   - 支持多种应用场景（闲聊、客服、保险等）

---

## 架构层次

```
┌─────────────────────────────────────────────────────┐
│          应用层 (Applications)                       │
│  ├── gradio_demo.py  (Web UI)                       │
│  ├── interactive_demo.py  (CLI)                     │
│  └── apps/  (chat, callcenter, insurance)           │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│       上下文工程层 (Context Engineering)             │
│  ┌─────────────┐          ┌────────────────┐        │
│  │  DST 模式   │          │ Evolution 模式  │        │
│  ├─────────────┤          ├────────────────┤        │
│  │ 槽位提取    │          │ Pipeline 算法   │        │
│  │ 状态追踪    │          │ 记忆库管理      │        │
│  │ Prompt 工程 │          │ 记忆进化系统    │        │
│  └─────────────┘          └────────────────┘        │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│          Agent 层 (基于 google-adk)                  │
│  ├── DSTAgent (google.adk.agents.Agent)             │
│  └── EvolutionAgent (google.adk.agents.Agent)       │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│         LLM 层 (google.adk.models)                   │
│  └── OpenAI (配置为 Qwen API - OpenAI 兼容接口)      │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│              Qwen API                                │
└─────────────────────────────────────────────────────┘
```

---

## 层次职责

### 1. 应用层 (Applications)

**职责**: 提供用户交互界面和应用逻辑

**组件**:
- `gradio_demo.py` - Web UI 演示
- `interactive_demo.py` - 命令行演示
- `apps/` - 不同场景的应用实现
  - `chat_app.py` - 闲聊应用
  - `callcenter_app.py` - 客服应用
  - `insurance_app.py` - 保险应用

**特点**:
- 场景特定的业务逻辑
- 用户输入/输出处理
- 调用上下文工程层

### 2. 上下文工程层 (Context Engineering)

**职责**: 核心的上下文理解、管理和优化

#### DST 模式 (`dst/`)

**职责**: 对话状态追踪和槽位提取

**自研组件**:
- `dialogue_state_tracker.py` - 状态追踪核心
- `prompt_manager.py` - Prompt 工程
- `response_parser.py` - 响应解析
- 槽位提取算法
- 状态管理逻辑

**特点**:
- 基于 ACL 2023 论文实现
- 适合结构化任务（订票、客服）
- 轻量、高效

#### Evolution 模式 (`evolution/`)

**职责**: 基于进化的上下文优化和记忆管理

**自研组件**:
- `engine.py` - Evolution 引擎
- `pipeline/` - 上下文工程 Pipeline
  - `preprocessor.py` - 预处理
  - `compressor.py` - 压缩
  - `reorderer.py` - 重排序
  - `summarizer.py` - 摘要
- `memory/` - 记忆管理
  - `bank.py` - 记忆库
  - `session.py` - 会话管理
  - `memory_fitness.py` - 记忆适应度
- `evolution/` - 进化系统
  - `evolutionary_updater.py` - 进化更新
  - `feedback_system.py` - 反馈系统

**特点**:
- 五层 Pipeline 架构
- 语义记忆库
- 自主进化学习
- 适合开放域对话和个性化交互

### 3. Agent 层 (基于 google-adk)

**职责**: 提供标准化的 Agent 接口

**组件**:
- `dst/adk_agent.py` - DST 专用 Agent
- `evolution/agent.py` - Evolution 专用 Agent
- `utils/adk_config.py` - ADK 配置

**实现**:
```python
from google.adk import agents
from google.adk.models.openai import OpenAI

# 创建 OpenAI 模型（配置为 Qwen API）
model = OpenAI(
    model="Qwen2.5-7B-Instruct",
    api_key=os.getenv("QWEN3_API_KEY"),
    base_url=os.getenv("QWEN3_BASE_URL")  # Qwen API endpoint
)

# 创建 ADK Agent
agent = agents.Agent(
    model=model,
    name="contextmind_agent"
)
```

**特点**:
- 完全基于 google.adk.agents.Agent
- 无自定义封装层
- 通过配置使用不同的 LLM（当前使用 Qwen）

### 4. LLM 层 (google.adk.models)

**职责**: LLM 模型调用

**实现**:
- 使用 `google.adk.models.openai.OpenAI`
- 配置 `base_url` 指向 Qwen API
- Qwen API 是 OpenAI 兼容接口

**特点**:
- ADK 处理所有 LLM 通信细节
- 支持同步和异步调用
- 可轻松切换到其他 OpenAI 兼容模型

---

## 设计原则

### 1. 职责分离

**ADK 负责**:
- ✅ Agent 框架和生命周期管理
- ✅ LLM 模型调用和管理
- ✅ 底层通信和错误处理

**ContextMind 负责**:
- ✅ 上下文工程算法
- ✅ 对话状态管理
- ✅ 记忆系统和进化
- ✅ 场景特定的业务逻辑

### 2. 最小化本地实现

**原则**: 尽量直接使用 ADK 已有的能力，无需本地实现

**当前状态**:
- ✅ Agent 框架 - 直接使用 google.adk.agents.Agent
- ✅ LLM 调用 - 直接使用 google.adk.models
- ✅ 错误处理 - 使用 ADK 的错误处理
- ✅ 本地实现仅限于 ADK 不提供的上下文工程功能

### 3. 可扩展性

**场景扩展**:
- 通过 `scenarios/` 配置系统添加新场景
- 无需修改核心框架代码

**模式扩展**:
- 可以添加新的上下文工程模式
- 基于相同的 ADK Agent 层

**模型扩展**:
- 可以切换到任何 OpenAI 兼容的 LLM
- 只需修改配置，无需改代码

---

## 两种模式对比

| 维度 | DST 模式 | Evolution 模式 |
|------|---------|----------------|
| **定位** | 对话状态追踪 | 上下文工程完整方案 |
| **技术基础** | ACL 2023 论文 | 五层 Pipeline + 记忆进化 |
| **ADK 使用** | google.adk.agents.Agent | google.adk.agents.Agent |
| **自研部分** | 槽位提取、状态追踪、Prompt 工程 | Pipeline 算法、记忆库、进化系统 |
| **记忆系统** | ❌ 无持久记忆 | ✅ 语义记忆库 + 进化学习 |
| **学习能力** | ❌ 无学习 | ✅ 从对话中持续学习 |
| **适用场景** | 结构化任务 | 开放域对话、个性化交互 |
| **复杂度** | ⭐⭐ 轻量 | ⭐⭐⭐⭐ 完整 |

---

## 数据流示例

### DST 模式

```
用户输入
    ↓
应用层 (gradio_demo/interactive_demo)
    ↓
DialogueStateTracker.process_turn()
    ├── PromptManager.build_prompt() [自研]
    ├── DSTAgent.chat_async() [ADK]
    │   └── google.adk.agents.Agent
    │       └── google.adk.models.openai.OpenAI
    │           └── Qwen API
    └── ResponseParser.parse() [自研]
    ↓
槽位更新 + 状态追踪 [自研]
    ↓
返回结果
```

### Evolution 模式

```
用户输入
    ↓
应用层 (gradio_demo/interactive_demo)
    ↓
EvolutionEngine.optimize() [自研]
    ├── SessionManager [自研]
    ├── MemoryBank [自研]
    └── Pipeline [自研]
        ├── preprocessor
        ├── compressor
        ├── reorderer
        └── summarizer
    ↓
ContextResult [自研]
    ↓
App.build_prompt() [自研]
    ↓
EvolutionAgent.generate_async() [ADK]
    └── google.adk.agents.Agent
        └── google.adk.models.openai.OpenAI
            └── Qwen API
    ↓
EvolutionEngine.update() [自研]
    ├── SessionManager.add_message()
    └── extract_knowledge() + 记忆进化 [自研]
    ↓
返回结果
```

---

## 配置管理

### 环境变量 (.env)

```ini
# Qwen LLM 配置
QWEN3_API_KEY=sk-xxx
QWEN3_BASE_URL=http://your-endpoint/v1
QWEN3_MODEL=Qwen2.5-7B-Instruct
QWEN3_MAX_TOKENS=8192

# Embedding 配置（记忆检索）
EMBEDDING_MODEL_PATH=/path/to/bge-large-zh-v1.5
EMBEDDING_MODEL=bge-large-zh-v1.5
```

### ADK 配置 (utils/adk_config.py)

```python
from google.adk.models.openai import OpenAI

def create_qwen_model(config=None):
    """创建配置为 Qwen API 的 ADK OpenAI 模型"""
    config = config or QwenADKConfig.from_env()
    
    return OpenAI(
        model=config.model,
        api_key=config.api_key,
        base_url=config.base_url  # 关键：指向 Qwen API
    )
```

---

## 扩展指南

### 添加新场景

1. 在 `scenarios/` 创建场景配置文件
2. 定义系统提示词、槽位、意图等
3. 在 `scenarios/__init__.py` 导出
4. 在应用层使用新场景配置

### 添加新的上下文工程模式

1. 在项目根目录创建新模式目录
2. 实现模式特定的上下文工程算法
3. 创建专用的 ADK Agent（基于 google.adk.agents.Agent）
4. 在应用层集成新模式

### 切换到其他 LLM

1. 如果是 OpenAI 兼容接口：
   - 修改 .env 中的 `base_url` 和 `model`
   
2. 如果是 Gemini：
   - 使用 `google.adk.models.Gemini`
   - 修改 `adk_config.py` 中的模型创建逻辑

---

## 总结

ContextMind 是一个：
- ✅ **基于 adk-python** 的上下文工程框架
- ✅ **专注于上下文工程** 的自研实现
- ✅ **通用、可扩展、易集成** 的框架设计
- ✅ 支持 **两种上下文工程模式**（DST 和 Evolution）
- ✅ **充分利用 ADK** 的成熟能力，避免重复造轮子

**核心价值**: 在 ADK 提供的稳定 Agent 基础上，实现专业的上下文工程能力。

---

**版本**: v0.4.1  
**更新日期**: 2026-02-03
