# 知识提取与记忆入库系统

## 概述

ContextMind v7.1 提供了灵活的知识提取和记忆存储系统，支持两种提取方式：

1. **规则提取 (Rule-based)**: 使用模式匹配和启发式方法，快速、确定性地提取知识
2. **LLM自动提取 (LLM-based)**: 使用大语言模型的语义理解能力，智能提取结构化知识

## 知识提取方式对比

| 特性 | 规则提取 | LLM提取 |
|------|---------|---------|
| 提取速度 | 快速 | 较慢 (需要API调用) |
| 准确性 | 高 (明确模式) | 高 (语义理解) |
| 灵活性 | 低 (需要预定义模式) | 高 (自适应) |
| 成本 | 无成本 | API调用成本 |
| 复杂场景 | 有限 | 强大 |
| 实体关系 | 不支持 | 支持 |
| 适用场景 | 简单、明确的信息 | 复杂、多样的对话 |

## 使用方法

### 1. 配置提取方式

```python
from contextmind import ContextEngine
from demos.llm_client import SimpleLLMClient, LLMConfig

# 方式1: 使用规则提取 (默认)
engine = ContextEngine(
    app_name="my-app",
    user_id="user-123",
    extraction_method="rule"  # 规则提取
)

# 方式2: 使用LLM提取
llm_client = SimpleLLMClient.from_env()  # 从.env加载配置
engine = ContextEngine(
    app_name="my-app",
    user_id="user-123",
    llm_client=llm_client,
    extraction_method="llm"  # LLM自动提取
)
```

### 2. 提取配置

```python
from contextmind.models import ExtractionConfig

# 自定义提取配置
config = ExtractionConfig(
    extraction_method="llm",  # 提取方式
    min_confidence=0.7,  # 最小置信度阈值
    max_phrase_length=100,  # 最大短语长度
    
    # 提取类型开关
    extract_preferences=True,  # 提取偏好
    extract_facts=True,  # 提取事实
    extract_events=True,  # 提取事件
    extract_entities=True,  # 提取实体 (仅LLM)
    extract_relationships=True,  # 提取关系 (仅LLM)
    
    # LLM提取专用配置
    llm_temperature=0.1,  # 较低温度确保稳定性
    llm_max_tokens=1000,  # 最大token数
)

engine = ContextEngine(
    app_name="my-app",
    user_id="user-123",
    llm_client=llm_client,
    extraction_method="llm",
    extraction_config=config
)
```

### 3. 提取知识

```python
# 提取并自动存储到长期记忆
knowledge_list = await engine.extract_knowledge(auto_store=True)

# 仅提取，不存储
knowledge_list = await engine.extract_knowledge(auto_store=False)

# 手动存储
await engine.memory_bank.store(knowledge_list)
```

## 存储的知识数据结构

每条提取的知识包含以下信息：

```python
@dataclass
class Knowledge:
    """知识项"""
    # 核心信息
    content: str  # 知识内容
    knowledge_type: KnowledgeType  # 类型: PREFERENCE, FACT, EVENT
    confidence: float  # 置信度 (0-1)
    
    # 提取信息
    extraction_method: str  # 'rule' 或 'llm'
    source_message_ids: List[str]  # 来源消息ID列表
    
    # 时间信息
    timestamp: datetime  # 提取时间
    last_accessed: Optional[datetime]  # 最后访问时间
    
    # 重要性管理
    access_count: int  # 访问次数
    importance_score: float  # 重要性分数 (可动态调整)
    
    # 元数据
    metadata: Dict[str, Any]
        # category: 细分类别 (如"食物偏好"、"个人信息")
        # entities: 涉及的实体列表 (如["张三", "北京"])
        # keywords: 关键词列表
        # sentiment: 情感倾向 (positive/negative/neutral)
        # context: 原始上下文片段
        # relationships: 相关关系 (如"张三是李四的同事")
```

## 知识类型

### 1. 偏好 (PREFERENCE)
用户的喜好、需求、意愿

**规则提取示例:**
- "我喜欢吃辣的" → "用户表示喜欢吃辣的"
- "我想要咖啡" → "用户表示想要咖啡"

**LLM提取示例:**
- 复杂情感: "虽然辣的很好吃，但我最近胃不好，还是少吃为妙"
- 隐含偏好: "每次来都点这个，太喜欢了"

### 2. 事实 (FACT)
关于用户或主题的客观信息

**规则提取示例:**
- "我叫张三" → "我叫张三"
- "我25岁" → "我25岁"

**LLM提取示例:**
- 复杂事实: "我在这家公司工作了三年，是技术部门的架构师"
- 关系事实: "我和小李是大学同学"

### 3. 事件 (EVENT)
发生的事件、行为或活动

**规则提取示例:**
- "昨天去了公园" → "昨天去了公园"
- "今天吃了火锅" → "今天吃了火锅"

**LLM提取示例:**
- 复杂事件: "上周末和朋友一起去爬山，虽然很累但很开心"
- 计划事件: "下个月要去北京出差三天"

## 存储策略建议

### 什么信息值得入库？

1. **高价值信息**
   - 用户的核心偏好 (如饮食习惯、兴趣爱好)
   - 重要个人信息 (如姓名、职业、家庭情况)
   - 关键事件和里程碑
   - 长期有效的关系和联系

2. **避免存储**
   - 临时性、一次性的信息
   - 过于具体、无法泛化的细节
   - 明显错误或矛盾的信息
   - 隐私敏感且无业务价值的信息

### 重要性评分机制

系统支持动态调整知识的重要性分数：

```python
# 基于访问频率更新重要性
knowledge.access_count += 1
knowledge.last_accessed = datetime.now()

# 重要性分数随时间衰减（可选）
time_decay = 0.95 ** days_since_creation
knowledge.importance_score *= time_decay

# 基于访问频率提升重要性
if knowledge.access_count > 10:
    knowledge.importance_score = min(1.0, knowledge.importance_score * 1.1)
```

## 最佳实践

### 1. 选择合适的提取方式

- **使用规则提取**:
  - 对话模式简单、明确
  - 需要快速响应
  - 成本敏感场景
  - 已知明确的提取模式

- **使用LLM提取**:
  - 对话内容复杂、多样
  - 需要理解上下文和语义
  - 需要提取实体关系
  - 追求高准确率和完整性

### 2. 混合使用

```python
# 先用规则提取快速获取明显信息
rule_knowledge = await rule_extractor.extract(messages)

# 对复杂场景使用LLM补充提取
if needs_deep_analysis:
    llm_knowledge = await llm_extractor.extract(messages)
    all_knowledge = rule_knowledge + llm_knowledge
```

### 3. 定期维护

```python
# 清理低置信度、低访问的知识
def cleanup_memory():
    threshold_date = datetime.now() - timedelta(days=90)
    for knowledge in memory_bank.all():
        if (knowledge.access_count < 2 and 
            knowledge.last_accessed < threshold_date):
            memory_bank.remove(knowledge)
```

### 4. 知识去重

```python
# 检测相似知识，避免重复存储
def deduplicate(new_knowledge, existing_knowledge):
    if similarity(new_knowledge, existing_knowledge) > 0.9:
        # 合并或更新而不是新增
        existing_knowledge.access_count += 1
        existing_knowledge.confidence = max(
            existing_knowledge.confidence,
            new_knowledge.confidence
        )
        return existing_knowledge
    return new_knowledge
```

## 示例代码

### 完整示例：使用LLM提取

```python
from contextmind import ContextEngine
from demos.llm_client import SimpleLLMClient
from demos.callcenter_app import CallCenterApplication

# 1. 初始化LLM客户端
llm_client = SimpleLLMClient.from_env()

# 2. 创建使用LLM提取的引擎
engine = ContextEngine(
    app_name="customer-service",
    user_id="user-001",
    llm_client=llm_client,
    extraction_method="llm"  # 使用LLM自动提取
)

# 3. 创建应用
app = CallCenterApplication(
    context_engine=engine,
    use_real_llm=True
)

# 4. 处理对话
response = await app.process_turn("我叫张三，在北京工作，喜欢吃川菜")

# 5. 知识会自动提取并存储到记忆库
# LLM会提取:
# - Fact: "用户名叫张三"
# - Fact: "用户在北京工作"
# - Preference: "用户喜欢吃川菜"
# - Entities: ["张三", "北京", "川菜"]
# - Category: "个人信息", "食物偏好"
```

## 环境变量配置

使用LLM提取时，需要在`.env`文件中配置：

```bash
# LLM API配置
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://api.example.com/v1
LLM_MODEL=gpt-3.5-turbo

# 提取专用配置（可选）
EXTRACTION_METHOD=llm  # 'rule' 或 'llm'
EXTRACTION_TEMPERATURE=0.1
EXTRACTION_MAX_TOKENS=1000
```

## 性能优化建议

1. **批量提取**: 累积多条消息后一次性提取，减少API调用
2. **异步处理**: 提取和入库异步进行，不阻塞主流程
3. **缓存结果**: 对相似对话缓存提取结果
4. **智能触发**: 只对有价值的对话触发提取，避免无效提取

## 总结

ContextMind v7.1 的知识提取和记忆系统提供了：

✅ 双模式支持：规则提取 + LLM自动提取
✅ 灵活配置：支持自定义提取策略和参数
✅ 丰富元数据：追溯来源、访问统计、重要性评分
✅ 易于扩展：可插拔的提取器架构
✅ 生产就绪：完善的错误处理和降级机制

通过合理使用知识提取和存储功能，可以让AI系统更好地理解和记住用户，提供个性化、连贯的服务体验。
