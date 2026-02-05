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
- **可安装包** - 支持 pip 安装，模块化设计

---

## 快速开始

### 安装

```bash
# 安装依赖
pip install -r requirements.txt

# 或作为包安装
pip install -e .
```

### 配置

创建 `.env` 文件：

```bash
QWEN3_API_KEY=your_api_key
QWEN3_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN3_MODEL=qwen-plus
```

### 运行示例

#### CLI Demo（命令行）

```bash
# 闲聊场景 + Evolve模式
python examples/cli_demo.py --scenario chat --mode evolve

# 客服场景 + DST模式
python examples/cli_demo.py --scenario callcenter --mode dst

# 保险场景 + FnCTOD模式（函数调用）
python examples/cli_demo.py --scenario insurance --mode fnctod
```

#### Web Demo（Web界面）

```bash
# 启动Web界面
python examples/web_demo.py

# 在浏览器中访问 http://localhost:7860
# 可在界面中选择场景（chat/callcenter/insurance）和模式（Evolve/DST/FnCTOD）
```

---

## API使用

### Evolve 模式（基于记忆进化）

```python
from contextmind.modes.evolve import EvolveEngine, create_app_for_scenario
from contextmind.infra.llm_client import SimpleLLMClient
from contextmind.scenarios import get_chat_scenario

# 方式1: 使用工厂方法（推荐）
llm_client = SimpleLLMClient()
config = get_chat_scenario()
app = create_app_for_scenario("chat", llm_client, config)

# 对话 - 系统会记住上下文并不断优化
response = await app.process_turn("你好")
print(response)

# 方式2: 直接使用引擎
engine = EvolveEngine(
    app_name="my_app",
    user_id="user123",
    llm_client=llm_client,
    enable_memory=True,      # 启用语义记忆
    enable_evolution=True     # 启用进化学习
)
```

### DST 模式（对话状态追踪）

```python
from contextmind.modes.dst import DialogueStateTracker
from contextmind.infra.llm_client import SimpleLLMClient
from contextmind.scenarios import get_callcenter_scenario

# 使用工厂方法（推荐）
llm_client = SimpleLLMClient()
config = get_callcenter_scenario()
tracker = DialogueStateTracker.from_scenario(
    llm_client=llm_client,
    scenario_config=config
)

# 对话 - 提取意图和槽位
await tracker.process_turn("我想投诉")
state = tracker.get_state()
print(state)  # 返回提取的状态信息
```

### FnCTOD 模式（函数调用DST）

```python
from contextmind.modes.fnctod import FnCTODTracker
from contextmind.infra.llm_client import SimpleLLMClient
from contextmind.scenarios import get_insurance_scenario

# 使用工厂方法（推荐）
llm_client = SimpleLLMClient()
config = get_insurance_scenario()
tracker = FnCTODTracker.from_scenario(
    llm_client=llm_client,
    scenario_config=config,
    use_two_stage=True  # 启用两阶段处理
)

# 对话 - 返回function call和自然语言回复
result = await tracker.process_turn("我想了解保险")
print(result)  # {"state": {...}, "response": "...", "function_call": {...}}
```

---

## 项目结构

```
ContextMind/
├── contextmind/              # 主包（可安装）
│   ├── __init__.py           # 包入口
│   │
│   ├── infra/                # 基础设施层
│   │   ├── logger.py         # 日志工具
│   │   ├── llm_client.py     # LLM客户端
│   │   ├── embedding.py      # 向量嵌入
│   │   └── data_models.py    # 通用数据模型
│   │
│   ├── config/               # 配置层
│   │   ├── registry.py       # 场景注册表
│   │   ├── scenarios.yaml    # 场景配置文件
│   │   └── prompts.py        # 系统提示词
│   │
│   ├── ui/                   # UI层
│   │   └── components.py     # Gradio UI组件
│   │
│   ├── modes/                # 对话处理模式
│   │   ├── dst/              # 对话状态追踪
│   │   │   ├── dialogue_state_tracker.py
│   │   │   ├── prompt_manager.py
│   │   │   └── response_parser.py
│   │   │
│   │   ├── fnctod/           # 函数调用模式
│   │   │   ├── fnctod_tracker.py
│   │   │   ├── function_manager.py
│   │   │   ├── response_parser.py
│   │   │   └── schemas.py
│   │   │
│   │   └── evolve/           # 演化式上下文
│   │       ├── engine.py
│   │       ├── core/         # 核心组件
│   │       ├── memory/       # 记忆系统
│   │       ├── evolution/    # 进化学习
│   │       └── pipeline/     # 五步流水线
│   │
│   ├── scenarios/            # 场景配置
│   │   ├── chat_scenario.py
│   │   ├── callcenter_scenario.py
│   │   └── insurance_scenario.py
│   │
│   └── apps/                 # 应用实现
│       ├── chat_app.py
│       ├── callcenter_app.py
│       └── insurance_app.py
│
├── examples/                 # 示例程序
│   ├── cli_demo.py           # 命令行示例
│   ├── web_demo.py           # Web界面示例
│   └── batch_demo.py         # 批量测试示例
│
├── tests/                    # 测试
├── docs/                     # 文档
├── resources/                # 静态资源
├── setup.py                  # 安装配置
└── README.md                 # 项目说明
```

详细架构说明请查看 [ARCHITECTURE.md](ARCHITECTURE.md)。

---

## 三种模式对比

| 特性 | DST 模式 | FnCTOD 模式 | Evolve 模式 |
|------|---------|-------------|-------------|
| 方法论 | 对话状态追踪 | 函数调用DST | 基于记忆进化 |
| 技术基础 | ACL 2023 DST | FnCTOD论文 | 五层架构 |
| 记忆系统 | ❌ 无 | ❌ 无 | ✅ 完整 |
| 学习能力 | ❌ 无 | ❌ 无 | ✅ 持续学习 |
| 处理模式 | 单阶段 | 两阶段 | 多层流水线 |
| 输出格式 | JSON状态 | Function call + 回复 | 自然回复 |
| Schema | 动态或预定义 | 预定义Schema | 无 |
| 适用场景 | 结构化任务 | API集成+任务对话 | 开放对话 |
| 标准兼容 | 自定义 | OpenAI兼容 | 自定义 |

详细对比请查看 [模式对比文档](docs/modes.md)。

---

## 场景配置

ContextMind 支持通过配置文件轻松切换不同的对话任务：

| 场景 | 配置文件 | 说明 |
|------|---------|------|
| 闲聊 | `contextmind/scenarios/chat_scenario.py` | 动态槽位，开放意图 |
| 客服 | `contextmind/scenarios/callcenter_scenario.py` | 问题追踪，工单管理 |
| 保险 | `contextmind/scenarios/insurance_scenario.py` | 预定义意图和槽位 |

### 使用场景配置

```python
from contextmind.scenarios import get_insurance_scenario
from contextmind.modes.dst import DialogueStateTracker
from contextmind.modes.evolve import create_app_for_scenario
from contextmind.infra.llm_client import SimpleLLMClient

# 获取场景配置
config = get_insurance_scenario()
llm_client = SimpleLLMClient()

# DST 模式 - 使用工厂方法
tracker = DialogueStateTracker.from_scenario(
    llm_client=llm_client,
    scenario_config=config
)

# Evolve 模式 - 使用工厂方法
app = create_app_for_scenario("insurance", llm_client, config)
```

更多配置选项请查看 [配置指南](docs/configuration.md)。

---

## 文档

- [快速开始](docs/quick-start.md) - 详细安装和使用指南
- [架构说明](docs/architecture.md) - 系统架构设计
- [模式对比](docs/modes.md) - 三种模式详细对比
- [配置指南](docs/configuration.md) - 高级配置选项
- [扩展场景](docs/extending-scenarios.md) - 添加新场景指南
- [命名规范](docs/naming-standards.md) - 代码命名标准
- [迁移指南](docs/migration.md) - 版本升级指南
- [更新日志](docs/changelog.md) - 版本变更历史

---

## 贡献

欢迎贡献代码、文档或提出问题！详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 开源协议

MIT License
