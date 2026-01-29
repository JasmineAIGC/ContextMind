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
from baseline import DialogueStateTracker, PromptManager
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

```bash
# 闲聊演示
python chat_interactive_demo.py --mode contextmind  # 完整模式
python chat_interactive_demo.py --mode basic        # DST 模式

# 客服演示
python callcenter_interactive_demo.py --mode contextmind
python callcenter_interactive_demo.py --mode basic

# Web UI
python chat_gradio_demo.py
python callcenter_gradio_demo.py

# DST 基础演示
python baseline_demo.py
```

---

## 项目结构

```
ContextMind/
├── contextmind/           # 完整框架（五层架构）
├── baseline/              # DST 基础实现（ACL 2023）
├── utils/                 # 通用工具（logger, LLM client）
├── examples/              # 应用示例
├── docs/                  # 文档
└── *_demo.py              # 演示程序
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
