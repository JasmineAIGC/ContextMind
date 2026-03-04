# Evolve模式（演化式上下文优化）

## 概述

Evolve（Evolutionary Context Optimization，演化式上下文优化）是一种基于**AlphaEvolve和ThetaEvolve算法**的高级对话管理模式。它通过智能的记忆管理和上下文优化，实现更自然、更智能的长对话处理。

## 核心原理

Evolve模式基于两个核心算法：

### AlphaEvolve算法

**上下文演化和优化算法**，负责：
1. **上下文检索**：从历史对话和记忆库中检索相关信息
2. **上下文整合**：整合检索结果，构建最优上下文
3. **动态压缩**：压缩冗余信息，保持上下文简洁
4. **重排序**：根据相关性重新排序上下文

### ThetaEvolve算法

**记忆演化和学习算法**，负责：
1. **知识提取**：从对话中提取有价值的知识点
2. **记忆存储**：将知识存储为结构化记忆
3. **适应度评估**：评估记忆的重要性和相关性
4. **记忆演化**：基于适应度优化记忆库

## 架构设计

Evolve模式由五大核心组件构成：

### 1. EvolveEngine

核心引擎，协调所有组件：
- 流程控制
- 组件调度
- 状态管理
- 性能监控

### 2. Memory系统

记忆管理子系统：
- **MemoryBank**：记忆存储库
- **MemoryExtractor**：知识提取器
- **MemoryRetriever**：记忆检索器
- **MemoryUpdater**：记忆更新器
- **MemoryFitness**：适应度评估器

### 3. Pipeline

上下文处理流水线：
- **InputPreprocessor**：输入预处理
- **ContextRetriever**：上下文检索
- **ContextCompressor**：压缩
- **ContextReorderer**：重排序
- **Summarizer**：摘要生成

### 4. Evolution

演化系统：
- **EvolutionaryUpdater**：演化更新器
- **FeedbackSystem**：反馈系统

### 5. Core Framework

核心框架：
- **DataModels**：数据模型（Message、ContextItem等）
- **Config**：类型定义（KnowledgeType等）和配置数据类（合并）
- **Strategies**：抽象策略基类
- **Registry**：插件注册表

## 计算流程

### AlphaEvolve流程（上下文优化）

```
用户输入
    ↓
1. 上下文检索
   - 检索相关历史对话
   - 检索相关记忆
   - 合并检索结果
    ↓
2. 上下文整合
   - 预处理（去重、过滤）
   - 压缩（移除冗余）
   - 重排序（按相关性）
   - 构建最终上下文
    ↓
3. LLM生成
   - 使用优化后的上下文
   - 调用LLM生成回复
    ↓
4. 对话更新
   - 更新对话历史
   - 记录新的交互
    ↓
生成的回复
```

### ThetaEvolve流程（记忆演化）

```
对话完成
    ↓
1. 知识提取
   - 分析对话内容
   - 提取关键信息
   - 识别知识点
    ↓
2. 记忆存储
   - 创建Memory对象
   - 添加元数据
   - 存入MemoryBank
    ↓
3. 适应度评估
   - 计算相关性分数
   - 计算重要性分数
   - 计算新鲜度分数
    ↓
4. 记忆演化
   - 淘汰低适应度记忆
   - 合并相似记忆
   - 优化记忆库结构
    ↓
优化后的记忆库
```

### 完整处理流程

```
用户输入
    ↓
AlphaEvolve: 上下文检索
    ↓
AlphaEvolve: 上下文整合
    ↓
LLM生成
    ↓
AlphaEvolve: 对话更新
    ↓
ThetaEvolve: 知识提取
    ↓
ThetaEvolve: 记忆存储
    ↓
ThetaEvolve: 适应度评估
    ↓
ThetaEvolve: 记忆演化
    ↓
输出回复 + 更新系统状态
```

### 详细步骤说明

#### 步骤1：上下文检索（AlphaEvolve）
- 使用向量相似度检索历史对话
- 使用关键词检索记忆库
- 合并去重检索结果
- 典型耗时：~0.15s

#### 步骤2：上下文整合（AlphaEvolve）
- 预处理：去除无关信息
- 压缩：摘要长文本
- 重排序：相关性排序
- 典型耗时：~0.05s

#### 步骤3：LLM生成
- 使用优化后的上下文
- 生成高质量回复
- 典型耗时：~1.5-2.5s（占80-90%）

#### 步骤4：对话更新（AlphaEvolve）
- 添加到对话历史
- 更新会话状态
- 典型耗时：~0.02s

#### 步骤5：知识提取（ThetaEvolve）
- LLM提取关键知识点
- 结构化知识表示
- 典型耗时：~0.08s

#### 步骤6-8：记忆演化（ThetaEvolve）
- 存储、评估、优化记忆
- 后台异步执行
- 不影响响应速度

## 记忆系统

### Memory数据模型

```python
@dataclass
class Memory:
    """记忆对象"""
    content: str              # 记忆内容
    embedding: List[float]    # 向量表示
    importance: float         # 重要性分数
    relevance: float          # 相关性分数
    created_at: datetime      # 创建时间
    accessed_count: int       # 访问次数
    metadata: Dict[str, Any]  # 元数据
```

### 记忆检索策略

1. **向量检索**：基于embedding的相似度检索
2. **关键词检索**：基于关键词匹配
3. **混合检索**：结合向量和关键词
4. **时间衰减**：新鲜的记忆权重更高

### 适应度函数

```python
fitness = α * relevance + β * importance + γ * freshness
```

其中：
- `relevance`：与当前对话的相关性
- `importance`：记忆本身的重要性
- `freshness`：时间新鲜度
- `α, β, γ`：权重参数

## 上下文优化

### 检索策略

```python
# 配置检索参数
retrieval_config = {
    "max_history_turns": 10,      # 最多检索10轮历史
    "max_memories": 5,             # 最多检索5条记忆
    "similarity_threshold": 0.7,   # 相似度阈值
    "use_reranking": True          # 启用重排序
}
```

### 压缩策略

- **滑动窗口**：只保留最近N轮对话
- **摘要压缩**：长文本自动摘要
- **关键信息提取**：只保留关键部分

### 重排序算法

基于多因素的重排序：
1. 相关性分数
2. 时间距离
3. 重要性
4. 用户偏好

## 数据模型

### ContextInfo

```python
@dataclass
class ContextInfo:
    """上下文信息"""
    dialogue_history: List[Turn]   # 对话历史
    retrieved_memories: List[Memory]  # 检索的记忆
    compressed_context: str        # 压缩后的上下文
```

### SessionState

```python
@dataclass
class SessionState:
    """会话状态"""
    session_id: str               # 会话ID
    user_profile: Dict            # 用户画像
    context_info: ContextInfo     # 上下文信息
    memory_bank: MemoryBank       # 记忆库
```

## 使用示例

### 基础用法

```python
from contextmind.modes.evolve import create_app_for_scenario
from contextmind.infra.llm_client import SimpleLLMClient

# 创建Evolve应用
llm_client = SimpleLLMClient()
app = create_app_for_scenario(
    scenario_name="chat",
    llm_client=llm_client
)

# 处理对话
user_input = "你好，我叫张三"
response = app.chat(user_input)
print(response)
# 输出：你好张三！很高兴认识你...

# 后续对话（会记住用户名字）
user_input = "我喜欢打篮球"
response = app.chat(user_input)
print(response)
# 输出：张三，篮球是很好的运动...
```

### 查看步骤耗时

```python
print(f"步骤耗时：{app.step_timings}")
# 输出：
# {
#   '上下文检索': 0.15,
#   '上下文整合': 0.05,
#   'LLM生成': 1.85,
#   '对话更新': 0.02,
#   '知识提取': 0.08
# }
```

### 查看记忆库

```python
# 获取所有记忆
memories = app.engine.memory_bank.get_all_memories()
print(f"记忆数量：{len(memories)}")

# 查看最近的记忆
recent = app.engine.memory_bank.get_recent_memories(n=5)
for mem in recent:
    print(f"- {mem.content} (重要性: {mem.importance})")
```

### 自定义配置

```python
from contextmind.modes.evolve.core.config import MemorySystemConfig

config = MemorySystemConfig(
    # 根据 MemorySystemConfig 的字段进行配置
)

app = create_app_for_scenario(
    scenario_name="chat",
    llm_client=llm_client,
    config=config
)
```

## 性能特点

### 优势

1. **智能记忆**：记住用户信息和对话上下文
2. **长对话优化**：通过压缩和检索处理长对话
3. **自我演化**：记忆库持续优化，越用越好
4. **个性化**：基于记忆提供个性化回复

### 适用场景

- ✅ 长期对话（需要记住历史信息）
- ✅ 个性化助手（需要了解用户）
- ✅ 知识积累（需要学习和记忆）
- ✅ 复杂上下文（需要上下文理解）

### 对比其他模式

| 特性 | DST | FnCTOD | Evolve |
|------|-----|--------|--------|
| 记忆能力 | ❌ | ❌ | ✅ |
| 长对话 | ❌ | ❌ | ✅ |
| 上下文优化 | ❌ | ❌ | ✅ |
| 个性化 | ❌ | ❌ | ✅ |
| 复杂度 | 低 | 中 | 高 |
| 计算开销 | 低 | 中 | 高 |

### 局限性

- ❌ 计算开销较大（检索、压缩等）
- ❌ 需要向量数据库（存储embeddings）
- ❌ 配置相对复杂
- ❌ 冷启动时效果一般（记忆库为空）

## AlphaEvolve vs ThetaEvolve

### AlphaEvolve（上下文层）

- **作用域**：单次对话处理
- **优化目标**：上下文质量
- **主要操作**：检索、整合、压缩、重排序
- **执行时机**：每次对话处理时

### ThetaEvolve（记忆层）

- **作用域**：跨对话长期记忆
- **优化目标**：记忆库质量
- **主要操作**：提取、存储、评估、演化
- **执行时机**：对话后台异步

### 协同工作

```
AlphaEvolve使用ThetaEvolve的记忆库 → 生成更好的上下文
ThetaEvolve从对话中提取知识 → 优化记忆库
形成正向循环 → 系统越用越智能
```

## 配置和扩展

### 自定义检索策略

```python
from contextmind.modes.evolve.memory.retriever import MemoryRetriever

class CustomRetriever(MemoryRetriever):
    def retrieve(self, query: str, top_k: int) -> List[Memory]:
        # 自定义检索逻辑
        pass
```

### 自定义压缩策略

```python
from contextmind.modes.evolve.pipeline.steps import ContextCompressor

class CustomCompressor(ContextCompressor):
    def compress(self, context: str) -> str:
        # 自定义压缩逻辑
        pass
```

### 插件系统

Evolve支持插件扩展：
- 自定义记忆提取器
- 自定义适应度函数
- 自定义上下文处理组件

## 总结

Evolve模式是基于AlphaEvolve和ThetaEvolve算法的先进对话系统，通过智能的记忆管理和上下文优化，实现了真正智能和个性化的对话体验。它特别适合需要长期记忆、上下文理解和个性化服务的应用场景。
