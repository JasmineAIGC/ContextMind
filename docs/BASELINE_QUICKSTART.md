# 槽位模板快速入门指南

## 5 分钟快速开始

### 1. 基础使用

```python
import asyncio
from baseline import SlotTemplateEngine
from prompts import BASELINE_SYSTEM_PROMPT

async def basic_example():
    # 创建引擎
    engine = SlotTemplateEngine()
    
    # 添加对话历史
    engine.add_message("user", "我叫张三")
    engine.add_message("assistant", "很高兴认识你，张三！")
    
    # 处理当前输入
    result = await engine.process(
        user_input="你还记得我叫什么吗？",
        system_prompt_template=BASELINE_SYSTEM_PROMPT
    )
    
    # 查看结果
    print("槽位值：", result['slot_values'])
    print("提示词：", result['filled_prompt'])

asyncio.run(basic_example())
```

### 2. 运行演示

```bash
# 基础演示
python baseline_demo.py
# 选择: 1

# 对比演示  
python baseline_demo.py
# 选择: 3

# 完整对比实验
python comparison_experiment.py
# 选择: 1
```

### 3. 核心概念

**三个槽位**：
- `user_intent`: 用户意图
- `conversation_context`: 对话上下文  
- `key_info`: 关键信息

**两种提取方式**：
- 规则提取（默认）：快速，无需 API
- LLM 提取（可选）：准确，需要 API

### 4. 与 ContextMind 对比

```python
# 槽位模板 - 简单
from baseline import SlotTemplateEngine

engine = SlotTemplateEngine()
result = await engine.process("你好")
# ✅ 简单快速
# ❌ 无长期记忆

# ContextMind - 完整
from contextmind import ContextEngine

engine = ContextEngine(app_name="app", user_id="user1")
context = await engine.optimize("你好")
# ✅ 功能完整
# ✅ 长期记忆
```

### 5. 适用场景

**使用槽位模板**：
- ✅ 快速原型
- ✅ 简单对话
- ✅ Baseline 实验
- ✅ 学习示例

**使用 ContextMind**：
- ✅ 生产环境
- ✅ 复杂应用
- ✅ 长期记忆需求
- ✅ 最佳效果

## 详细文档

- [槽位模板实现文档](BASELINE_IMPLEMENTATION.md)
- [槽位模板模块文档](BASELINE_README.md)
- [主项目文档](../README.md)
