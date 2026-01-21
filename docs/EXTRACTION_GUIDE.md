# 知识提取配置指南

## 概述

ContextMind v7.1 提供两种知识提取方式：
1. **规则提取 (Rule-based)** - 快速、通用、零成本
2. **LLM自动提取 (LLM-based)** - 智能、深度理解、需要API

两种方式都设计为**领域无关**的通用提取器，适用于任何对话场景。

---

## 核心设计原则

### ✅ 通用性优先
- **不硬编码领域知识** - 不针对特定行业（如电商、客服等）
- **基于语言学模式** - 依赖中文语法结构，而非具体名词
- **适应任何场景** - 聊天、客服、咨询、教育等全场景适用

### ✅ 准确性保证
- **多模式匹配** - 规则提取使用10+通用语言模式
- **置信度评分** - 每条知识都有置信度，可过滤低质量提取
- **LLM深度理解** - LLM提取能理解复杂语义和隐含信息

### ✅ 及时性保障
- **实时提取** - 每轮对话后立即提取知识
- **自动入库** - 支持`auto_store=True`自动存储到长期记忆
- **增量更新** - 新知识实时可用于下一轮对话

---

## 配置方式

### 1. 在 ContextEngine 初始化时配置

这是**主要配置位置**：

```python
from contextmind import ContextEngine
from contextmind.models import ExtractionConfig

# 方式1: 规则提取（默认，推荐）
engine = ContextEngine(
    app_name="my-app",
    user_id="user-123",
    extraction_method="rule"  # 使用规则提取
)

# 方式2: LLM自动提取（需要 LLM 客户端）
from demos.llm_client import SimpleLLMClient

llm_client = SimpleLLMClient.from_env()
engine = ContextEngine(
    app_name="my-app",
    user_id="user-123",
    llm_client=llm_client,  # 必须提供
    extraction_method="llm"  # 使用 LLM 提取
)

# 方式3: 自定义配置
config = ExtractionConfig(
    extraction_method="rule",
    min_confidence=0.6,  # 最小置信度阈值
    max_phrase_length=150,  # 最大短语长度
    extract_preferences=True,  # 提取偏好
    extract_facts=True,  # 提取事实
    extract_events=True,  # 提取事件
)

engine = ContextEngine(
    app_name="my-app",
    user_id="user-123",
    extraction_method="rule",
    extraction_config=config  # 传入自定义配置
)
```

### 2. 在 Demo 应用中配置

Demo应用（如CallCenterApplication）会读取引擎的配置：

```python
from contextmind import ContextEngine
from demos.callcenter_app import CallCenterApplication

# 创建引擎（配置提取方式）
engine = ContextEngine(
    app_name="callcenter",
    user_id="user-456",
    extraction_method="rule"  # 在这里配置
)

# 创建应用（会自动使用引擎的配置）
app = CallCenterApplication(
    context_engine=engine,
    use_real_llm=True
)

# 也可以显式指定（会覆盖引擎配置）
app = CallCenterApplication(
    context_engine=engine,
    extraction_method="llm",  # 覆盖为LLM提取
    use_real_llm=True
)
```

---

## 规则提取 vs LLM提取

### 规则提取（推荐用于大部分场景）

**原理:**
- 基于通用中文语言学模式
- 使用正则表达式匹配常见表达结构
- 不依赖特定领域知识

**提取能力:**
1. **意图和需求** - "想买XX", "需要XX", "希望XX", "给我推荐XX"
2. **偏好表达** - "我喜欢XX", "更倾向XX", "不喜欢XX"
3. **数值约束** - "XX元以下", "低于XX", "不超过XX", "XX左右"
4. **身份信息** - "我是XX", "我叫XX", "我XX岁"
5. **时间事件** - "昨天XX", "明天XX", "刚才XX"

**优点:**
- ✅ 速度快（毫秒级）
- ✅ 零成本（无API调用）
- ✅ 确定性强（相同输入=相同输出）
- ✅ 适用任何领域

**缺点:**
- ❌ 无法理解复杂语义
- ❌ 不能提取隐含信息
- ❌ 模式覆盖有限

**适用场景:**
- 日常对话
- 明确表达的需求
- 对提取成本敏感的场景
- 需要高性能的场景

### LLM提取（适用于复杂场景）

**原理:**
- 使用LLM的深度语义理解能力
- 通过精心设计的prompt引导提取
- 输出结构化JSON知识

**提取能力:**
1. **深度语义理解** - 理解隐含意图和情感
2. **实体识别** - 自动识别人名、地名、品牌等
3. **关系提取** - 提取实体间的关系
4. **上下文理解** - 结合多轮对话理解
5. **复杂推理** - 从对话中推断潜在需求

**优点:**
- ✅ 理解复杂语义
- ✅ 提取隐含信息
- ✅ 支持实体和关系
- ✅ 自适应任何领域

**缺点:**
- ❌ 速度较慢（API调用）
- ❌ 有成本（API费用）
- ❌ 非确定性（LLM可能有随机性）

**适用场景:**
- 复杂咨询对话
- 需要深度理解的场景
- 对提取质量要求极高的场景
- 不敏感API成本的场景

---

## 提取效果示例

### 场景1: 日常对话

**对话内容:**
```
用户: 我想买一台冰箱
用户: 预算大概2000元左右
用户: 西门子的质量怎么样
```

**规则提取结果:**
```
1. [偏好] 用户intent: 买一台冰箱 (置信度: 0.75)
2. [偏好] 用户约束: 2000元 (置信度: 0.85)
3. [偏好] 用户偏好: 想买冰箱 (置信度: 0.80)
```

**LLM提取结果:**
```
1. [偏好] 用户购买意图: 冰箱 (置信度: 0.90)
2. [偏好] 预算约束: 2000元左右 (置信度: 0.95)
3. [偏好] 品牌关注: 西门子 (置信度: 0.85)
4. [事实] 品牌质量咨询: 西门子冰箱 (置信度: 0.80)
```

### 场景2: 个人信息

**对话内容:**
```
用户: 我叫张三
用户: 今年25岁
用户: 在北京工作
```

**规则提取结果:**
```
1. [事实] 我叫张三 (置信度: 0.70)
2. [事实] 我25岁 (置信度: 0.70)
3. [事实] 我在北京 (置信度: 0.70)
```

**LLM提取结果:**
```
1. [事实] 姓名: 张三 (置信度: 0.95)
2. [事实] 年龄: 25岁 (置信度: 0.95)
3. [事实] 工作地点: 北京 (置信度: 0.90)
```

---

## 配置参数说明

### ExtractionConfig 参数

```python
@dataclass
class ExtractionConfig:
    # 提取方式
    extraction_method: str = "rule"  # 'rule' 或 'llm'
    
    # 通用参数
    min_confidence: float = 0.5  # 最小置信度（低于此值的知识会被过滤）
    max_phrase_length: int = 100  # 最大短语长度
    
    # 提取类型开关
    extract_preferences: bool = True  # 是否提取偏好
    extract_facts: bool = True  # 是否提取事实
    extract_events: bool = True  # 是否提取事件
    extract_entities: bool = True  # 是否提取实体（LLM专用）
    extract_relationships: bool = True  # 是否提取关系（LLM专用）
    
    # 置信度设置
    preference_confidence: float = 0.8  # 偏好默认置信度
    fact_confidence: float = 0.7  # 事实默认置信度
    event_confidence: float = 0.6  # 事件默认置信度
    entity_confidence: float = 0.75  # 实体默认置信度（LLM）
    relationship_confidence: float = 0.7  # 关系默认置信度（LLM）
    
    # LLM专用配置
    llm_temperature: float = 0.1  # LLM温度（越低越确定）
    llm_max_tokens: int = 1000  # LLM最大token数
    llm_batch_size: int = 10  # 批处理大小
```

### 调优建议

**提高提取率:**
- 降低 `min_confidence` (如 0.5 → 0.4)
- 增加 `max_phrase_length` (如 100 → 150)

**提高提取精度:**
- 提高 `min_confidence` (如 0.5 → 0.6)
- 减少 `max_phrase_length` (如 100 → 50)

**降低LLM成本:**
- 减少 `llm_max_tokens` (如 1000 → 500)
- 增加 `llm_batch_size` (批量处理)

---

## 最佳实践

### 1. 选择合适的提取方式

**使用规则提取 when:**
- 对话结构相对简单
- 用户表达比较直接明确
- 对成本敏感
- 需要高性能（低延迟）
- **推荐：90%的场景**

**使用LLM提取 when:**
- 对话语义复杂
- 需要理解隐含信息
- 需要提取实体和关系
- 对提取质量要求极高
- **推荐：10%的高价值场景**

### 2. 混合策略（未来支持）

未来版本将支持混合提取：
- 规则提取作为基础（快速、覆盖常见情况）
- LLM提取作为补充（处理复杂情况）
- 自动决策何时使用LLM

### 3. 监控和优化

```python
# 提取知识后检查
knowledge_list = await engine.extract_knowledge()

# 查看提取数量
print(f"提取了 {len(knowledge_list)} 条知识")

# 查看置信度分布
for k in knowledge_list:
    print(f"[{k.knowledge_type.value}] {k.content[:30]}... (置信度: {k.confidence:.2f})")

# 调整配置if necessary
if len(knowledge_list) < expected_count:
    # 提取率太低，降低阈值
    config.min_confidence = 0.4
```

---

## 常见问题

### Q1: 为什么不硬编码品牌名、产品类型等？

**A:** 硬编码会限制通用性。例如：
- 电商场景硬编码"西门子、海尔"，换到其他行业就无效
- 通用模式如"想买XX"适用于任何行业
- 如需特定领域优化，应使用LLM提取或在应用层处理

### Q2: 提取的知识太少/太多怎么办？

**A:** 调整配置参数：
```python
# 提取太少 - 降低阈值
config.min_confidence = 0.4

# 提取太多 - 提高阈值
config.min_confidence = 0.7
```

### Q3: 两种方式可以同时使用吗？

**A:** 当前版本一次只能选择一种。未来版本将支持混合策略。

### Q4: 如何查看当前使用的提取方式？

**A:** 
```python
print(f"提取方式: {engine.extraction_method}")
# 或
print(f"提取方式: {app.extraction_method}")
```

### Q5: LLM提取失败会怎样？

**A:** 自动降级到规则提取，确保系统稳定性。

---

## 技术架构

```
应用层 (CallCenterApplication, ChatApplication)
   ↓ 配置 extraction_method
引擎层 (ContextEngine)
   ↓ 初始化对应提取器
提取器层 (RuleBasedExtractor / LLMBasedExtractor)
   ↓ 执行提取
知识库 (MemoryBank)
   ↓ 存储和检索
```

---

## 总结

1. **配置位置**: `ContextEngine` 初始化时设置 `extraction_method`
2. **两种方式**: 规则提取（推荐）vs LLM提取（复杂场景）
3. **通用设计**: 不硬编码领域知识，适用任何场景
4. **灵活调优**: 通过 `ExtractionConfig` 自定义参数
5. **最佳实践**: 90%场景用规则，10%高价值场景用LLM

有任何问题请参考文档或查看代码示例！
