# ContextMind v0.4.1

一个通用、可扩展、易集成的上下文工程框架，专为基于大语言模型的对话系统设计。

v0.4.1 版本**直接使用 Google ADK-Python**，两个模式各自独立使用 ADK Agent。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-0.4.1-green.svg)](https://github.com/Jasmine66Bloom/ContextMind)

---

## 🎯 v0.4.1 架构

### 两个独立模式

#### 1. **DST 模式** (`dst/`)
- **ADK 负责**: Agent 框架、LLM 调用
- **自研部分**: 槽位提取、Prompt 工程、状态追踪算法
- **特点**: 简单、高效、专注于对话状态

#### 2. **ContextMind 模式** (`contextmind/`)
- **ADK 负责**: Agent 框架、LLM 调用
- **自研部分**: Pipeline 算法、记忆库、记忆进化系统
- **特点**: 复杂、智能、专注于上下文工程

### 核心原则

**直接使用 ADK**：
- ✅ 无中间封装层
- ✅ 直接使用 `google.adk.agents.Agent`
- ✅ 直接使用 `google.adk.models.lite_llm.LiteLlm`
- ✅ 各模式独立实现专用 Agent

**保留自研核心**：
- ✅ DST 的槽位提取和状态追踪算法
- ✅ ContextMind 的上下文工程 Pipeline
- ✅ ContextMind 的记忆进化系统

---

编辑 `.env` 文件：

```ini
# 选项 1: 使用 Google Gemini (推荐)
GOOGLE_API_KEY=your-google-api-key-here
MODEL=gemini-2.0-flash-exp

# 选项 2: 使用 OpenAI
# OPENAI_API_KEY=your-openai-key
# MODEL=openai/gpt-4

# 选项 3: 使用 Anthropic Claude
# ANTHROPIC_API_KEY=your-anthropic-key
# MODEL=anthropic/claude-3-sonnet
```

### 运行Demo

#### Interactive Demo（命令行）

```bash
# 闲聊场景 + ContextMind模式
python interactive_demo.py --scenario chat --mode contextmind

# 客服场景 + DST模式
python interactive_demo.py --scenario callcenter --mode dst

# 保险场景 + ContextMind模式
python interactive_demo.py --scenario insurance --mode contextmind
```

#### Gradio Demo（Web界面）

```bash
# 启动Web界面
python gradio_demo.py

# 在浏览器中访问 http://localhost:7860
# 可在界面中选择场景（chat/callcenter/insurance）和模式（ContextMind/DST）
```

### API使用

#### ContextMind 模式（基于记忆进化）

```python
from contextmind import ContextEngine
from contextmind.adk_integration import ADKLLMClient

# 初始化 - 使用 ADK LLM 客户端
llm_client = ADKLLMClient()
engine = ContextEngine(
    app_name="my_app",
    user_id="user_123",
    llm_client=llm_client
)

# 对话 - 系统会记住上下文并不断优化
response = await engine.chat("你好")
print(response)
```

#### DST 模式（对话状态追踪）

```python
from dst import DialogueStateTracker, PromptManager
from utils import SimpleLLMClient

# 初始化 - 专注于槽位提取
llm_client = SimpleLLMClient()
pm = PromptManager(domain="restaurant")
tracker = DialogueStateTracker(llm_client=llm_client, prompt_manager=pm)

# 对话 - 提取意图和槽位
state = await tracker.process_turn("你好", "我想订餐")
print(state)  # 返回提取的状态信息
```

---

## 演示程序

### 闲聊场景
```bash
python chat_interactive_demo.py --mode contextmind  # 完整模式
python chat_interactive_demo.py --mode basic        # DST 模式
python chat_gradio_demo.py                          # Web UI
```

### 客服场景
```bash
python callcenter_interactive_demo.py --mode contextmind
python callcenter_interactive_demo.py --mode basic
python callcenter_gradio_demo.py                    # Web UI
```

### 保险场景（共荣保险）
```bash
python insurance_interactive_demo.py --mode contextmind
python insurance_interactive_demo.py --mode basic   # 使用预定义意图和槽位
python insurance_gradio_demo.py                     # Web UI
```

---

## 场景配置系统

ContextMind v0.4.0 支持通过配置文件轻松切换不同的对话任务：

### 支持的场景

| 场景 | 配置文件 | 说明 |
|------|---------|------|
| 闲聊 | `scenarios/chat_scenario.py` | 动态槽位，开放意图 |
| 客服 | `scenarios/callcenter_scenario.py` | 问题追踪，工单管理 |
| 保险 | `scenarios/insurance_scenario.py` | 共荣保险，预定义意图和槽位 |

### 使用配置

```python
from scenarios import get_insurance_scenario, get_chat_scenario, get_callcenter_scenario

# 获取场景配置
config = get_insurance_scenario()

# DST 模式（使用预定义意图和槽位）
from dst import DialogueStateTracker, PromptManager

pm = PromptManager(
    domain=config.scenario_name,
    enable_dynamic_slots=False  # 使用预定义槽位
)

# 添加预定义槽位
for slot_name, slot_desc in config.dst_slots.items():
    pm.add_slot(slot_name, slot_desc)

# ContextMind 模式
from contextmind import ContextEngine

engine = ContextEngine(
    system_prompt=config.system_prompt,
    enable_memory=config.enable_memory
)
```

### 添加新场景

1. 在 `scenarios/` 创建新配置文件
2. 在 `prompts.py` 添加系统提示词
3. 创建对应的 demo 文件
4. 在 `scenarios/__init__.py` 导出

详见：[场景配置文档](docs/SCENARIO_CONFIGURATION.md)

---

## 项目结构

```
ContextMind/ v0.4.0
├── contextmind/              # ContextMind 完整框架（五层架构）
├── dst/                      # DST 基础实现（ACL 2023 论文）
├── scenarios/                # 场景配置系统 ✨
│   ├── config.py            # 配置基类
│   ├── chat_scenario.py     # 闲聊场景
│   ├── callcenter_scenario.py  # 客服场景
│   └── insurance_scenario.py   # 保险场景（共荣保险）
├── utils/                    # 通用工具（logger, LLM client）
├── examples/                 # 应用示例
│   ├── chat_app.py
│   ├── callcenter_app.py
│   └── insurance_app.py
├── docs/                     # 文档
├── prompts.py                # 系统提示词（3个主要场景）
└── *_demo.py                 # 演示程序
```

---

## 两种模式对比

| 特性 | DST 模式 | ContextMind 模式 |
|------|---------|-----------------|
| 方法论 | 对话状态追踪 (Dialogue State Tracking) | 基于记忆进化的对话系统 |
| 技术基础 | ACL 2023 论文，槽位-值提取 | 五层架构，语义记忆+进化学习 |
| 核心能力 | 意图识别、槽位提取、状态追踪 | 上下文理解、记忆管理、自主进化 |
| 记忆系统 | ❌ 无持久记忆 | ✅ 语义记忆库 + 进化学习 |
| 学习能力 | ❌ 无学习 | ✅ 从对话中持续学习优化 |
| 适用场景 | 结构化任务（订票、客服） | 开放域对话、个性化交互 |
| 复杂度 | ⭐⭐ 轻量 | ⭐⭐⭐⭐ 完整 |

---

## 文档

- [架构说明](docs/ARCHITECTURE.md)
- [DST 文档](docs/BASIC_DST_DOCUMENTATION.md)
- [迁移指南](docs/MIGRATION.md)
- [更新日志](docs/CHANGELOG.md)

---

## 开源协议

MIT License
