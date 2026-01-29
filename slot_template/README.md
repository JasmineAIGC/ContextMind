# 槽位模板上下文优化方案 (Slot Template Baseline)

## 概述

槽位模板方案是一个**简单的上下文优化基础版本**，作为与 ContextMind 框架对比实验的 baseline。

### 🆕 新增：对话状态追踪 (DST)

基于 **ACL 2023 论文** 《ChatGPT for Zero-shot Dialogue State Tracking》，我们新增了完整的对话状态追踪实现。

**两种方式对比：**

| 方式 | 特点 | 适用场景 |
|------|------|---------|
| **基础槽位模板** | 简单、快速、3个固定槽位 | 简单对话、快速原型 |
| **对话状态追踪 (DST)** | 完整、可扩展、论文级实现 | 复杂多轮对话、精确状态追踪 |

详细文档请参考：[DST 文档](../docs/DST_DOCUMENTATION.md)

### 核心思路

通过预定义的槽位模板，从对话历史中提取关键信息填充槽位，生成指导当前回复的提示词。

```
对话历史 → 意图提取 → 槽位填充 → 生成提示词 → LLM 回复
```

## 与 ContextMind 的区别

| 特性 | 槽位模板 (Baseline) | ContextMind (上下文工程) |
|------|-------------------|------------------------|
| 复杂度 | ⭐ 简单 | ⭐⭐⭐⭐ 复杂 |
| 记忆库 | ❌ 无 | ✅ 有 (长期记忆) |
| 上下文检索 | ❌ 无 | ✅ 有 (语义检索) |
| 上下文压缩 | ❌ 无 | ✅ 有 (智能压缩) |
| 上下文重排序 | ❌ 无 | ✅ 有 (重排序优化) |
| 依赖范围 | 仅当前会话 | 跨会话记忆 + 历史 |
| 适用场景 | 简单对话、baseline | 复杂应用、生产环境 |

## 核心组件

### 1. SlotTemplateEngine (引擎)

核心引擎，提供简洁的 API。

```python
from slot_template import SlotTemplateEngine

# 初始化引擎
engine = SlotTemplateEngine(
    llm_client=your_llm_client,  # 可选，用于智能意图提取
    use_llm_extraction=False     # False: 规则提取, True: LLM 提取
)

# 处理用户输入
result = await engine.process(
    user_input="今天天气怎么样？",
    system_prompt_template=SYSTEM_PROMPT
)

# 获取填充后的提示词
prompt = result['filled_prompt']
```

### 2. IntentExtractor (意图提取器)

从对话历史中提取用户意图和关键信息。

**支持两种提取方式：**

- **规则提取**：基于关键词和模式匹配（快速，但简单）
- **LLM 提取**：使用 LLM 智能分析（准确，但需要 API 调用）

```python
from slot_template import IntentExtractor

extractor = IntentExtractor(llm_client=None)  # None = 规则提取

slot_values = await extractor.extract_from_history(
    messages=conversation_history,
    current_input="你好"
)

# 返回:
# {
#     "user_intent": "用户意图：问候",
#     "conversation_context": "这是对话的开始",
#     "key_info": "暂无明显关键信息"
# }
```

### 3. TemplateManager (模板管理器)

管理槽位模板的定义和填充。

**预定义槽位：**

| 槽位名称 | 描述 | 默认值 |
|---------|------|--------|
| `user_intent` | 用户当前意图 | "用户正在进行日常对话" |
| `conversation_context` | 对话上下文摘要 | "暂无对话历史" |
| `key_info` | 关键信息（实体、偏好等） | "暂无关键信息" |

```python
from slot_template import TemplateManager, SlotTemplate

manager = TemplateManager()

# 设置槽位值
manager.set_slot_value("user_intent", "用户想要咨询产品")

# 填充模板
template = """
用户意图：{slot_user_intent}
对话上下文：{slot_conversation_context}
关键信息：{slot_key_info}
"""

filled = manager.fill_template(template)
```

## 实现逻辑

### 工作流程

```
┌─────────────────┐
│  用户输入        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  意图提取器      │ ← 对话历史
│ IntentExtractor │
└────────┬────────┘
         │
         ▼
    槽位信息
    {
      user_intent: "...",
      conversation_context: "...",
      key_info: "..."
    }
         │
         ▼
┌─────────────────┐
│  模板管理器      │
│ TemplateManager │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  填充后的提示词  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   LLM 调用      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   生成回复      │
└─────────────────┘
```

### 详细步骤

**步骤 1：意图提取**

从对话历史中提取：
- 用户意图（基于关键词或 LLM 分析）
- 对话上下文（最近几轮对话摘要）
- 关键信息（实体、数字、偏好等）

**步骤 2：槽位填充**

将提取的信息填充到预定义的槽位：
```python
{
  "user_intent": "用户意图：咨询",
  "conversation_context": "已进行 3 轮对话。用户最近提到：产品价格...",
  "key_info": "涉及数字: 100, 200; 提到实体: 张三"
}
```

**步骤 3：生成提示词**

使用槽位值填充系统提示词模板：
```
你是智能对话助手。

基于以下槽位信息进行回复：

用户意图：用户意图：咨询
对话上下文：已进行 3 轮对话。用户最近提到：产品价格...
关键信息：涉及数字: 100, 200; 提到实体: 张三

## 当前用户问题
产品有什么优惠吗？

请基于上述槽位信息给出回复：
```

**步骤 4：LLM 生成回复**

将填充后的提示词发送给 LLM，生成回复。

## 使用示例

### 完整示例

```python
import asyncio
from slot_template import SlotTemplateEngine
from prompts import SLOT_TEMPLATE_SYSTEM_PROMPT

async def main():
    # 1. 初始化引擎
    engine = SlotTemplateEngine(
        llm_client=None,  # 使用规则提取
        use_llm_extraction=False
    )
    
    # 2. 模拟多轮对话
    turns = [
        ("你好", "您好！有什么可以帮助您的吗？"),
        ("我想了解产品", "好的，我们有多种产品可供选择。您对哪类产品感兴趣？"),
        ("价格是多少", None)  # 当前轮，需要生成回复
    ]
    
    # 3. 添加历史对话
    for user_msg, assistant_msg in turns[:-1]:
        engine.add_message("user", user_msg)
        if assistant_msg:
            engine.add_message("assistant", assistant_msg)
    
    # 4. 处理当前输入
    current_input = turns[-1][0]
    result = await engine.process(
        user_input=current_input,
        system_prompt_template=SLOT_TEMPLATE_SYSTEM_PROMPT
    )
    
    # 5. 查看槽位值
    print("槽位值：")
    for slot_name, value in result['slot_values'].items():
        print(f"  {slot_name}: {value}")
    
    # 6. 查看填充后的提示词
    print("\n填充后的提示词：")
    print(result['filled_prompt'])
    
    # 7. 使用提示词调用 LLM（示例）
    # response = await your_llm.chat(result['filled_prompt'])
    
    # 8. 添加本轮对话到历史
    engine.add_message("user", current_input)
    # engine.add_message("assistant", response)

if __name__ == "__main__":
    asyncio.run(main())
```

### 与 ContextMind 对比示例

**槽位模板方式：**
```python
from slot_template import SlotTemplateEngine

engine = SlotTemplateEngine()
result = await engine.process("你好")
prompt = result['filled_prompt']
# 调用 LLM
response = await llm.chat(prompt)
engine.add_message("user", "你好")
engine.add_message("assistant", response)
```

**ContextMind 方式：**
```python
from contextmind import ContextEngine

engine = ContextEngine(app_name="demo", user_id="user-1")
# 1. 优化上下文
context = await engine.optimize("你好")
# 2. 调用 LLM
response = await llm.chat(context.to_prompt())
# 3. 处理响应并更新记忆
await engine.handle_response("你好", response, context)
```

## 优缺点分析

### 优点

✅ **简单易懂**：逻辑清晰，易于理解和维护  
✅ **快速实现**：代码量少，实现成本低  
✅ **无依赖**：不需要向量数据库、嵌入模型等  
✅ **轻量级**：资源消耗小，适合简单场景  
✅ **可控性强**：槽位定义明确，行为可预测

### 缺点

❌ **无长期记忆**：仅基于当前会话，无法跨会话记忆  
❌ **上下文有限**：只能利用有限的对话历史  
❌ **提取能力弱**：规则提取简单，LLM 提取需要额外调用  
❌ **扩展性差**：槽位固定，难以适应复杂场景  
❌ **无优化机制**：不进行压缩、重排序等优化

## 适用场景

适合作为：
- ✅ **对比实验的 baseline**：与 ContextMind 对比效果
- ✅ **简单对话系统**：不需要长期记忆的场景
- ✅ **快速原型**：快速验证想法
- ✅ **学习示例**：理解上下文优化的基本思路

不适合：
- ❌ 需要长期记忆的应用
- ❌ 复杂的对话管理
- ❌ 生产环境的关键应用

## API 参考

### SlotTemplateEngine

**初始化**
```python
SlotTemplateEngine(
    llm_client: Optional[Any] = None,
    use_llm_extraction: bool = False
)
```

**方法**

- `async process(user_input, system_prompt_template=None)` - 处理用户输入
- `add_message(role, content)` - 添加消息到历史
- `clear_history()` - 清空历史
- `get_slot_value(slot_name)` - 获取槽位值
- `get_all_slots()` - 获取所有槽位值
- `async generate_prompt(user_input, system_prompt_template)` - 生成完整提示词

### IntentExtractor

**初始化**
```python
IntentExtractor(llm_client: Optional[Any] = None)
```

**方法**

- `async extract_from_history(messages, current_input)` - 提取槽位信息

### TemplateManager

**方法**

- `get_slot(slot_name)` - 获取槽位定义
- `set_slot_value(slot_name, value)` - 设置槽位值
- `get_slot_value(slot_name)` - 获取槽位值
- `fill_template(template)` - 填充模板
- `get_all_slot_values()` - 获取所有槽位值
- `clear()` - 清空槽位值

## 总结

槽位模板方案是一个**简单、直接的上下文优化方法**，适合作为 baseline 与 ContextMind 进行对比。

虽然功能有限，但它清晰地展示了上下文优化的基本思路：
1. 从历史中提取信息
2. 结构化表示上下文
3. 指导 LLM 生成回复

在实际应用中，应根据具体需求选择合适的方案：
- 简单场景 → 槽位模板
- 复杂场景 → ContextMind 上下文工程

---

## 🆕 对话状态追踪 (DST)

### 概述

基于 **ACL 2023 论文** 《ChatGPT for Zero-shot Dialogue State Tracking》的完整实现。

采用 Zero-shot 方式，通过精心设计的 Prompt 实现对话状态追踪。

### 快速开始

```python
from slot_template import DialogueStateTracker, PromptManager
import asyncio

async def main():
    # 1. 创建提示词管理器
    pm = PromptManager(domain="restaurant")
    pm.add_slot("restaurant_name", "餐厅名称")
    pm.add_slot("food_type", "菜系", ["中餐", "西餐", "日料"])
    
    # 2. 初始化追踪器
    tracker = DialogueStateTracker(
        llm_client=None,  # 可选 LLM 客户端
        prompt_manager=pm
    )
    tracker.reset_dialogue()
    
    # 3. 处理对话
    state = await tracker.process_turn(
        "您好，要预订吗？",
        "是的，订一家中餐厅"
    )
    print(state)  # {"food_type": "中餐", "intent": "预订"}
    
    state = await tracker.process_turn(
        "几位？",
        "4个人"
    )
    print(state)  # {"food_type": "中餐", "intent": "预订", "quantity": "4"}

asyncio.run(main())
```

### 运行演示

```bash
# 运行完整的 DST 演示
python dst_demo.py

# 选择演示模式：
# 1 - 基础对话状态追踪
# 2 - Prompt 设计展示
# 3 - 响应解析演示
# 4 - 对比演示
```

### 核心特性

✅ **Zero-shot**: 无需微调，即插即用  
✅ **可扩展**: 支持自定义槽位和领域  
✅ **累积更新**: DS_t = update(DS_{t-1}, updates)  
✅ **共指消解**: 通过上下文历史  
✅ **鲁棒解析**: 处理各种 JSON 格式  
✅ **幻觉过滤**: 只保留有效槽位  

### 详细文档

完整的 DST 文档请参考：[DST 文档](../docs/DST_DOCUMENTATION.md)

### DST vs 基础槽位模板

| 特性 | 基础槽位模板 | DST |
|------|------------|-----|
| 槽位定义 | 3个固定槽位 | 可扩展本体 |
| 状态管理 | 无状态累积 | 累积式更新 |
| 共指消解 | ❌ | ✅ |
| 值归一化 | ❌ | ✅ |
| 幻觉过滤 | ❌ | ✅ |
| 分类约束 | ❌ | ✅ |
| 适用场景 | 简单对话 | 复杂多轮对话 |

