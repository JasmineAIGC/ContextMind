# Baseline Template Module - 槽位模板基线版本

## 概述

这是一个独立的槽位模板基线实现模块，用于与 ContextMind 的上下文工程方式进行对比实验。

## 核心特点

### 1. 完全独立
- 不依赖 contextmind 框架
- 不使用记忆库功能
- 可以独立运行和测试

### 2. 简单直接
- 只有核心功能：对话历史 → 意图提取 → 模板填充 → 生成提示词
- 代码清晰易懂，便于理解和修改
- 适合作为对比实验的基准线（baseline）

### 3. 便于对比
- 与 contextmind 使用相同的系统提示词（从 `prompts.py` 导入）
- 输入输出格式一致
- 便于进行公平的对比实验

## 工作原理

```
对话历史 (List[Message])
    ↓
意图提取器 (IntentExtractor)
    ↓ 提取：意图、主题、上下文摘要
    ↓
提示词模板 (PromptTemplate)
    ↓ 填充槽位
    ↓
模板引擎 (TemplateEngine)
    ↓ 组合系统提示词 + 填充后的模板
    ↓
最终提示词 (str)
```

## 使用示例

### 基础使用

```python
import asyncio
from baseline_template import TemplateEngine, Message
from prompts import BASELINE_TEMPLATE_SYSTEM_PROMPT

async def main():
    # 创建引擎
    engine = TemplateEngine(system_prompt=BASELINE_TEMPLATE_SYSTEM_PROMPT)
    
    # 准备对话历史
    conversation_history = [
        Message(role="user", content="你好"),
        Message(role="assistant", content="你好！有什么可以帮助你的？"),
        Message(role="user", content="今天天气怎么样？"),
    ]
    
    # 生成提示词
    prompt = await engine.generate_prompt(conversation_history)
    print(prompt)

asyncio.run(main())
```

### 简化版使用（同步接口）

```python
from baseline_template import SimpleTemplateEngine, Message
from prompts import BASELINE_TEMPLATE_SYSTEM_PROMPT

# 创建简化版引擎
engine = SimpleTemplateEngine(system_prompt=BASELINE_TEMPLATE_SYSTEM_PROMPT)

# 直接生成提示词
prompt = engine.generate_prompt_sync(
    user_message="今天天气怎么样？",
    conversation_history=[
        Message(role="user", content="你好"),
        Message(role="assistant", content="你好！"),
    ]
)

print(prompt)
```

### 自定义模板

```python
from baseline_template import TemplateEngine, PromptTemplate, TemplateSlot

# 创建自定义模板
custom_template = PromptTemplate(
    template_id="custom",
    name="自定义模板",
    template_text="""用户意图: {intent}
话题: {topic}

请简洁回复。""",
    slots=[
        TemplateSlot(name="intent", default_value="一般对话"),
        TemplateSlot(name="topic", default_value="未知"),
    ]
)

# 使用自定义模板
engine = TemplateEngine(template=custom_template)
```

## 与 ContextMind 的对比

| 特性 | Baseline Template (本模块) | ContextMind (上下文工程) |
|-----|---------------------------|------------------------|
| 依赖 | 无外部依赖 | 依赖完整框架 |
| 记忆库 | ❌ 不使用 | ✅ 使用长期记忆 |
| 向量检索 | ❌ 不使用 | ✅ 使用嵌入向量 |
| 意图提取 | 基于规则 | 规则 + LLM（可选） |
| 上下文优化 | 模板填充 | 多策略优化 |
| 复杂度 | 简单 | 复杂 |
| 适用场景 | 基准对比、简单场景 | 复杂对话、需要记忆 |

## 对比实验建议

### 实验设置

1. **使用相同的系统提示词**
   ```python
   from prompts import BASELINE_TEMPLATE_SYSTEM_PROMPT
   
   # Baseline
   baseline_engine = TemplateEngine(system_prompt=BASELINE_TEMPLATE_SYSTEM_PROMPT)
   
   # ContextMind
   # 使用相同的系统提示词确保公平对比
   ```

2. **使用相同的测试数据**
   - 准备标准的对话历史数据集
   - 确保两种方法处理相同的输入

3. **评估指标**
   - 响应质量（人工评估）
   - 响应速度（时间测量）
   - 上下文连贯性
   - 记忆效果（如适用）

### 预期差异

- **Baseline**: 快速、简单、无记忆
- **ContextMind**: 较慢、复杂、有记忆和检索能力

## 文件结构

```
baseline_template/
├── __init__.py              # 模块初始化和导出
├── prompt_template.py       # 提示词模板系统
├── intent_extractor.py      # 意图提取器
├── template_engine.py       # 模板引擎（核心）
└── README.md               # 本文档
```

## 扩展和定制

### 自定义意图提取规则

```python
from baseline_template import IntentExtractor

class CustomIntentExtractor(IntentExtractor):
    def __init__(self):
        super().__init__()
        # 添加自定义关键词
        self.custom_keywords = ['特殊词', '关键词']
    
    def _classify_intent(self, text):
        # 自定义意图分类逻辑
        if any(kw in text for kw in self.custom_keywords):
            return "custom_intent", "自定义意图", 0.9
        return super()._classify_intent(text)
```

### 添加新的槽位

```python
from baseline_template import PromptTemplate, TemplateSlot

template = PromptTemplate(
    template_id="extended",
    name="扩展模板",
    template_text="""意图: {intent}
主题: {topic}
情感: {emotion}  # 新增槽位

上下文: {context}""",
    slots=[
        TemplateSlot(name="intent"),
        TemplateSlot(name="topic"),
        TemplateSlot(name="emotion", default_value="中性"),  # 新槽位
        TemplateSlot(name="context"),
    ]
)
```

## 性能基准

在典型场景下的性能表现：

- **意图提取**: < 5ms
- **模板填充**: < 1ms
- **总延迟**: < 10ms

（注：这些数字是估计值，实际性能取决于对话长度和硬件环境）

## 许可

与主项目保持一致。

## 贡献

欢迎提交 Issue 和 Pull Request 来改进这个基线实现。
