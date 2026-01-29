# 槽位模板基线版本 - 使用指南

## 概述

槽位模板基线版本是一个简单、快速的上下文优化方法，**不使用记忆库**，只基于对话历史进行意图提取和模板填充。

## 特点

- ✅ 完全独立，不依赖 ContextMind 框架
- ✅ 基于规则的意图提取（< 5ms）
- ✅ 模板填充生成提示词（< 1ms）
- ✅ 适合简单对话场景和快速原型
- ✅ 提供命令行和 Gradio UI 两种演示

## 使用方式

### 1. 命令行演示

```bash
python baseline_demo.py
```

这将运行命令行版本的演示，展示：
- 基线模板引擎的基本用法
- 简化版模板引擎的使用
- 与 ContextMind 的对比要点

### 2. Gradio UI 演示 ✨

```bash
python baseline_gradio_demo.py
```

然后在浏览器中访问：http://localhost:7860

**Gradio UI 功能**：
- 📱 友好的聊天界面
- ⚙️ 可切换系统提示词（基线模板 / 闲聊）
- 📝 实时显示生成的提示词
- 📊 对话统计信息
- 🔄 清空对话历史
- 💡 使用提示和槽位说明

### 3. 对比实验

```bash
python comparison_experiment.py
```

自动运行 Baseline Template 和 ContextMind 的对比实验，展示：
- 响应速度差异（Baseline < 10ms vs ContextMind ~50ms+）
- 功能差异（无记忆 vs 有记忆）
- 适用场景建议

## 模块结构

```
baseline_template/          # 槽位模板基线模块
├── __init__.py            # 模块初始化
├── prompt_template.py     # 提示词模板系统
├── intent_extractor.py    # 意图提取器
├── template_engine.py     # 模板引擎
└── README.md             # 模块文档

baseline_demo.py           # 命令行演示
baseline_gradio_demo.py    # Gradio UI 演示 ✨
comparison_experiment.py   # 对比实验工具
prompts.py                 # 统一的系统提示词
```

## 代码示例

### 基本使用

```python
from baseline_template import TemplateEngine, Message
from prompts import BASELINE_TEMPLATE_SYSTEM_PROMPT
import asyncio

# 创建引擎
engine = TemplateEngine(system_prompt=BASELINE_TEMPLATE_SYSTEM_PROMPT)

# 准备对话历史
conversation = [
    Message(role="user", content="你好"),
    Message(role="assistant", content="你好！有什么可以帮助你的？"),
    Message(role="user", content="今天天气怎么样？"),
]

# 生成提示词
async def main():
    prompt = await engine.generate_prompt(conversation)
    print(prompt)

asyncio.run(main())
```

### 在 Gradio 应用中使用

参考 `baseline_gradio_demo.py` 的实现。

## 工作流程

```
用户输入 + 对话历史
    ↓
IntentExtractor (规则提取)
    ├── 意图识别 (问候/问题/任务/情感)
    ├── 主题提取 (关键词)
    └── 上下文摘要 (最近对话)
    ↓
PromptTemplate (模板填充)
    ├── 填充 {intent} 槽位
    ├── 填充 {topic} 槽位
    └── 填充 {context} 槽位
    ↓
TemplateEngine (组合生成)
    ├── 系统提示词
    ├── 填充后的模板
    └── 当前用户输入
    ↓
最终提示词
```

## 槽位说明

默认模板包含以下槽位：

- **{intent}**: 用户意图（自动识别）
  - 问候、问题、任务请求、情感表达等
  
- **{topic}**: 对话主题（自动提取）
  - 从用户消息中提取的关键词
  
- **{context}**: 上下文摘要（最近对话）
  - 最近几轮对话的简要总结

## 适用场景

| 场景 | 是否适用 | 说明 |
|-----|---------|------|
| 简单问答 | ✅ 推荐 | 速度快，足够使用 |
| 快速原型 | ✅ 推荐 | 开发简单 |
| 客服系统 | ❌ 不推荐 | 需要记忆客户信息，建议用 ContextMind |
| 长期对话 | ❌ 不推荐 | 无法记住早期信息，建议用 ContextMind |

## 与 ContextMind 的对比

| 特性 | Baseline Template | ContextMind |
|-----|------------------|-------------|
| **架构** | 独立模块 | 完整框架 |
| **记忆库** | ❌ 无 | ✅ 有 |
| **向量检索** | ❌ 无 | ✅ 有 |
| **意图提取** | 规则 | 规则 + LLM |
| **优化策略** | 模板填充 | 多策略 |
| **速度** | < 10ms | 50ms+ |
| **复杂度** | 低 | 高 |

## 文档

- `baseline_template/README.md` - 模块详细文档
- `docs/COMPARISON_GUIDE.md` - 对比实验指南
- `docs/BASELINE_REFACTORING_SUMMARY.md` - 重构总结

## 依赖

无额外依赖，使用标准 Python 库。

Gradio UI 需要：
```bash
pip install gradio>=4.0.0
```

## 总结

槽位模板基线版本提供了一个简单、快速的上下文优化方案，适合：
- 快速原型开发
- 简单对话场景
- 作为对比实验的基准
- 理解上下文优化的核心原理

对于需要长期记忆、个性化、复杂对话的场景，建议使用完整的 ContextMind 框架。
