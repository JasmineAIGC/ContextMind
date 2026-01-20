# ContextMind v5.1 最佳实践

## 架构使用

### 1. 使用ContextEngine

✅ **推荐**：使用ContextEngine作为核心

```python
engine = ContextEngine(...)
context_result = await engine.optimize(user_input)
```

❌ **避免**：直接使用Pipeline组件

```python
# 不推荐
collector = ContextCollector(...)
context = await collector.collect(user_input)
```

### 2. 应用层设计

✅ **推荐**：继承BaseApplication

```python
class MyApp(BaseApplication):
    def build_prompt(self, user_input, context):
        return self._build_my_prompt(user_input, context)
```

---

## 上下文优化

### 1. 控制上下文长度

```python
context_result = await engine.optimize(
    user_input,
    max_context_length=2000,
)
```

### 2. 选择性包含

```python
# 只要会话历史
context = await engine.optimize(
    user_input,
    include_session=True,
    include_memory=False,
    include_knowledge=False,
)

# 完整上下文
context = await engine.optimize(
    user_input,
    include_session=True,
    include_memory=True,
    include_knowledge=True,
)
```

### 3. 记忆管理

```python
# 应用层配置
app = MyApp(
    context_engine=engine,
    llm_client=client,
    auto_extract_knowledge=True,
)

# 手动提取
knowledge = await engine.extract_knowledge(auto_store=True)
```

### 4. 植入初始知识

```python
# 初始化时植入
await engine.seed_memory([
    "业务规则1",
    "业务规则2",
    "产品信息",
])
```

---

## Prompt构建

### 1. 结构化Prompt

✅ **推荐**：使用清晰的结构

```python
def build_prompt(self, user_input, context):
    parts = []
    
    # 1. 系统角色
    parts.append(self.system_prompt)
    
    # 2. 业务信息（如果有）
    if self.business_info:
        parts.append(f"\n## 业务信息\n{self.business_info}")
    
    # 3. 长期记忆（重要信息前置）
    if context.long_term_memory:
        memory_text = "\n".join(
            f"- {item.content}"
            for item in context.long_term_memory[:3]
        )
        parts.append(f"\n## 重要信息\n{memory_text}")
    
    # 4. 对话历史
    if context.recent_history:
        history_text = "\n".join(
            f"{msg.role.value}: {msg.content}"
            for msg in context.recent_history[-5:]
        )
        parts.append(f"\n## 对话历史\n{history_text}")
    
    # 5. 当前输入
    parts.append(f"\n## 当前问题\n{user_input}")
    
    return "\n".join(parts)
```

### 2. Lost-in-the-Middle优化

✅ **推荐**：重要信息放在开头和结尾

```python
# 使用RerankingStrategy
from contextmind import RerankingStrategy

optimizer = ContextOptimizer()
# 或在自定义策略中实现重排
```

---

## 错误处理

### 1. 捕获特定异常

✅ **推荐**：针对性处理

```python
try:
    context = await engine.optimize(user_input)
except ValueError as e:
    # 输入验证失败
    logger.error(f"Invalid input: {e}")
    return "抱歉，输入无效"
except Exception as e:
    # 其他错误
    logger.error(f"Optimization failed: {e}")
    # 回退方案
    return default_response
```

### 2. 优雅降级

✅ **推荐**：提供回退方案

```python
async def process_turn(self, user_input):
    try:
        # 尝试完整流程
        context = await self.engine.optimize(user_input)
        prompt = self.build_prompt(user_input, context)
        response = self.llm_client.generate(prompt)
    except Exception as e:
        logger.warning(f"Full process failed, using fallback: {e}")
        # 回退：使用简单Prompt
        prompt = f"{self.system_prompt}\n{user_input}"
        response = self.llm_client.generate(prompt)
    
    return response
```

---

## 性能优化

### 1. 异步并发

✅ **推荐**：充分利用异步

```python
# 并发执行独立操作
import asyncio

async def batch_process(inputs):
    tasks = [engine.optimize(inp) for inp in inputs]
    results = await asyncio.gather(*tasks)
    return results
```

### 2. 合理设置参数

✅ **推荐**：根据场景调整

```python
# 快速响应场景
engine = ContextEngine(
    max_recent_events=5,  # 较少历史
)
context = await engine.optimize(
    user_input,
    max_context_length=1000,  # 较短上下文
)

# 深度对话场景
engine = ContextEngine(
    max_recent_events=20,  # 较多历史
)
context = await engine.optimize(
    user_input,
    max_context_length=5000,  # 较长上下文
)
```

---

## 测试

### 1. 单元测试

✅ **推荐**：测试各个组件

```python
import pytest
from contextmind import ContextEngine, Message, MessageRole

@pytest.mark.asyncio
async def test_optimize():
    engine = ContextEngine(
        app_name="test",
        user_id="test-user",
    )
    
    # 添加历史
    await engine.update("你好", "你好，有什么可以帮助你？")
    
    # 测试优化
    context = await engine.optimize("我想了解产品")
    
    assert len(context.recent_history) > 0
    assert context.recent_history[0].role == MessageRole.USER
```

### 2. 集成测试

✅ **推荐**：测试完整流程

```python
@pytest.mark.asyncio
async def test_full_conversation():
    engine = ContextEngine(...)
    app = MyApp(context_engine=engine, ...)
    
    # 第一轮
    response1 = await app.process_turn("你好")
    assert response1
    
    # 第二轮（测试上下文）
    response2 = await app.process_turn("刚才我问了什么？")
    assert "你好" in response2
```

---

## 日志

### 1. 配置日志级别

✅ **推荐**：开发和生产使用不同级别

```python
# 开发环境
setup_logging(level=DEBUG, log_to_console=True)

# 生产环境
setup_logging(level=INFO, log_file="app.log", log_to_console=False)
```

### 2. 使用结构化日志

✅ **推荐**：记录关键信息

```python
logger.info(
    f"Context optimized: "
    f"user={user_id}, "
    f"history={len(context.recent_history)}, "
    f"memory={len(context.long_term_memory)}"
)
```

---

## 部署

### 1. 环境变量

✅ **推荐**：使用环境变量配置

```bash
# .env 文件
QWEN3_API_KEY=your-api-key
QWEN3_MODEL=Qwen3-32B
QWEN3_BASE_URL=https://api.example.com
QWEN3_TEMPERATURE=0.6
```

```python
# 代码中
from dotenv import load_dotenv
load_dotenv()

client = Client(config=ClientConfig.from_env())
```

### 2. 资源管理

✅ **推荐**：适当清理资源

```python
# 定期清理旧会话
if turn_count % 100 == 0:
    await engine.clear_session()

# 提取知识后可以清理部分历史
await engine.extract_knowledge(auto_store=True)
```

---

## 常见陷阱

### ❌ 陷阱1：忘记await

```python
# 错误
context = engine.optimize(user_input)  # 返回coroutine对象

# 正确
context = await engine.optimize(user_input)
```

### ❌ 陷阱2：在非异步函数中调用

```python
# 错误
def my_function():
    context = await engine.optimize(user_input)  # SyntaxError

# 正确
async def my_function():
    context = await engine.optimize(user_input)
```

### ❌ 陷阱3：过度优化导致信息丢失

```python
# 可能有问题
context = await engine.optimize(
    user_input,
    max_context_length=100,  # 太短了！
)

# 更好
context = await engine.optimize(
    user_input,
    max_context_length=2000,  # 合理的长度
)
```

---

## 总结

1. **分层使用**：应用层 → 引擎层 → 流水线层 → 策略层
2. **异步优先**：充分利用async/await
3. **参数控制**：合理设置上下文长度和历史数量
4. **错误处理**：提供回退方案
5. **日志记录**：记录关键操作
6. **测试覆盖**：单元测试 + 集成测试
