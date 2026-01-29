# ContextMind

一个**通用、可扩展、易集成的上下文工程框架**，专为基于大语言模型的对话系统设计。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-7.4.0-green.svg)](https://github.com/Jasmine66Bloom/ContextMind)

---

## 🎯 什么是 ContextMind？

**ContextMind 是一个纯粹的上下文工程框架**，位于你的应用程序和大语言模型之间，解决对话系统的核心挑战：**如何智能地管理和优化上下文**。

### 核心问题

现代大语言模型面临三大挑战：
1. **有限的上下文窗口** - token 限制在长对话中很快耗尽
2. **信息过载** - 无关上下文会降低响应质量
3. **多源整合** - 会话历史、长期记忆和外部知识需要统一管理

### 解决方案

```
用户输入 → [ContextMind 上下文工程] → 优化后的上下文 → 大语言模型 → 高质量响应
```

ContextMind 通过**五步流水线架构**优化上下文：
1. **预处理** - 清理和规范化输入
2. **检索** - 召回相关记忆和上下文
3. **压缩** - 智能减少 token 使用
4. **重排序** - 优化上下文顺序
5. **响应处理** - 更新记忆库

---

## ✨ 核心特性

- **模型无关** - 适配 OpenAI、Anthropic、本地模型或任何 LLM 提供商
- **可插拔策略** - 无需修改代码即可切换提取器、检索器、压缩器
- **三行代码集成** - 最少样板代码，最大功能
- **智能记忆管理** - 自动提取知识的长期记忆，语义检索
- **上下文优化** - 压缩、重排序，缓解"中间丢失"问题

---

## 🚀 快速开始

### 安装

```bash
git clone https://github.com/Jasmine66Bloom/ContextMind.git
cd ContextMind
pip install -r requirements.txt
```

### 基本用法

```python
import asyncio
from contextmind import ContextEngine

async def main():
    # 初始化上下文引擎
    engine = ContextEngine(
        app_name="my-app",
        user_id="user-123",
        llm_client=your_llm_client,  # 可选：用于知识提取
    )
    
    # 步骤 1-4：准备优化后的上下文
    context = await engine.optimize("今天天气怎么样？")
    
    # 步骤 5：调用外部 LLM
    llm_response = await your_llm_client.chat(
        messages=context.to_messages()
    )
    
    # 步骤 6：更新记忆
    await engine.update_memory(llm_response)
    
asyncio.run(main())
```

### 高级 API（更简单）

```python
from contextmind import ContextMind

# 使用高级 API（推荐）
cm = ContextMind(
    app_name="my-app",
    user_id="user-123",
    llm_client=your_llm,
    enable_memory=True,      # 启用长期记忆
    enable_compression=True  # 启用上下文压缩
)

# 一次调用完成所有操作
response = await cm.chat("你好，今天天气怎么样？")
```

---

## 📐 架构

### 五步流水线

```
用户输入 
  ↓
[1] 预处理器 - 清理、验证输入
  ↓
[2] 记忆检索 - 召回相关记忆
  ↓
[3] 压缩器 - 减少 token 使用
  ↓
[4] 重排序器 - 优化上下文顺序
  ↓
优化后的上下文 → [你的 LLM] → 响应
  ↓
[5] 响应处理 - 提取知识，更新记忆
```

### 核心组件

- **ContextEngine** - 主编排器，协调整个流水线
- **MemoryBank** - 长期记忆管理（存储、检索、更新）
- **Plugin Registry** - 可扩展的策略注册系统
- **Evolution Module** - 进化式记忆优化（高级功能）

详细架构请参考：[ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## 🎮 运行演示

### ContextMind 完整演示

```bash
# 命令行交互演示
python chat_interactive_demo.py --mode contextmind

# Web 界面演示（需要 gradio）
python chat_gradio_demo.py
```

### 基础版本演示（ACL 2023 DST）

项目包含一个基于 **ACL 2023 论文**的对话状态追踪（DST）基础实现，作为对比基准：

```bash
# 运行 DST 演示（基础版本）
python baseline_demo.py

# 在交互或 Gradio 演示中切换到基础模式
python chat_interactive_demo.py --mode basic
python chat_gradio_demo.py  # 在 UI 中选择"基础 DST 模式"
```

**基础版本特性：**
- ✅ Zero-shot（无需微调）
- ✅ 累积式状态更新
- ✅ 共指消解支持

详细文档：[BASIC_DST_DOCUMENTATION.md](docs/BASIC_DST_DOCUMENTATION.md)

---

## 🔌 自定义插件

### 注册自定义策略

```python
from contextmind import registry
from contextmind.strategies.base import BaseExtractor

class CustomExtractor(BaseExtractor):
    async def extract(self, messages):
        # 你的提取逻辑
        return knowledge_items

# 注册并使用
registry.register_extractor('custom', CustomExtractor)
cm = ContextMind(llm_client=your_llm, extractor='custom')
```

---

## 📚 项目结构

```
ContextMind/
├── contextmind/              # 核心框架
│   ├── engine.py             # ContextEngine 主编排器
│   ├── core/                 # 核心组件（配置、注册、数据模型）
│   ├── pipeline/             # 五步流水线
│   ├── memory/               # MemoryBank 记忆管理
│   ├── evolution/            # 进化式优化（高级）
│   └── utils/                # 工具函数
│
├── baseline/                 # 基础 DST 实现（对比基准）
│   └── dialogue_state_tracker.py  # ACL 2023 DST 实现
│
├── examples/                 # 应用示例
├── docs/                     # 文档
│   ├── ARCHITECTURE.md       # 详细架构
│   ├── BASIC_DST_DOCUMENTATION.md  # DST 文档
│   └── MIGRATION.md          # 迁移指南
│
├── baseline_demo.py          # 基础版本演示（ACL 2023 DST）
├── chat_interactive_demo.py  # 聊天命令行演示
├── chat_gradio_demo.py       # 聊天 Web 演示
└── callcenter_*_demo.py      # 客服场景演示
```

---

## 📖 文档

- [架构文档](docs/ARCHITECTURE.md) - 详细的架构说明
- [DST 文档](docs/BASIC_DST_DOCUMENTATION.md) - 基础 DST 实现文档
- [迁移指南](docs/MIGRATION.md) - 版本迁移说明

---

## 🤝 贡献

欢迎贡献！请查看 issues 或提交 PR。

---

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

---

## ⭐ Star History

如果这个项目对你有帮助，请给个 star ⭐
