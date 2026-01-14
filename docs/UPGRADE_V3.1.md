# ContextMind v3.1 架构升级文档

## 概述

ContextMind v3.1 在 v3.0 的基础上进行了全面升级，增强了功能、兼容性和扩展性，使其能够轻松集成到任意对话系统中。

## 新增功能

### 1. 适配器层（Adapter Layer）

适配器层提供了标准化接口，支持将 ContextMind 无缝集成到各种对话系统中。

#### 核心组件

**BaseAdapter** - 适配器基类
- 定义了标准的集成接口
- 支持钩子函数（hooks）
- 提供消息格式转换
- 自动上下文注入

**OpenAIAdapter** - OpenAI 兼容适配器
- 支持 OpenAI Chat Completions API 格式
- 自动处理多轮对话
- 支持多模态消息

**LangChainAdapter** - LangChain 框架适配器
- 兼容 LangChain 的对话链
- 支持字符串和对象格式
- 无缝集成现有 LangChain 应用

**CustomAdapter** - 自定义适配器
- 完全可定制的集成逻辑
- 支持自定义转换函数
- 灵活的处理流程

#### 使用示例

```python
from contextmind import ContextEngine, OpenAIAdapter, DialogContext

# 创建引擎
engine = ContextEngine(
    app_name="my-app",
    user_id="user-123"
)

# 创建适配器
adapter = OpenAIAdapter(engine=engine)

# 处理对话
response = await adapter.process(
    user_input="你好",
    context=DialogContext(system_prompt="你是智能助手")
)
```

#### 钩子函数

适配器支持在关键流程点注册钩子函数：

```python
# 注册前置钩子
def before_optimize(user_input, context):
    print(f"优化前: {user_input}")

adapter.register_hook('before_optimize', before_optimize)

# 支持的钩子事件
- before_optimize: 上下文优化前
- after_optimize: 上下文优化后
- before_generate: 生成回复前
- after_generate: 生成回复后
```

### 2. 工具层（Utils Layer）

提供各种实用工具，增强框架的可用性和可观测性。

#### ConfigManager - 配置管理器

```python
from contextmind.utils import ConfigManager

config_mgr = ConfigManager(config_path="config.json")

# 加载配置
config = config_mgr.load()

# 验证配置
is_valid = config_mgr.validate()

# 保存配置
config_mgr.save(config)
```

#### PerformanceMonitor - 性能监控器

```python
from contextmind.utils import PerformanceMonitor

monitor = PerformanceMonitor()

# 开始监控
monitor.start_turn()

# ... 处理对话 ...

# 结束监控
metrics = monitor.end_turn()

# 获取摘要
print(monitor.get_summary())
```

监控指标包括：
- 总耗时
- 优化耗时
- 检索耗时
- 生成耗时
- 上下文长度
- 历史消息数
- 记忆条目数

#### ContextVisualizer - 上下文可视化

```python
from contextmind.utils import ContextVisualizer

# 文本格式
text = ContextVisualizer.render_text(context_result)

# JSON格式
json_data = ContextVisualizer.render_json(context_result)

# Markdown格式
markdown = ContextVisualizer.render_markdown(context_result)

# 摘要
summary = ContextVisualizer.render_summary(context_result)
```

#### EventBus - 事件系统

```python
from contextmind.utils import EventBus, Event

bus = EventBus()

# 订阅事件
def on_optimize(event):
    print(f"上下文已优化: {event.data}")

bus.subscribe('context_optimized', on_optimize)

# 发布事件
bus.publish('context_optimized', {'length': 100})

# 异步发布
await bus.publish_async('context_optimized', {'length': 100})

# 查看历史
history = bus.get_history('context_optimized', limit=10)
```

### 3. 增强的数据模型

#### DialogMessage - 标准化消息格式

```python
from contextmind.adapters import DialogMessage

msg = DialogMessage(
    role='user',
    content='你好',
    images=['http://example.com/image.jpg'],  # 多模态支持
    files=['document.pdf'],
    metadata={'source': 'web'}
)
```

#### DialogContext - 对话上下文容器

```python
from contextmind.adapters import DialogContext

context = DialogContext(
    messages=[msg1, msg2],
    system_prompt='你是智能助手',
    metadata={'session_id': '123'}
)
```

## 架构对比

### v3.0 架构
```
应用层 → 引擎层 → 流水线层 → 策略层
```

### v3.1 架构
```
应用层 ↔ 适配器层 → 引擎层 → 流水线层 → 策略层
                 ↓
              工具层 (配置、监控、可视化、事件)
```

## 集成示例

### 集成到 OpenAI 风格的应用

```python
import asyncio
from contextmind import ContextEngine, OpenAIAdapter, DialogContext

async def chatbot():
    # 创建引擎
    engine = ContextEngine(
        app_name="chatbot",
        user_id="user-001"
    )
    
    # 创建适配器
    adapter = OpenAIAdapter(engine=engine)
    
    # 对话循环
    context = DialogContext(
        system_prompt="你是一个友好的聊天机器人"
    )
    
    while True:
        user_input = input("你: ")
        if user_input.lower() in ['quit', 'exit']:
            break
        
        response = await adapter.process(user_input, context)
        print(f"机器人: {response.content}")

asyncio.run(chatbot())
```

### 集成到自定义对话系统

```python
from contextmind import ContextEngine, CustomAdapter

# 定义自定义转换函数
def my_to_standard(msg):
    return DialogMessage(
        role=msg.get('author'),
        content=msg.get('text')
    )

def my_from_standard(msg):
    return {
        'author': msg.role,
        'text': msg.content,
        'timestamp': msg.timestamp
    }

# 创建自定义适配器
adapter = CustomAdapter(
    engine=engine,
    to_standard_converter=my_to_standard,
    from_standard_converter=my_from_standard
)
```

## 最佳实践

### 1. 选择合适的适配器

- **OpenAIAdapter**: 适用于 OpenAI API 兼容的系统
- **LangChainAdapter**: 适用于 LangChain 应用
- **CustomAdapter**: 适用于特殊需求或自定义系统

### 2. 使用性能监控

在生产环境中始终启用性能监控：

```python
monitor = PerformanceMonitor()

for turn in conversation:
    monitor.start_turn()
    # ... 处理对话 ...
    metrics = monitor.end_turn()
    
    # 记录到日志或监控系统
    log_metrics(metrics)
```

### 3. 利用事件系统

使用事件系统实现解耦的组件通信：

```python
bus = EventBus()

# 在适配器中发布事件
bus.publish('message_received', user_input)
bus.publish('response_generated', response)

# 其他组件订阅事件
bus.subscribe('message_received', analytics.track_message)
bus.subscribe('response_generated', quality.evaluate_response)
```

### 4. 配置管理

使用配置管理器集中管理配置：

```python
config_mgr = ConfigManager('config.json')
config = config_mgr.load()

engine = ContextEngine(**config.get('engine_params'))
```

## 兼容性

ContextMind v3.1 完全向后兼容 v3.0，原有代码无需修改即可继续使用。新增功能作为可选模块提供。

## 升级指南

从 v3.0 升级到 v3.1：

1. 更新导入语句（可选）：
```python
# 新增导入
from contextmind import OpenAIAdapter, PerformanceMonitor
```

2. 使用适配器包装引擎（可选）：
```python
# v3.0 方式仍然支持
engine = ContextEngine(...)

# v3.1 新方式（可选）
adapter = OpenAIAdapter(engine=engine)
```

3. 启用监控和可视化（推荐）：
```python
monitor = PerformanceMonitor()
visualizer = ContextVisualizer()
```

## 总结

v3.1 升级带来的主要改进：

✅ **通用适配器层** - 支持集成到任意对话系统
✅ **性能监控** - 全面的性能追踪和分析
✅ **上下文可视化** - 多格式的可视化输出
✅ **事件系统** - 解耦的组件通信
✅ **配置管理** - 统一的配置加载和验证
✅ **钩子机制** - 灵活的扩展点
✅ **多模态支持** - 支持图片、文件等多模态消息
✅ **完全兼容** - 向后兼容 v3.0

这些改进使 ContextMind 成为一个功能全面、兼容性好、扩展性强的上下文优化框架，可以轻松集成到任何对话系统中。
