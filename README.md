# ContextMind v0.4.0

一个通用、可扩展、易集成的上下文工程框架，专为基于大语言模型的对话系统设计。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-0.4.0-green.svg)](https://github.com/Jasmine66Bloom/ContextMind)

---

## 核心特性

- **模型无关** - 适配任何 LLM 提供商
- **五步流水线** - 预处理、检索、压缩、重排序、响应处理
- **智能记忆** - 自动知识提取和语义检索
- **两种模式** - ContextMind 进化模式 / DST 状态追踪模式

---

## 快速开始

### 安装

```bash
pip install -r requirements.txt
```

### 配置

创建 `.env` 文件：

```bash
QWEN3_API_KEY=your_api_key
QWEN3_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN3_MODEL=qwen-plus
```

### 运行Demo

#### Interactive Demo（命令行）

```bash
# 闲聊场景 + ContextMind模式
python interactive_demo.py --scenario chat --mode contextmind

# 客服场景 + DST模式
python interactive_demo.py --scenario callcenter --mode basic

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
from utils import SimpleLLMClient

# 初始化 - 支持记忆和进化学习
llm_client = SimpleLLMClient()
engine = ContextEngine(
    llm_client=llm_client,
    enable_memory=True,      # 启用语义记忆
    enable_evolution=True     # 启用进化学习
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
