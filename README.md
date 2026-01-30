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
- **两种模式** - ContextMind 完整模式 / DST 基础模式

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

### 使用

#### ContextMind 完整模式

```python
from contextmind import ContextEngine
from utils import SimpleLLMClient

# 初始化
llm_client = SimpleLLMClient()
engine = ContextEngine(llm_client=llm_client)

# 对话
response = await engine.chat("你好")
print(response)
```

#### DST 基础模式

```python
from dst import DialogueStateTracker, PromptManager
from utils import SimpleLLMClient

# 初始化
llm_client = SimpleLLMClient()
pm = PromptManager(domain="restaurant")
tracker = DialogueStateTracker(llm_client=llm_client, prompt_manager=pm)

# 对话
state = await tracker.process_turn("你好", "我想订餐")
print(state)
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

### DST 基础演示
```bash
python dst_demo.py
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

| 特性 | DST 基础模式 | ContextMind 完整模式 |
|------|------------|-------------------|
| 技术 | ACL 2023 论文 | 五层架构上下文工程 |
| 复杂度 | ⭐ 简单 | ⭐⭐⭐⭐ 复杂 |
| 记忆 | ❌ 无 | ✅ 语义检索 |
| 适用 | Baseline 实验 | 生产环境 |

---

## 文档

- [架构说明](docs/ARCHITECTURE.md)
- [DST 文档](docs/BASIC_DST_DOCUMENTATION.md)
- [迁移指南](docs/MIGRATION.md)
- [更新日志](docs/CHANGELOG.md)

---

## 开源协议

MIT License
