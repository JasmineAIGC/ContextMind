# 模板填槽位优化方式 - 实现逻辑文档

## 一、概述

### 1.1 设计目标

本实现提供了一种**基于提示词模板和意图提取**的上下文优化方式，核心特点是：

- ✅ **非侵入性**：不修改 ContextMind 框架的任何核心代码
- ✅ **可选使用**：用户可以选择使用或不使用此功能
- ✅ **独立运行**：可以独立使用，也可以与 ContextEngine 配合
- ✅ **策略模式**：作为 OptimizationStrategy 的一个实现

### 1.2 核心思想

```
每轮对话时：
1. 从对话历史中提取用户意图
2. 识别对话主题和上下文
3. 将提取的信息填入预定义的模板槽位
4. 生成优化后的提示词，指导 LLM 回复
```

## 二、架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    ContextMind 框架                           │
│  ┌────────────────────────────────────────────────────┐     │
│  │            ContextEngine (核心引擎)                  │     │
│  │  - optimize()                                       │     │
│  │  - update()                                         │     │
│  │  - handle_response()                                │     │
│  └────────────────────────────────────────────────────┘     │
│                         ↓                                    │
│  ┌────────────────────────────────────────────────────┐     │
│  │         Pipeline 组件 (可插拔)                        │     │
│  │  - InputPreprocessor                                │     │
│  │  - MemoryBank                                       │     │
│  │  - ContextCompressor                                │     │
│  │  - ContextReorderer                                 │     │
│  │  - ResponseHandler                                  │     │
│  └────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│           模板优化方式 (独立的可选组件)                        │
│  ┌────────────────────────────────────────────────────┐     │
│  │      TemplateBasedOptimization (优化策略)           │     │
│  │                                                      │     │
│  │  ┌──────────────────┐    ┌───────────────────┐    │     │
│  │  │ IntentExtractor  │    │ PromptTemplate    │    │     │
│  │  │ (意图提取器)      │    │ (提示词模板)       │    │     │
│  │  │                  │    │                   │    │     │
│  │  │ - 规则提取       │    │ - 槽位定义         │    │     │
│  │  │ - LLM提取        │    │ - 槽位填充         │    │     │
│  │  └──────────────────┘    └───────────────────┘    │     │
│  └────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 非侵入式设计

**关键原则**：模板优化方式是一个**可选的附加组件**，不会影响框架原有功能。

#### 2.2.1 代码组织

```
contextmind/
├── core/
│   ├── prompt_template.py      # 新增：模板系统（独立模块）
│   ├── strategies.py           # 原有：策略基类
│   └── __init__.py             # 修改：仅添加导出，不修改原有代码
│
├── pipeline/
│   ├── intent_extractor.py     # 新增：意图提取（独立模块）
│   ├── template_optimizer.py   # 新增：优化策略（独立模块）
│   └── __init__.py             # 修改：仅添加导出，不修改原有代码
│
└── engine.py                    # 未修改：核心引擎保持不变
```

#### 2.2.2 接口设计

遵循**开闭原则**：对扩展开放，对修改封闭

```python
# OptimizationStrategy 是框架已有的抽象基类
class OptimizationStrategy(ABC):
    @abstractmethod
    async def optimize(self, context: ProcessedContext):
        pass

# TemplateBasedOptimization 实现这个接口，不修改基类
class TemplateBasedOptimization(OptimizationStrategy):
    async def optimize(self, context: ProcessedContext) -> ContextResult:
        # 实现模板优化逻辑
        ...
```

## 三、核心组件实现

### 3.1 PromptTemplate（提示词模板）

**位置**：`contextmind/core/prompt_template.py`

#### 3.1.1 设计思路

提示词模板使用**槽位（slot）**机制，类似于字符串模板，但更强大：

```python
template_text = """你是智能助手。

用户意图: {intent}
对话主题: {topic}
相关上下文: {context}

请基于以上信息回复。"""
```

#### 3.1.2 核心功能

1. **自动槽位提取**
   ```python
   # 从模板文本中自动识别 {slot_name} 格式的槽位
   pattern = r'\{(\w+)\}'
   slots = re.findall(pattern, template_text)
   ```

2. **槽位定义**
   ```python
   @dataclass
   class TemplateSlot:
       name: str                    # 槽位名称
       description: str = ""        # 槽位说明
       default_value: str = ""      # 默认值
       required: bool = False       # 是否必填
       slot_type: str = "intent"    # 类型标识
   ```

3. **槽位填充**
   ```python
   def fill_slots(self, slot_values: Dict[str, str], strict: bool = False):
       # 1. 验证必填槽位
       # 2. 应用默认值
       # 3. 替换模板中的占位符
       filled_text = template_text
       for slot_name, value in slot_values.items():
           filled_text = filled_text.replace(f"{{{slot_name}}}", value)
       return filled_text
   ```

4. **槽位验证**
   ```python
   def validate_slots(self, slot_values: Dict[str, str]):
       # 检查必填槽位是否都提供了值
       # 检查是否有未定义的槽位
       return is_valid, error_messages
   ```

#### 3.1.3 使用示例

```python
# 创建模板
template = PromptTemplate(
    template_id="chat",
    name="对话模板",
    template_text="意图: {intent}, 主题: {topic}"
)

# 填充槽位
result = template.fill_slots({
    'intent': '询问天气',
    'topic': '天气查询'
})
# 输出: "意图: 询问天气, 主题: 天气查询"
```

### 3.2 IntentExtractor（意图提取器）

**位置**：`contextmind/pipeline/intent_extractor.py`

#### 3.2.1 设计思路

从对话历史中提取**结构化信息**，用于填充模板槽位：

- **用户意图**：用户想要做什么
- **对话主题**：正在讨论的话题
- **上下文摘要**：简洁的对话上下文

#### 3.2.2 双模式实现

**模式1：规则提取器（IntentExtractor）**

优点：快速、不需要 LLM、无 API 成本
适用：实时场景、对准确度要求不太高的场景

```python
class IntentExtractor:
    def __init__(self):
        # 定义关键词规则
        self.question_keywords = ['什么', '怎么', '如何', '为什么', ...]
        self.task_keywords = ['帮我', '请', '能否', ...]
        self.greeting_keywords = ['你好', 'hello', 'hi', ...]
        
    async def extract_intent(self, messages: List[Message]):
        # 1. 获取最新用户消息
        latest = messages[-1].content
        
        # 2. 关键词匹配
        if any(kw in latest for kw in self.question_keywords):
            return ExtractedIntent("question", "用户提出问题", 0.85)
        # ... 其他规则
```

**模式2：LLM提取器（LLMIntentExtractor）**

优点：准确度高、理解深度更好
适用：离线处理、对准确度要求高的场景

```python
class LLMIntentExtractor(IntentExtractor):
    async def extract_intent(self, messages: List[Message]):
        # 1. 准备对话历史
        conversation = "\n".join([f"{m.role}: {m.content}" for m in messages])
        
        # 2. 构建提示词
        prompt = f"请分析对话，提取用户意图：\n{conversation}"
        
        # 3. 调用 LLM
        response = await self.llm_client.generate_async(prompt)
        
        # 4. 返回结果
        return ExtractedIntent("llm_extracted", response, 0.95)
```

#### 3.2.3 提取的信息类型

1. **意图类型识别**
   - greeting（问候）
   - question（提问）
   - task_request（任务请求）
   - emotion_*（情感表达）
   - general_chat（一般对话）

2. **主题提取**
   ```python
   async def extract_topic(self, messages: List[Message]):
       # 从最新消息中提取关键词作为主题
       latest = messages[-1].content
       words = extract_keywords(latest)
       return ' '.join(words[:5])  # 返回前5个关键词
   ```

3. **上下文摘要**
   ```python
   async def extract_context_summary(self, messages: List[Message]):
       # 总结最近几轮对话
       recent = messages[-4:]
       summary = []
       for msg in recent:
           summary.append(f"{msg.role}: {msg.content[:30]}...")
       return "; ".join(summary)
   ```

### 3.3 TemplateBasedOptimization（优化策略）

**位置**：`contextmind/pipeline/template_optimizer.py`

#### 3.3.1 工作流程

```
输入: ProcessedContext (包含对话历史和长期记忆)
  ↓
步骤1: 从 ContextItem 转换为 Message 对象
  ↓
步骤2: 使用 IntentExtractor 提取意图、主题、上下文
  ↓
步骤3: 准备槽位值字典
  slot_values = {
      'intent': 提取的意图,
      'topic': 提取的主题,
      'context': 上下文摘要
  }
  ↓
步骤4: 使用 PromptTemplate 填充槽位
  filled_template = template.fill_slots(slot_values)
  ↓
步骤5: 创建新的 ContextItem 包含填充后的模板
  ↓
步骤6: 可选保留部分原始记忆项
  ↓
输出: ContextResult (优化后的上下文)
```

#### 3.3.2 核心代码逻辑

```python
class TemplateBasedOptimization(OptimizationStrategy):
    def __init__(self, template=None, llm_client=None, use_llm_extraction=False):
        # 使用默认模板或自定义模板
        self.template = template or DEFAULT_CHAT_TEMPLATE
        
        # 选择提取器
        if use_llm_extraction and llm_client:
            self.intent_extractor = LLMIntentExtractor(llm_client)
        else:
            self.intent_extractor = IntentExtractor()
    
    async def optimize(self, context: ProcessedContext) -> ContextResult:
        # 1. 提取对话历史
        history_items = [item for item in context.items 
                        if item.source == ContextSource.HISTORY]
        messages = self._convert_items_to_messages(history_items)
        
        # 2. 提取意图、主题、上下文
        intent = await self.intent_extractor.extract_intent(messages)
        topic = await self.intent_extractor.extract_topic(messages)
        context_summary = await self.intent_extractor.extract_context_summary(messages)
        
        # 3. 填充模板
        slot_values = {
            'intent': intent.description,
            'topic': topic,
            'context': context_summary,
        }
        filled_template = self.template.fill_slots(slot_values)
        
        # 4. 创建优化结果
        template_item = ContextItem(
            content=filled_template,
            source=ContextSource.MEMORY,
            score=intent.confidence,
            metadata={
                'type': 'template_optimization',
                'intent_type': intent.intent_type,
                'slot_values': slot_values,
            }
        )
        
        # 5. 可选：保留部分原始记忆
        memory_items = [item for item in context.items 
                       if item.source == ContextSource.MEMORY]
        
        # 6. 返回结果
        return ContextResult(
            items=[template_item] + memory_items[:5],
            compressed=True,
            metadata={'optimization_method': 'template_based'}
        )
```

## 四、与框架的集成方式

### 4.1 集成层次

模板优化方式提供**三种使用层次**：

#### 层次1：完全独立使用

```python
from contextmind.pipeline import TemplateBasedOptimization
from contextmind.core import ProcessedContext, ContextItem

# 直接使用，不依赖 ContextEngine
optimizer = TemplateBasedOptimization()

# 准备上下文
context = ProcessedContext(items=[...])

# 执行优化
result = await optimizer.optimize(context)
```

#### 层次2：后处理使用（推荐）

```python
from contextmind import ContextEngine
from contextmind.pipeline import TemplateBasedOptimization
from contextmind.core import ProcessedContext

# 使用 ContextEngine 的标准功能
engine = ContextEngine(app_name="app", user_id="user")

# 获取标准优化结果
context = await engine.optimize("用户输入")

# 可选：使用模板进一步优化
optimizer = TemplateBasedOptimization()
processed = ProcessedContext(items=context.items)
enhanced = await optimizer.optimize(processed)

# 使用增强后的提示词
prompt = enhanced.items[0].content
```

#### 层次3：策略替换（高级）

```python
# 未来可以通过插件系统注册
from contextmind import registry

registry.register('optimizers', 'template_based', TemplateBasedOptimization)

# 或在自定义流程中使用
```

### 4.2 不影响原有功能的证明

#### 4.2.1 代码层面

1. **没有修改核心类**
   - `ContextEngine` 类：0 行修改
   - 现有 Pipeline 组件：0 行修改
   - 策略基类：0 行修改

2. **仅添加新文件**
   - 新增 3 个独立模块文件
   - 修改 2 个 `__init__.py`（仅添加导出）

3. **依赖关系单向**
   ```
   TemplateBasedOptimization → OptimizationStrategy (已有接口)
                             ↗ (实现)
   
   框架核心 ← ✗ 不依赖 ← 模板优化
   ```

#### 4.2.2 运行时层面

1. **不自动启用**
   ```python
   # 用户需要显式导入和使用
   from contextmind.pipeline import TemplateBasedOptimization  # 显式导入
   optimizer = TemplateBasedOptimization()  # 显式创建
   result = await optimizer.optimize(context)  # 显式调用
   ```

2. **可选依赖**
   - 不需要额外的依赖包
   - LLM 提取器是可选的（可以只用规则提取）

3. **独立测试**
   - 有专门的测试文件 `test_template_optimization.py`
   - 不影响原有测试套件

## 五、使用场景与选择

### 5.1 何时使用模板优化

✅ **适合使用的场景**：

1. **固定对话流程**
   - 客服场景（标准化回复）
   - 任务型对话（明确的意图分类）
   - 教学场景（结构化指导）

2. **需要明确意图引导**
   - 希望 LLM 明确知道用户意图
   - 需要结构化的提示词
   - 想要更可控的回复

3. **资源受限场景**
   - 使用规则提取器，无需额外 API 调用
   - 降低对话理解成本

### 5.2 何时不使用模板优化

❌ **不适合使用的场景**：

1. **开放式对话**
   - 闲聊、娱乐对话
   - 创意写作
   - 没有明确意图的场景

2. **已有完善的提示词工程**
   - 已经有精心设计的提示词
   - 不需要动态调整提示词

3. **追求最大灵活性**
   - 需要 LLM 自由发挥
   - 不希望受模板约束

### 5.3 使用建议

**推荐方式**：渐进式采用

```python
# 阶段1：标准使用
engine = ContextEngine(...)
context = await engine.optimize(user_input)
response = await llm.chat(context.to_prompt())

# 阶段2：尝试模板优化（可选）
optimizer = TemplateBasedOptimization()
enhanced = await optimizer.optimize(ProcessedContext(items=context.items))
response = await llm.chat(enhanced.items[0].content)

# 阶段3：根据效果决定是否继续使用
```

## 六、扩展性设计

### 6.1 自定义模板

```python
from contextmind.core import PromptTemplate, TemplateSlot

# 创建特定场景模板
custom_template = PromptTemplate(
    template_id="custom",
    name="我的模板",
    template_text="""场景特定的提示词...
    
意图: {intent}
自定义槽位: {custom_slot}

指导语...""",
    slots=[
        TemplateSlot(name="intent", required=True),
        TemplateSlot(name="custom_slot", default_value="默认值"),
    ]
)

optimizer = TemplateBasedOptimization(template=custom_template)
```

### 6.2 自定义意图提取器

```python
from contextmind.pipeline import IntentExtractor

class MyIntentExtractor(IntentExtractor):
    async def extract_intent(self, messages):
        # 自定义的意图提取逻辑
        # 可以结合业务规则、机器学习模型等
        ...
        return ExtractedIntent(...)

# 使用自定义提取器
optimizer = TemplateBasedOptimization()
optimizer.intent_extractor = MyIntentExtractor()
```

### 6.3 组合使用

```python
# 可以创建多个优化器，用于不同场景
chat_optimizer = TemplateBasedOptimization(template=CHAT_TEMPLATE)
cs_optimizer = TemplateBasedOptimization(template=CUSTOMER_SERVICE_TEMPLATE)

# 根据场景选择
if is_customer_service:
    result = await cs_optimizer.optimize(context)
else:
    result = await chat_optimizer.optimize(context)
```

## 七、性能与成本

### 7.1 性能分析

| 组件 | 延迟 | 说明 |
|-----|------|------|
| 规则意图提取 | < 5ms | 纯内存操作，关键词匹配 |
| LLM意图提取 | 500-2000ms | 取决于 LLM API 响应时间 |
| 模板填充 | < 1ms | 字符串替换操作 |
| **总延迟（规则）** | **< 10ms** | 几乎无感知 |
| **总延迟（LLM）** | **500-2000ms** | 需要权衡准确度与速度 |

### 7.2 成本分析

| 模式 | API调用 | Token消耗 | 成本 |
|-----|---------|----------|------|
| 规则提取 | 0 | 0 | 免费 |
| LLM提取 | 1次/轮 | ~100-300 tokens | 取决于模型定价 |

**推荐策略**：
- 实时对话：使用规则提取
- 离线分析：使用 LLM 提取
- 混合模式：简单场景用规则，复杂场景用 LLM

## 八、总结

### 8.1 核心优势

1. ✅ **非侵入性**：不修改框架核心，完全可选
2. ✅ **灵活性**：支持自定义模板和提取器
3. ✅ **可控性**：明确的意图引导，结构化提示词
4. ✅ **经济性**：规则提取器零成本
5. ✅ **兼容性**：遵循框架的设计模式

### 8.2 设计原则

- **开闭原则**：对扩展开放，对修改封闭
- **单一职责**：每个组件职责清晰
- **依赖倒置**：依赖抽象接口，不依赖具体实现
- **最小修改**：仅添加新代码，不改动原有代码

### 8.3 使用建议

1. **评估场景**：确认是否适合使用模板优化
2. **从简单开始**：先用默认模板和规则提取
3. **观察效果**：对比使用前后的 LLM 回复质量
4. **逐步定制**：根据需要创建自定义模板
5. **监控成本**：如果使用 LLM 提取，注意 API 成本

### 8.4 后续演进

可能的改进方向：
- [ ] 模板版本管理
- [ ] 模板效果评估指标
- [ ] 更多预定义模板
- [ ] 可视化模板编辑器
- [ ] 模板推荐系统

---

**文档版本**：v1.0  
**最后更新**：2026-01-29  
**维护者**：ContextMind Team
