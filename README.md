# ContextMind

一个**通用、可扩展、易集成的上下文工程框架**，专为基于大语言模型的对话系统设计。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-7.3.0-green.svg)](https://github.com/yourusername/ContextMind)

---

## 🎯 什么是 ContextMind？

**ContextMind 是一个纯粹的上下文工程框架**，位于你的应用程序和任意大语言模型提供商之间。它解决了对话系统的核心挑战：**如何智能地管理、优化并向大语言模型提供上下文**。

### 问题背景

现代大语言模型面临三大核心挑战：
1. **有限的上下文窗口** - 即使是 32K/128K 的 token 限制在长对话中也会很快耗尽
2. **信息过载** - 并非所有历史记录都相关；无关上下文会降低响应质量
3. **多源整合** - 会话历史、长期记忆和外部知识需要统一管理

### 解决方案

```
用户输入 → [ContextMind 上下文工程] → 优化后的上下文 → 你的大语言模型 → 高质量响应
```

ContextMind 通过**五步流水线架构**将原始对话数据转换为精确优化的上下文：
1. **预处理** - 清理和规范化输入
2. **检索** - 召回相关记忆和上下文
3. **压缩** - 智能减少 token 使用
4. **重排序** - 优化上下文顺序
5. **响应处理** - 更新记忆库（LLM 调用后）

**注意**：LLM 调用发生在步骤 4 和 5 之间，由用户控制。

---

## ✨ 核心特性

### 🎨 通用性
- **无 UI 框架依赖** - 纯上下文工程，不耦合 Gradio/Streamlit
- **模型无关** - 适配 OpenAI、Anthropic、本地模型或任何大语言模型提供商
- **任务无关** - 适用于聊天机器人、客户服务、RAG、智能体及任何对话任务

### 🔌 可扩展的插件架构
- **可插拔策略** - 无需修改代码即可切换提取器、检索器、压缩器
- **自定义插件** - 通过插件注册表轻松注册自定义策略
- **模块化流水线** - 每个组件（预处理器、压缩器、重排序器）均可独立配置

### ⚡ 易于集成
- **三行代码集成** - 最少样板代码，最大功能
- **异步优先** - 原生支持 async/await 以实现高性能应用
- **会话管理** - 内置会话处理和自动记忆持久化

### 🚀 高级上下文优化
- **智能检索** - 语义搜索、混合检索、基于定位器的策略
- **上下文压缩** - 在保留关键信息的同时减少 token 数量
- **记忆管理** - 自动提取知识的长期记忆
- **上下文重排序** - 缓解"中间丢失"问题

---

## 🚀 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/yourusername/ContextMind.git
cd ContextMind

# 安装依赖
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
        extraction_method="llm"      # 或 "rule"
    )
    
    # 步骤 1-4：准备优化后的上下文
    context = await engine.optimize("今天天气怎么样？")
    
    # 步骤 5：你调用外部大语言模型（ContextMind 外部）
    llm_response = await your_llm_client.chat(
        messages=context.to_messages(),  # 转换为消息格式
        # 或使用 context.to_prompt() 获取字符串
    )
    
    # 步骤 6：处理响应并自动更新记忆
    result = await engine.handle_response(
        user_input="今天天气怎么样？",
        llm_response=llm_response,
        context=context,
        auto_extract=True,   # 自动提取知识
        auto_store=True      # 自动存储到记忆库
    )
    
    print(f"响应已处理: {result['recorded']}")
    print(f"提取知识: {len(result['extracted_knowledge'])} 条")
    print(f"已入库: {result['stored']}")

asyncio.run(main())
```

### 简化用法（向后兼容）

```python
# 如果只需要简单的对话记录，无需知识提取
async def simple_usage():
    engine = ContextEngine(app_name="my-app", user_id="user-123")
    
    context = await engine.optimize("你好")
    response = await your_llm.chat(context.to_prompt())
    
    # 仅记录对话，不提取知识
    await engine.update("你好", response)
```

---

## 📐 架构

### 五步流水线 (v7.3)

```
用户输入
    ↓
1. InputPreprocessor     (清理和规范化)
    ↓
2. ContextRetriever +    (检索上下文)
   MemoryBank            (召回长期记忆)
    ↓
3. ContextCompressor     (智能压缩)
    ↓
4. ContextReorderer      (重排序优化)
    ↓
构建提示 → [用户调用 LLM] → 获得响应
    ↓
5. ResponseHandler       (处理响应 + 更新记忆)
    ↓
最终结果 + 记忆已更新
```

### 分层设计

```
┌─────────────────────────────────────────┐
│  应用层                                  │  你的应用代码
│  (demos/, examples/)                     │
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│  引擎层                                  │  ContextEngine、ContextMind API
│  (engine.py, framework_config.py)       │
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│  流水线层                                │  六步处理流程
│  (pipeline/)                             │
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│  策略/插件层                             │  可插拔算法
│  (strategies/, registry)                 │
└─────────────────────────────────────────┘
```

---

## 🎯 核心组件

### MemoryBank - 长期记忆管理
跨会话持久化存储和智能检索用户信息、偏好和事实。

**核心功能：**
- 从对话中提取知识
- 使用可配置检索器进行语义搜索
- 自动更新记忆并解决冲突
- 会话管理和消息历史

### Plugin Registry - 可扩展引擎
用于切换和注册自定义策略的集中式插件管理系统。

**支持的插件类型：**
- **提取器（Extractors）** - 从对话中提取知识（基于大语言模型）
- **检索器（Retrievers）** - 检索相关记忆（语义搜索、基于嵌入向量）
- **更新器（Updaters）** - 使用智能去重更新记忆（基于嵌入向量相似度）
- **摘要器（Summarizers）** - 压缩上下文（基于大语言模型）

### 流水线组件
1. **预处理器（Preprocessor）** - 输入清理、验证和规范化
2. **上下文检索器（ContextRetriever）** - 外部知识检索（可扩展占位符）
3. **压缩器（Compressor）** - 基于大语言模型的 token 级上下文压缩和摘要
4. **重排序器（Reorderer）** - 上下文重排序以对抗注意力稀释
5. **响应处理器（ResponseHandler）** - 响应解析、知识提取和记忆更新

### Evolution - 进化式记忆优化（高级功能）
借鉴 AlphaEvolve/ThetaEvolve 思想的进化式记忆管理系统。

**核心能力：**
- **观测-反馈-学习循环** - 持续优化记忆质量
  - 观测：记录记忆的检索和使用情况
  - 反馈：收集用户评价和系统评估
  - 学习：动态调整记忆的价值评分
- **多维度适应度评估** - 使用频率、使用率、时间新鲜度、准确性、贡献度
- **智能进化操作** - 精英选择、记忆合并、自动淘汰
- **反馈收集** - 显式反馈（用户评价）+ 隐式反馈（行为分析）

> 💡 **不理解观测-反馈-学习循环？** 查看 [通俗易懂的解释文档](docs/UNDERSTANDING_OBSERVATION_FEEDBACK_LEARNING.md)

**使用示例：**
```python
from contextmind import MemoryBank, EvolutionaryMemoryUpdater

# 使用进化式更新器
updater = EvolutionaryMemoryUpdater(
    max_memory_size=100,
    elite_ratio=0.7,  # 保留70%高质量记忆
)

memory_bank = MemoryBank(updater=updater)
```

---

## 📚 项目结构

```
ContextMind/
├── contextmind/                    # 核心框架（纯上下文工程）
│   ├── __init__.py                 # 框架入口点
│   ├── engine.py                   # ContextEngine - 主要编排器
│   ├── core/
│   │   ├── framework_config.py     # ContextMind 高级 API
│   │   ├── registry.py             # 插件注册系统
│   │   ├── data_models.py          # 数据模型（Message、Knowledge 等）
│   │   ├── types.py                # 类型定义
│   │   ├── configs.py              # 配置类
│   │   └── strategies.py           # 策略基类
│   ├── pipeline/                   # 六步流水线组件
│   │   ├── preprocessor.py         # 步骤 1：输入预处理
│   │   ├── context_retriever.py    # 步骤 2：外部检索
│   │   ├── compressor.py           # 步骤 3：上下文压缩
│   │   ├── reorderer.py            # 步骤 4：上下文重排序
│   │   ├── summarizer.py           # 摘要器（由压缩器使用）
│   │   └── response_handler.py     # 步骤 5：响应处理和记忆更新
│   ├── memory/                     # MemoryBank 模块
│   │   ├── bank.py                 # 主 MemoryBank 类
│   │   ├── session.py              # 会话管理
│   │   ├── extractor.py            # 知识提取（基于大语言模型）
│   │   ├── retriever.py            # 记忆检索（语义搜索）
│   │   ├── updater.py              # 记忆更新（基于嵌入向量去重）
│   │   └── memory_fitness.py       # 适应度评估
│   ├── evolution/                  # 进化式记忆优化（高级功能）
│   │   ├── evolutionary_updater.py # 进化式更新器
│   │   ├── feedback_system.py      # 观测和反馈收集
│   │   ├── examples/               # 演示程序
│   │   └── docs/                   # 详细文档
│   └── utils/                      # 工具（日志、嵌入等）
│
├── slot_template/                  # 槽位模板上下文优化（Baseline）
│   ├── __init__.py                 # 模块入口
│   ├── engine.py                   # SlotTemplateEngine - 核心引擎
│   ├── intent_extractor.py         # IntentExtractor - 意图提取器
│   ├── template_manager.py         # TemplateManager - 模板管理器
│   └── README.md                   # 槽位模板文档
│
├── examples/                       # 应用示例
│   ├── chat_app.py                 # 聊天应用示例
│   ├── callcenter_app.py           # 客户服务示例
│   ├── plugin_examples.py          # 插件使用示例
│   └── llm_client.py               # 大语言模型客户端包装器
│
├── tests/                          # 单元和集成测试
├── docs/                           # 文档
│   ├── ARCHITECTURE.md             # 详细架构
│   ├── MIGRATION.md                # 迁移指南
│   ├── MODULE_REORGANIZATION.md    # 模块重组说明
│   └── SLOT_TEMPLATE_IMPLEMENTATION.md  # 槽位模板实现文档
│
├── prompts.py                      # 统一系统提示词管理
├── interactive_demo.py             # 命令行交互演示
├── gradio_demo.py                  # Web UI 演示（Gradio）
├── chat_interactive_demo.py        # 聊天命令行演示
├── chat_gradio_demo.py             # 聊天 Web 演示
├── callcenter_interactive_demo.py  # 客服命令行演示
├── callcenter_gradio_demo.py       # 客服 Web 演示
├── slot_template_demo.py           # 槽位模板演示
├── comparison_experiment.py        # 对比实验脚本
├── requirements.txt                # 依赖
└── README.md                       # 本文件
```

---

## 🔧 高级配置

### 自定义策略注册

```python
from contextmind import registry
from contextmind.strategies.base import BaseExtractor

class CustomExtractor(BaseExtractor):
    """你的自定义知识提取逻辑"""
    async def extract(self, messages):
        # 实现你的提取逻辑
        knowledge_items = []
        # ... 你的代码 ...
        return knowledge_items

# 注册你的自定义策略
registry.register_extractor('custom', CustomExtractor)

# 使用它
cm = ContextMind(llm_client=your_llm, extractor='custom')
```

### 细粒度配置

```python
from contextmind import ContextMind
from contextmind.core import MemorySystemConfig, CompressionConfig

# 配置记忆系统
memory_config = MemorySystemConfig(
    max_memory_items=1000,
    retrieval_top_k=5,
    similarity_threshold=0.7
)

# 配置压缩
compression_config = CompressionConfig(
    max_context_tokens=4096,
    compression_ratio=0.5
)

cm = ContextMind(
    llm_client=your_llm,
    memory_config=memory_config,
    compression_config=compression_config
)
```

---

## 🔬 槽位模板 Baseline

ContextMind 项目还包含一个**槽位模板上下文优化方案**作为对比实验的基线（baseline）。

### 什么是槽位模板？

槽位模板是一个**简单的上下文优化方法**，通过预定义的槽位从对话历史中提取关键信息：

```python
from slot_template import SlotTemplateEngine

# 初始化引擎
engine = SlotTemplateEngine()

# 添加对话历史
engine.add_message("user", "我叫张三")
engine.add_message("assistant", "很高兴认识你！")

# 处理当前输入
result = await engine.process("你还记得我叫什么吗？")

# 获取槽位值
print(result['slot_values'])
# {
#   "user_intent": "用户意图：咨询",
#   "conversation_context": "已进行 1 轮对话...",
#   "key_info": "提到实体: 张三"
# }
```

### 🆕 对话状态追踪 (DST)

**新增功能**：基于 **ACL 2023 论文** 的 Zero-shot 对话状态追踪实现。

```python
from slot_template import DialogueStateTracker, PromptManager

# 创建追踪器
pm = PromptManager(domain="restaurant")
pm.add_slot("food_type", "菜系", ["中餐", "西餐", "日料"])

tracker = DialogueStateTracker(prompt_manager=pm)
tracker.reset_dialogue()

# 处理对话
state = await tracker.process_turn(
    "您好，要预订吗？",
    "是的，订一家中餐厅"
)
print(state)  # {"food_type": "中餐", "intent": "预订"}
```

**DST 特性：**
- ✅ Zero-shot（无需微调）
- ✅ 累积式状态更新
- ✅ 共指消解支持
- ✅ 幻觉过滤
- ✅ 值归一化

### 槽位模板 vs ContextMind

| 特性 | 槽位模板 | ContextMind |
|------|---------|------------|
| 复杂度 | ⭐ 简单 | ⭐⭐⭐⭐ 复杂 |
| 记忆库 | ❌ 无 | ✅ 有 |
| 上下文检索 | ❌ 无 | ✅ 语义检索 |
| 上下文压缩 | ❌ 无 | ✅ 智能压缩 |
| 适用场景 | Baseline/简单对话 | 生产环境/复杂应用 |

### 运行对比实验

```bash
# 运行槽位模板演示
python slot_template_demo.py

# 运行 DST 演示
python dst_demo.py

# 运行对比实验
python comparison_experiment.py
```

详细文档：
- [对话状态追踪文档](docs/DST_DOCUMENTATION.md) 🆕
- [槽位模板实现文档](docs/SLOT_TEMPLATE_IMPLEMENTATION.md)
- [槽位模板模块文档](slot_template/README.md)

---

## 📊 应用场景

### 1. 具有长期记忆的聊天机器人
```python
# 用户："我喜欢吃辣"
# ... 多次对话后 ...
# 用户："推荐一家餐厅"
# 机器人："根据你喜欢吃辣的偏好，我推荐..."
```

### 2. 具有上下文连续性的客户服务
```python
# 会话 1：用户报告问题
# 会话 2（几天后）：用户跟进
# 机器人自动记住问题详情
```

### 3. RAG 应用
```python
# 结合会话历史 + 外部知识 + 记忆
context = await cm.prepare_context(
    user_input="解释量子计算",
    session_id="user-456"
)
# ContextMind 自动检索相关文档和过往讨论
```

---

## ✅ 测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行特定测试模块
python -m pytest tests/test_core.py -v
python -m pytest tests/test_pipeline.py -v
python -m pytest tests/test_memory.py -v
```

**测试覆盖率：**
- ✅ 数据模型和类型
- ✅ 流水线组件（6 步）
- ✅ MemoryBank 系统
- ✅ 插件注册表
- ✅ 策略实现

---

## 🎨 运行演示

### 命令行演示
```bash
# 交互式命令行演示
python interactive_demo.py

# 聊天命令行演示
python chat_interactive_demo.py
```

### Web UI 演示（Gradio）
```bash
# 基础 Gradio 演示
python gradio_demo.py

# 聊天 Gradio 演示
python chat_gradio_demo.py
```

**注意：** 演示文件需要 API 密钥。创建 `.env` 文件：
```bash
# Qwen API 示例
QWEN3_API_KEY=your-api-key
QWEN3_MODEL=Qwen3-32B
QWEN3_BASE_URL=https://api.example.com
```

---

## 🌟 设计原则

1. **模块化** - 每个组件都有单一职责，可独立替换
2. **可扩展性** - 插件架构允许轻松集成新策略
3. **关注点分离** - 上下文工程 ≠ 大语言模型推理 ≠ UI 框架
4. **类型安全** - 使用数据模型进行强类型检查以确保可靠性
5. **异步优先** - 原生支持 async/await 以实现高性能应用
6. **代码复用** - 组合优于继承，消除重复

---

## 📈 性能

### Token 管理精度
| 方法 | 英文误差 | 中文误差 | 溢出风险 |
|--------|---------------|---------------|---------------|
| 字符估算 | ±20% | ±40% | 高 ❌ |
| ContextMind | <1% | <1% | 无 ✅ |

### 缓存性能
| 场景 | 无缓存 | 有缓存 | 加速 |
|----------|---------------|------------|---------|
| 嵌入计算 | 500ms | 5ms | 100x ✅ |
| 向量检索 | 100ms | 10ms | 10x ✅ |
| 大语言模型摘要 | 2000ms | 5ms | 400x ✅ |

---

## 🤝 贡献

我们欢迎贡献！在提交 PR 之前：
- ✅ 运行所有测试并确保它们通过
- ✅ 遵循现有的代码风格
- ✅ 为新功能添加文档
- ✅ 更新相关测试

---

## 📄 许可证

MIT 许可证 - 详见 [LICENSE](LICENSE)

---

## 🔗 链接

- **文档**: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **示例**: [examples/](examples/)
- **问题**: [GitHub Issues](https://github.com/yourusername/ContextMind/issues)

---

**ContextMind** - 让上下文优化既简单又强大 ✨

