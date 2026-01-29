# 基于模板的上下文优化 (Template-based Context Optimization)

## 概述

这是 ContextMind 的新增功能，通过**提示词模板（Prompt Template）**和**意图提取（Intent Extraction）**实现上下文优化。

### 核心思想

在每轮对话中：
1. 从对话历史中提取用户意图
2. 识别对话主题和上下文
3. 将提取的信息填充到预定义的模板槽位中
4. 使用填充后的模板指导大语言模型的回复

## 核心组件

### 1. PromptTemplate - 提示词模板

支持槽位（slots）的提示词模板系统。

**特性：**
- 自动从模板文本中提取槽位
- 支持必填/可选槽位
- 提供默认值机制
- 槽位验证

**使用示例：**

```python
from contextmind.core import PromptTemplate, TemplateSlot

# 创建模板
template = PromptTemplate(
    template_id="my_template",
    name="我的模板",
    template_text="""你是一个智能助手。

用户意图: {intent}
对话主题: {topic}
上下文: {context}

请基于以上信息回复。""",
    slots=[
        TemplateSlot(name="intent", description="用户意图", required=True),
        TemplateSlot(name="topic", description="对话主题", default_value="一般对话"),
        TemplateSlot(name="context", description="上下文信息", default_value="暂无"),
    ]
)

# 填充槽位
filled_prompt = template.fill_slots({
    'intent': '用户询问天气',
    'topic': '天气查询',
    'context': '用户位于北京'
})

print(filled_prompt)
```

### 2. IntentExtractor - 意图提取器

从对话历史中提取用户意图、主题和上下文摘要。

**两种实现：**
- **IntentExtractor**: 基于规则的快速提取（不需要LLM）
- **LLMIntentExtractor**: 基于LLM的精准提取（需要LLM客户端）

**使用示例：**

```python
from contextmind.pipeline import IntentExtractor
from contextmind.core import Message, MessageRole

# 创建提取器
extractor = IntentExtractor()

# 准备对话历史
messages = [
    Message(role=MessageRole.USER, content="你好"),
    Message(role=MessageRole.ASSISTANT, content="你好！"),
    Message(role=MessageRole.USER, content="今天天气怎么样？"),
]

# 提取意图
intent = await extractor.extract_intent(messages)
print(f"意图: {intent.description}")  # "用户提出问题或查询信息"

# 提取主题
topic = await extractor.extract_topic(messages)
print(f"主题: {topic}")  # "今天天气怎么样"

# 提取上下文摘要
summary = await extractor.extract_context_summary(messages)
print(f"摘要: {summary}")
```

### 3. TemplateBasedOptimization - 模板优化策略

将意图提取和模板填充整合到上下文优化流程中。

**使用示例：**

```python
from contextmind.pipeline import TemplateBasedOptimization
from contextmind.core import DEFAULT_CHAT_TEMPLATE, ProcessedContext

# 创建优化器
optimizer = TemplateBasedOptimization(
    template=DEFAULT_CHAT_TEMPLATE,
    use_llm_extraction=False  # 使用规则提取
)

# 优化上下文
context = ProcessedContext(items=your_context_items)
result = await optimizer.optimize(context)

# 使用优化后的内容
optimized_prompt = result.items[0].content
```

## 完整使用示例

### 基础使用

```python
import asyncio
from contextmind import ContextEngine
from contextmind.pipeline import TemplateBasedOptimization
from contextmind.core import PromptTemplate, TemplateSlot

async def main():
    # 1. 创建自定义模板
    template = PromptTemplate(
        template_id="chat_template",
        name="对话模板",
        template_text="""你是智能助手。

用户意图: {intent}
话题: {topic}
上下文: {context}

请回复用户。"""
    )
    
    # 2. 创建模板优化器
    optimizer = TemplateBasedOptimization(template=template)
    
    # 3. 在上下文引擎中使用（可选）
    # 您可以将优化器集成到自定义的优化流程中
    
    print("模板优化器已初始化")

asyncio.run(main())
```

### 与 ContextEngine 集成

虽然模板优化器可以独立使用，但也可以与现有的 ContextEngine 配合：

```python
from contextmind import ContextEngine
from contextmind.pipeline import TemplateBasedOptimization
from contextmind.core import DEFAULT_CHAT_TEMPLATE

async def chat_with_template_optimization():
    # 初始化引擎
    engine = ContextEngine(
        app_name="my-app",
        user_id="user-123"
    )
    
    # 创建模板优化器
    optimizer = TemplateBasedOptimization(
        template=DEFAULT_CHAT_TEMPLATE,
        use_llm_extraction=False
    )
    
    # 进行对话
    user_input = "今天天气怎么样？"
    
    # 1. 优化上下文
    context = await engine.optimize(user_input)
    
    # 2. 进一步使用模板优化
    from contextmind.core import ProcessedContext
    processed = ProcessedContext(items=context.items)
    optimized = await optimizer.optimize(processed)
    
    # 3. 使用优化后的提示词
    prompt = optimized.items[0].content
    
    # 4. 调用 LLM（用户自己实现）
    # response = await your_llm.generate(prompt)
    
    print("优化后的提示词:")
    print(prompt)
```

## 运行演示

我们提供了完整的演示程序：

```bash
# From the repository root
python examples/template_optimization_demo.py
```

演示包含：
1. 基础模板使用
2. 意图提取
3. 完整优化流程
4. 自定义模板示例

## 预定义模板

系统提供了一个默认模板 `DEFAULT_CHAT_TEMPLATE`：

```python
from contextmind.core import DEFAULT_CHAT_TEMPLATE

# 查看模板信息
print(f"模板名称: {DEFAULT_CHAT_TEMPLATE.name}")
print(f"槽位: {DEFAULT_CHAT_TEMPLATE.get_slot_names()}")
```

默认模板包含三个槽位：
- `intent`: 用户意图
- `topic`: 对话主题
- `context`: 相关上下文

## 扩展和自定义

### 自定义意图提取器

您可以继承 `IntentExtractor` 并实现自己的意图识别逻辑：

```python
from contextmind.pipeline import IntentExtractor

class MyIntentExtractor(IntentExtractor):
    async def extract_intent(self, messages):
        # 实现您的意图提取逻辑
        # ...
        return ExtractedIntent(...)
```

### 创建领域特定模板

针对不同场景创建专门的模板：

```python
# 客服模板
customer_service_template = PromptTemplate(
    template_id="customer_service",
    name="客服模板",
    template_text="""你是专业客服。

客户意图: {intent}
问题类型: {topic}
历史: {context}
用户级别: {user_level}

请专业回复。""",
    slots=[
        TemplateSlot(name="intent", required=True),
        TemplateSlot(name="topic", required=True),
        TemplateSlot(name="context", default_value="首次咨询"),
        TemplateSlot(name="user_level", default_value="普通用户"),
    ]
)
```

## 架构说明

```
┌─────────────────────────────────────────┐
│  TemplateBasedOptimization              │  优化策略
│  (整合意图提取和模板填充)                │
└─────────────────────────────────────────┘
            ↓                    ↓
┌──────────────────┐  ┌──────────────────┐
│ IntentExtractor  │  │ PromptTemplate   │  核心组件
│ (提取意图/主题)   │  │ (槽位管理)       │
└──────────────────┘  └──────────────────┘
            ↓                    ↓
┌─────────────────────────────────────────┐
│  ProcessedContext → ContextResult       │  数据流
└─────────────────────────────────────────┘
```

## API 参考

### PromptTemplate

**主要方法：**
- `fill_slots(slot_values, strict=False)`: 填充槽位
- `get_slot_names()`: 获取所有槽位名称
- `validate_slots(slot_values)`: 验证槽位值

### IntentExtractor

**主要方法：**
- `extract_intent(messages, focus_recent=5)`: 提取意图
- `extract_topic(messages, focus_recent=10)`: 提取主题
- `extract_context_summary(messages, max_length=200)`: 提取上下文摘要

### TemplateBasedOptimization

**主要方法：**
- `optimize(context)`: 执行优化
- `set_template(template)`: 更新模板
- `get_template_info()`: 获取模板信息

## 性能考虑

- **规则提取器**: 快速，无需 LLM，适合实时场景
- **LLM 提取器**: 更精准，但需要 API 调用，有延迟

根据您的应用场景选择合适的提取器。

## 未来计划

- [ ] 支持更多槽位类型（如列表、对象）
- [ ] 模板版本管理
- [ ] 模板库和共享
- [ ] 可视化模板编辑器
- [ ] A/B 测试支持

## 贡献

欢迎贡献代码、报告问题或提出改进建议！

---

**版本**: 1.0  
**作者**: ContextMind Team  
**许可**: MIT
