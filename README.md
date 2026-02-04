# ContextMind

一个通用、可扩展、易集成的上下文工程框架，专为基于大语言模型的对话系统设计。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-0.2.1-green.svg)](https://github.com/Jasmine66Bloom/ContextMind)

---

## 核心特性

- **模型无关** - 适配任何 LLM 提供商
- **五步流水线** - 预处理、检索、压缩、重排序、响应处理
- **智能记忆** - 自动知识提取和语义检索
- **三种模式** - Evolve 进化模式 / DST 状态追踪模式 / FnCTOD 函数调用模式

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
# 闲聊场景 + Evolve模式
python interactive_demo.py --scenario chat --mode evolve

# 客服场景 + DST模式
python interactive_demo.py --scenario callcenter --mode dst

# 保险场景 + FnCTOD模式（函数调用）
python interactive_demo.py --scenario insurance --mode fnctod
```

#### Gradio Demo（Web界面）

```bash
# 启动Web界面
python gradio_demo.py

# 在浏览器中访问 http://localhost:7860
# 可在界面中选择场景（chat/callcenter/insurance）和模式（Evolve/DST/FnCTOD）
```

---

## API使用

### Evolve 模式（基于记忆进化）

```python
from evolve import EvolveEngine
from utils import SimpleLLMClient

# 初始化 - 支持记忆和进化学习
llm_client = SimpleLLMClient()
engine = EvolveEngine(
    llm_client=llm_client,
    enable_memory=True,      # 启用语义记忆
    enable_evolution=True     # 启用进化学习
)

# 对话 - 系统会记住上下文并不断优化
response = await engine.chat("你好")
print(response)
```

### DST 模式（对话状态追踪）

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

### FnCTOD 模式（函数调用DST）

```python
from fnctod import get_function_schema_for_scenario, FunctionManager, FnCTODTracker
from utils import SimpleLLMClient

# 初始化 - 使用预定义Schema
llm_client = SimpleLLMClient()
schema = get_function_schema_for_scenario("闲聊")
function_manager = FunctionManager()
function_manager.add_domain(schema)

tracker = FnCTODTracker(
    llm_client=llm_client,
    function_manager=function_manager,
    use_two_stage=True  # 启用两阶段处理
)

# 对话 - 返回function call和自然语言回复
result = await tracker.process_turn(user_utterance="你好")
print(result)  # {"state": {...}, "response": "...", "function_call": {...}}
```

---

## 项目结构

```
ContextMind/
├── evolve/                   # Evolve 框架（五层架构）
│   ├── core/                # 核心数据模型和配置
│   ├── memory/              # 记忆系统（提取、存储、检索）
│   ├── evolution/           # 进化学习系统
│   └── pipeline/            # 五步处理流水线
├── dst/                      # DST 基础实现（ACL 2023）
│   ├── dialogue_state_tracker.py
│   ├── prompt_manager.py
│   └── response_parser.py
├── fnctod/                   # FnCTOD 函数调用实现
│   ├── fnctod_tracker.py    # 主追踪器（两阶段处理）
│   ├── function_manager.py  # 函数管理器
│   ├── response_parser.py   # 响应解析器
│   ├── schemas.py           # 预定义函数Schema
│   └── data_models.py       # 数据模型
├── scenarios/                # 场景配置系统
│   ├── chat_scenario.py     # 闲聊场景
│   ├── callcenter_scenario.py  # 客服场景
│   └── insurance_scenario.py   # 保险场景
├── apps/                     # 应用示例
│   ├── chat_app.py
│   ├── callcenter_app.py
│   └── insurance_app.py
├── utils/                    # 通用工具
│   ├── logger.py
│   ├── llm_client.py
│   └── embedding.py
├── docs/                     # 文档
├── interactive_demo.py       # 命令行演示
└── gradio_demo.py           # Web界面演示
```

---

## 三种模式对比

| 特性 | DST 模式 | Evolve 模式 | FnCTOD 模式 |
|------|---------|-------------|-------------|
| 方法论 | 对话状态追踪 | 基于记忆进化 | 函数调用DST |
| 技术基础 | ACL 2023 DST | 五层架构 | FnCTOD论文 |
| 记忆系统 | ❌ 无 | ✅ 完整 | ❌ 无 |
| 学习能力 | ❌ 无 | ✅ 持续学习 | ❌ 无 |
| 处理模式 | 单阶段 | 多层流水线 | 两阶段 |
| 输出格式 | JSON状态 | 自然回复 | Function call + 回复 |
| Schema | 动态或预定义 | 无 | 预定义Schema |
| 适用场景 | 结构化任务 | 开放对话 | API集成+任务对话 |
| 标准兼容 | 自定义 | 自定义 | OpenAI兼容 |

详细对比请查看 [模式对比文档](docs/modes.md)。
| 技术基础 | ACL 2023 论文 | 五层架构 + 语义记忆 |
| 核心能力 | 意图识别、槽位提取 | 上下文理解、记忆管理、自主进化 |
| 记忆系统 | ❌ 无持久记忆 | ✅ 语义记忆库 + 进化学习 |
| 学习能力 | ❌ 无学习 | ✅ 持续学习优化 |
| 适用场景 | 结构化任务（订票、客服） | 开放域对话、个性化交互 |
| 复杂度 | ⭐⭐ 轻量 | ⭐⭐⭐⭐ 完整 |

---

## 场景配置

ContextMind 支持通过配置文件轻松切换不同的对话任务：

| 场景 | 配置文件 | 说明 |
|------|---------|------|
| 闲聊 | `scenarios/chat_scenario.py` | 动态槽位，开放意图 |
| 客服 | `scenarios/callcenter_scenario.py` | 问题追踪，工单管理 |
| 保险 | `scenarios/insurance_scenario.py` | 预定义意图和槽位 |

### 使用场景配置

```python
from scenarios import get_insurance_scenario

# 获取场景配置
config = get_insurance_scenario()

# DST 模式 - 使用预定义槽位
from dst import DialogueStateTracker, PromptManager

pm = PromptManager(domain=config.scenario_name)
for slot_name, slot_desc in config.dst_slots.items():
    pm.add_slot(slot_name, slot_desc)

# Evolve 模式 - 使用系统提示词
from evolve import EvolveEngine

engine = EvolveEngine(
    system_prompt=config.system_prompt,
    enable_memory=config.enable_memory
)
```

---

## 文档

- [快速开始](docs/quick-start.md) - 详细安装和使用指南
- [架构说明](docs/architecture.md) - 系统架构设计
- [模式对比](docs/modes.md) - DST vs Evolve 详细对比
- [配置指南](docs/configuration.md) - 高级配置选项
- [迁移指南](docs/migration.md) - 版本升级指南
- [更新日志](docs/changelog.md) - 版本变更历史

---

## 开源协议

MIT License
