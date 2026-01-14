# ContextMind 2.0 - Universal Context Optimization Framework

**全新通用上下文优化框架** - 完全重新设计，支持快速集成各种上下文优化技术

## 🌟 核心特性

- ⚡ **高性能**: 全异步设计，支持并发处理
- 🔌 **插件化**: 步骤和策略完全可插拔
- 📝 **声明式**: 支持代码和配置两种构建方式
- 🎯 **类型安全**: 完整的Python类型提示
- 🔍 **可观测**: 内置执行追踪和性能监控
- 🧩 **模块化**: 清晰的四层架构设计

## 🏗️ 架构设计

```
Pipeline Layer (编排层)
    ↓
Step Layer (步骤层 - 可配置)
    ↓
Strategy Layer (策略层 - 可替换)
    ↓
Component Layer (组件层 - 可复用)
```

### 核心概念

**Context**: 在pipeline中流动的数据容器，包含所有状态和元数据

**Pipeline**: 编排引擎，管理步骤的顺序执行

**Step**: 处理单元，执行特定的转换操作

**Strategy**: 可插拔的算法实现，同一步骤可使用不同策略

## 🚀 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/Jasmine66Bloom/ContextMind.git
cd ContextMind

# 当前版本无需额外依赖（仅使用Python标准库）
```

### 基础使用

```python
import asyncio
from contextmind import Context, PipelineBuilder
from contextmind.steps import ValidationStep, CollectionStep, GenerationStep
from contextmind.strategies import KeywordRetrievalStrategy

async def main():
    # 1. 构建pipeline
    pipeline = PipelineBuilder("my_pipeline") \
        .add_step("validation") \
        .add_custom_step(
            "collection",
            CollectionStep(collection_strategy=KeywordRetrievalStrategy())
        ) \
        .add_step("integration") \
        .add_custom_step("generation", GenerationStep()) \
        .build()
    
    # 2. 创建上下文
    context = Context(user_input="What is the price?")
    
    # 3. 执行pipeline
    result = await pipeline.execute(context)
    
    # 4. 获取结果
    print(f"Response: {result.response}")
    print(f"Processing time: {result.get_metadata('pipeline_duration')}s")

if __name__ == "__main__":
    asyncio.run(main())
```

### 运行示例

```bash
python examples/basic_example.py
```

## 📚 核心组件

### Pipeline

Pipeline是核心编排引擎，管理步骤的执行流程。

```python
from contextmind import Pipeline, PipelineBuilder

# 方式1: 使用Builder（推荐）
pipeline = PipelineBuilder("my_pipeline") \
    .add_step("validation", min_length=1, max_length=1000) \
    .add_step("collection") \
    .build()

# 方式2: 从配置构建
config = {
    "name": "my_pipeline",
    "steps": [
        {"type": "validation", "min_length": 1},
        {"type": "collection"}
    ]
}
pipeline = PipelineBuilder.from_config(config)

# 执行
result = await pipeline.execute(context)
```

### Context

Context是数据容器，在步骤间传递数据。

```python
from contextmind import Context, ContextData

# 创建context
context = Context(user_input="Hello")

# 读写数据
context.set("key", "value")
value = context.get("key", default="default")

# 添加结构化数据
context.add_context_data(ContextData(
    content="Some context information",
    source="knowledge_base",
    score=0.9
))

# 获取元数据
context.set_metadata("request_id", "123")
request_id = context.get_metadata("request_id")
```

### Steps (步骤)

步骤是处理单元，实现特定的转换逻辑。

#### 内置步骤

**ValidationStep**: 输入验证和预处理
```python
from contextmind.steps import ValidationStep

step = ValidationStep(
    min_length=1,
    max_length=1000,
    strip_whitespace=True
)
```

**CollectionStep**: 上下文收集
```python
from contextmind.steps import CollectionStep
from contextmind.strategies import KeywordRetrievalStrategy

step = CollectionStep(
    collection_strategy=KeywordRetrievalStrategy()
)
```

**IntegrationStep**: 上下文整合
```python
from contextmind.steps import IntegrationStep

step = IntegrationStep(
    integration_method="structured",  # or "concat"
    prioritize_by_score=True
)
```

**GenerationStep**: 响应生成
```python
from contextmind.steps import GenerationStep

step = GenerationStep(
    generator=my_llm_client,  # 可选的LLM客户端
    max_retries=3
)
```

#### 自定义步骤

```python
from contextmind.core import BaseStep, Context, register_step

@register_step("my_step", "My custom step")
class MyStep(BaseStep):
    def __init__(self, **config):
        super().__init__(config)
    
    async def execute(self, context: Context) -> Context:
        # 处理逻辑
        user_input = context.user_input
        context.set("processed", user_input.upper())
        return context
```

### Strategies (策略)

策略是可插拔的算法实现。

#### 内置策略

**检索策略**:
- `SimpleRetrievalStrategy`: 简单检索
- `KeywordRetrievalStrategy`: 关键词匹配检索

**Prompt策略**:
- `SimplePromptStrategy`: 简单Prompt生成
- `TemplatePromptStrategy`: 模板化Prompt

#### 自定义策略

```python
from contextmind.core import BaseStrategy, Context, register_strategy

@register_strategy("retrieval", "vector", "Vector-based retrieval")
class VectorRetrievalStrategy(BaseStrategy):
    def __init__(self, **config):
        super().__init__(config)
        # 初始化向量模型等
    
    async def apply(self, context: Context, **kwargs):
        # 实现检索逻辑
        query = context.user_input
        results = await self.vector_search(query)
        return results
```

## 🔧 高级特性

### 钩子系统

```python
def before_step_hook(context, step_name, step):
    print(f"Before {step_name}")

def after_step_hook(context, step_name, step):
    print(f"After {step_name}")

pipeline.add_hook("before_step", before_step_hook)
pipeline.add_hook("after_step", after_step_hook)
```

### 条件执行

```python
from contextmind.core import ConditionalStep

def should_execute(context):
    return context.get("user_type") == "premium"

step = ConditionalStep(
    step=MyExpensiveStep(),
    condition=should_execute
)
```

### 组合步骤

```python
from contextmind.core import CompositeStep

composite = CompositeStep([
    ValidationStep(),
    NormalizationStep(),
    EnrichmentStep()
])
```

## 📊 监控和调试

### 执行历史

```python
result = await pipeline.execute(context)

# 获取执行历史
history = result.get_history()
for record in history:
    print(f"{record['step']}: {record['data']['duration']}s")
```

### 性能指标

```python
# Pipeline级别
total_time = result.get_metadata("pipeline_duration")

# Step级别
for record in result.get_history():
    step_time = record['data'].get('duration', 0)
    print(f"{record['step']}: {step_time*1000:.2f}ms")
```

## 🎨 扩展示例

### 集成LLM

```python
class MyLLMClient:
    async def generate(self, prompt):
        # 调用LLM API
        response = await call_llm_api(prompt)
        return response

# 使用
pipeline = PipelineBuilder() \
    .add_custom_step("generation", GenerationStep(generator=MyLLMClient())) \
    .build()
```

### 集成向量数据库

```python
@register_strategy("retrieval", "faiss", "FAISS vector retrieval")
class FAISSRetrievalStrategy(BaseStrategy):
    def __init__(self, index_path, **config):
        super().__init__(config)
        self.index = faiss.read_index(index_path)
    
    async def apply(self, context, **kwargs):
        # 向量检索逻辑
        query_vector = embed(context.user_input)
        distances, indices = self.index.search(query_vector, k=5)
        return self.format_results(indices, distances)
```

## 📦 项目结构

```
contextmind/
├── core/                  # 核心框架
│   ├── context.py         # Context和ContextData
│   ├── pipeline.py        # Pipeline和PipelineBuilder
│   ├── registry.py        # 注册表系统
│   ├── base.py            # BaseStep和BaseStrategy
│   └── exceptions.py      # 异常定义
│
├── steps/                 # 标准步骤
│   ├── validation.py      # 验证步骤
│   ├── collection.py      # 收集步骤
│   ├── integration.py     # 整合步骤
│   └── generation.py      # 生成步骤
│
├── strategies/            # 策略实现
│   ├── retrieval.py       # 检索策略
│   └── prompt.py          # Prompt策略
│
└── examples/              # 示例代码
    └── basic_example.py   # 基础示例
```

## 🤝 贡献指南

### 添加新步骤

1. 继承`BaseStep`
2. 实现`execute()`方法
3. 使用`@register_step`装饰器注册

### 添加新策略

1. 继承`BaseStrategy`
2. 实现`apply()`方法
3. 使用`@register_strategy`装饰器注册

## 📄 许可证

MIT License

## 🔗 相关资源

- [框架设计文档](docs/FRAMEWORK_DESIGN.md)
- [集成指南](docs/INTEGRATION_GUIDE.md)
- [API文档](docs/API.md)

---

**ContextMind 2.0** - 构建下一代上下文优化应用的基础设施
