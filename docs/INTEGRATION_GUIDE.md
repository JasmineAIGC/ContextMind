# 模板优化集成指南

## 目录

1. [快速开始](#快速开始)
2. [集成方式](#集成方式)
3. [最佳实践](#最佳实践)
4. [常见问题](#常见问题)
5. [迁移指南](#迁移指南)

## 快速开始

### 最小集成示例

```python
from contextmind import ContextEngine
from contextmind.pipeline import TemplateBasedOptimization
from contextmind.core import ProcessedContext

# 1. 创建标准引擎（无变化）
engine = ContextEngine(
    app_name="my-app",
    user_id="user-123"
)

# 2. 创建模板优化器（可选）
optimizer = TemplateBasedOptimization()

# 3. 处理对话
user_input = "今天天气怎么样？"

# 标准流程
context = await engine.optimize(user_input)

# 可选：应用模板优化
processed = ProcessedContext(items=context.items)
enhanced = await optimizer.optimize(processed)

# 使用优化后的提示词
prompt = enhanced.items[0].content
```

### 验证集成

运行以下代码确认集成成功：

```python
from contextmind.pipeline import TemplateBasedOptimization
from contextmind.core import DEFAULT_CHAT_TEMPLATE

# 检查模板
print(f"模板名称: {DEFAULT_CHAT_TEMPLATE.name}")
print(f"槽位: {DEFAULT_CHAT_TEMPLATE.get_slot_names()}")

# 创建优化器
optimizer = TemplateBasedOptimization()
print("✓ 模板优化器创建成功")
```

## 集成方式

### 方式 1：完全独立使用（推荐新项目）

适合：全新项目，想要完全控制优化流程

```python
from contextmind.pipeline import TemplateBasedOptimization, IntentExtractor
from contextmind.core import PromptTemplate, ContextItem, ProcessedContext

# 创建自定义模板
template = PromptTemplate(
    template_id="custom",
    name="自定义模板",
    template_text="""意图: {intent}
主题: {topic}
上下文: {context}"""
)

# 创建优化器
optimizer = TemplateBasedOptimization(
    template=template,
    use_llm_extraction=False  # 使用规则提取
)

# 手动构建上下文
items = [
    ContextItem(content="user: 你好", ...),
    ContextItem(content="assistant: 你好！", ...),
]

context = ProcessedContext(items=items)
result = await optimizer.optimize(context)
```

### 方式 2：与 ContextEngine 配合（推荐现有项目）

适合：已有 ContextEngine 的项目，想要增强上下文

```python
from contextmind import ContextEngine
from contextmind.pipeline import TemplateBasedOptimization
from contextmind.core import ProcessedContext

# 标准引擎
engine = ContextEngine(app_name="app", user_id="user")

# 模板优化器（可选组件）
optimizer = TemplateBasedOptimization()

async def process_message(user_input: str) -> str:
    # 1. 标准优化
    context = await engine.optimize(user_input)
    
    # 2. 可选：模板优化
    if should_use_template():  # 根据场景决定
        processed = ProcessedContext(items=context.items)
        context = await optimizer.optimize(processed)
    
    # 3. 构建提示词
    prompt = "\n".join([item.content for item in context.items])
    
    # 4. 调用 LLM
    response = await llm_client.generate(prompt)
    
    # 5. 更新上下文
    await engine.update(user_input, response)
    
    return response
```

### 方式 3：条件启用（推荐生产环境）

适合：需要 A/B 测试或按场景选择

```python
class ChatApplication:
    def __init__(self, use_template_optimization: bool = False):
        self.engine = ContextEngine(...)
        self.use_template = use_template_optimization
        
        if self.use_template:
            from contextmind.pipeline import TemplateBasedOptimization
            self.optimizer = TemplateBasedOptimization()
        else:
            self.optimizer = None
    
    async def process(self, user_input: str):
        context = await self.engine.optimize(user_input)
        
        # 条件应用模板优化
        if self.optimizer:
            from contextmind.core import ProcessedContext
            processed = ProcessedContext(items=context.items)
            context = await self.optimizer.optimize(processed)
        
        # 继续处理...
```

## 最佳实践

### 1. 选择合适的提取器

**规则提取器**（默认）：
- ✅ 速度快（< 5ms）
- ✅ 无 API 成本
- ✅ 适合实时对话
- ❌ 准确度相对较低

**LLM 提取器**：
- ✅ 准确度高
- ✅ 理解深度更好
- ❌ 延迟高（500-2000ms）
- ❌ 有 API 成本

```python
# 生产环境推荐配置
if is_realtime_chat:
    # 实时对话：使用规则提取
    optimizer = TemplateBasedOptimization(use_llm_extraction=False)
else:
    # 离线分析：使用 LLM 提取
    optimizer = TemplateBasedOptimization(
        llm_client=your_llm_client,
        use_llm_extraction=True
    )
```

### 2. 自定义模板

为不同场景创建专门的模板：

```python
from contextmind.core import PromptTemplate, TemplateSlot

# 客服场景
CS_TEMPLATE = PromptTemplate(
    template_id="customer_service",
    name="客服模板",
    template_text="""你是专业客服。

客户意图: {intent}
问题类型: {topic}
历史记录: {context}
用户等级: {user_level}

请专业、友好地回复客户。必要时转人工。""",
    slots=[
        TemplateSlot(name="intent", required=True),
        TemplateSlot(name="topic", required=True),
        TemplateSlot(name="context", default_value="首次咨询"),
        TemplateSlot(name="user_level", default_value="普通用户"),
    ]
)

# 使用
cs_optimizer = TemplateBasedOptimization(template=CS_TEMPLATE)
```

### 3. 错误处理

```python
async def safe_template_optimization(context: ProcessedContext):
    """带错误处理的模板优化"""
    try:
        optimizer = TemplateBasedOptimization()
        result = await optimizer.optimize(context)
        return result
    except Exception as e:
        logger.error(f"模板优化失败: {e}")
        # 回退：返回原始上下文
        return context.to_context_result()
```

### 4. 性能监控

```python
import time

async def monitored_optimization(context: ProcessedContext):
    start = time.time()
    
    optimizer = TemplateBasedOptimization()
    result = await optimizer.optimize(context)
    
    duration = time.time() - start
    logger.info(f"模板优化耗时: {duration:.3f}s")
    
    return result
```

## 常见问题

### Q1: 使用模板优化会影响原有功能吗？

**答**：不会。模板优化是完全可选的附加功能，不使用时对原有功能零影响。

```python
# 不使用模板优化
engine = ContextEngine(...)
context = await engine.optimize("输入")
# 完全正常工作

# 使用模板优化
optimizer = TemplateBasedOptimization()
enhanced = await optimizer.optimize(ProcessedContext(items=context.items))
# 额外的优化步骤
```

### Q2: 如何知道何时使用模板优化？

**答**：根据场景判断：

| 场景 | 是否使用 | 原因 |
|-----|---------|------|
| 客服对话 | ✅ 推荐 | 意图明确，需要结构化引导 |
| 任务型对话 | ✅ 推荐 | 意图分类清晰 |
| 教学场景 | ✅ 推荐 | 需要明确的角色和引导 |
| 闲聊娱乐 | ❌ 不推荐 | 开放式对话，过度约束 |
| 创意写作 | ❌ 不推荐 | 需要自由发挥 |

### Q3: 模板优化的性能开销是多少？

**答**：
- 规则提取：< 10ms
- LLM 提取：500-2000ms（取决于 API）
- 模板填充：< 1ms

推荐：实时场景用规则提取，对性能影响可忽略不计。

### Q4: 可以同时使用多个模板吗？

**答**：可以。创建多个优化器实例：

```python
chat_optimizer = TemplateBasedOptimization(template=CHAT_TEMPLATE)
cs_optimizer = TemplateBasedOptimization(template=CS_TEMPLATE)

# 根据场景选择
if is_customer_service:
    result = await cs_optimizer.optimize(context)
else:
    result = await chat_optimizer.optimize(context)
```

### Q5: 如何自定义意图提取逻辑？

**答**：继承 IntentExtractor：

```python
from contextmind.pipeline import IntentExtractor, ExtractedIntent

class MyIntentExtractor(IntentExtractor):
    async def extract_intent(self, messages):
        # 自定义逻辑
        intent_type = analyze_with_my_model(messages)
        return ExtractedIntent(
            intent_type=intent_type,
            description="自定义意图",
            confidence=0.9
        )

# 使用
optimizer = TemplateBasedOptimization()
optimizer.intent_extractor = MyIntentExtractor()
```

## 迁移指南

### 从完全不使用到使用模板优化

**步骤 1**：评估需求

```python
# 现有代码（无需修改）
engine = ContextEngine(...)
context = await engine.optimize(user_input)
prompt = "\n".join([item.content for item in context.items])
response = await llm.generate(prompt)
```

**步骤 2**：添加模板优化（可选）

```python
from contextmind.pipeline import TemplateBasedOptimization
from contextmind.core import ProcessedContext

engine = ContextEngine(...)
optimizer = TemplateBasedOptimization()  # 新增

context = await engine.optimize(user_input)

# 新增：可选的模板优化
processed = ProcessedContext(items=context.items)
enhanced = await optimizer.optimize(processed)
prompt = enhanced.items[0].content  # 使用优化后的

response = await llm.generate(prompt)
```

**步骤 3**：观察效果

- 对比使用前后的回复质量
- 监控性能影响
- 根据效果决定是否保留

### A/B 测试配置

```python
import random

class AdaptiveApplication:
    def __init__(self):
        self.engine = ContextEngine(...)
        self.optimizer = TemplateBasedOptimization()
    
    async def process(self, user_input: str, user_id: str):
        context = await self.engine.optimize(user_input)
        
        # A/B 测试：50% 用户使用模板优化
        use_template = hash(user_id) % 2 == 0
        
        if use_template:
            from contextmind.core import ProcessedContext
            processed = ProcessedContext(items=context.items)
            context = await self.optimizer.optimize(processed)
            method = "template"
        else:
            method = "standard"
        
        # 记录使用的方法
        log_experiment(user_id, method)
        
        # 继续处理...
```

## 总结

### ✅ 集成要点

1. **完全可选**：不使用时不影响任何原有功能
2. **灵活配置**：可以按场景、用户、时间等条件启用
3. **易于回退**：任何时候都可以停止使用
4. **独立测试**：有专门的测试套件验证非侵入性

### 📊 决策树

```
是否需要明确的意图引导？
├─ 是 → 是否需要高准确度？
│   ├─ 是 → 使用 LLM 提取器
│   └─ 否 → 使用规则提取器（推荐）
└─ 否 → 不使用模板优化
```

### 🔗 相关文档

- [实现逻辑文档](./IMPLEMENTATION_LOGIC.md) - 详细的技术实现
- [使用文档](./TEMPLATE_OPTIMIZATION.md) - API 参考和示例
- [实现总结](../IMPLEMENTATION_SUMMARY.md) - 快速概览

---

**最后更新**：2026-01-29  
**文档版本**：v1.0
