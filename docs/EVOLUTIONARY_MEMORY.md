# 进化式记忆管理系统

## 概述

ContextMind 的进化式记忆管理系统借鉴 **AlphaEvolve** 和 **ThetaEvolve** 的进化思想，将进化算法应用于对话任务中的记忆库优化。

### 核心思想

**AlphaEvolve/ThetaEvolve** 是用于解决数学问题和算法优化的进化系统，而 **ContextMind** 将这些进化思想应用于对话任务的记忆管理：

| AlphaEvolve/ThetaEvolve | ContextMind 记忆管理 |
|------------------------|---------------------|
| 候选解决方案 | 记忆条目 |
| 适应度函数 | 记忆有用性评分 |
| 种群进化 | 记忆库更新 |
| 选择算子 | 保留高质量记忆 |
| 变异算子 | 更新记忆内容 |
| 交叉算子 | 合并相似记忆 |
| 优化目标 | 记忆质量提升 |

---

## 架构设计

### 1. 记忆适应度评估 (`memory_fitness.py`)

#### MemoryFitness

多维度评分系统：

```python
@dataclass
class MemoryFitness:
    usage_count: int = 0      # 使用次数
    last_used: float = 0.0    # 最后使用时间
    accuracy: float = 1.0     # 准确性（基于反馈）
    relevance: float = 1.0    # 相关性评分
    recency: float = 1.0      # 新鲜度
```

**适应度计算**:
```python
score = (
    0.3 * usage_score +       # 使用频率
    0.25 * recency_score +    # 时间新鲜度
    0.25 * accuracy +         # 准确性
    0.2 * relevance           # 相关性
)
```

**时间衰减**:
- 使用指数衰减函数
- 半衰期：7天
- 公式：`exp(-时间差 / 半衰期)`

#### FitnessCalculator

统一的适应度计算接口：

```python
calculator = FitnessCalculator(
    weights={
        'usage': 0.3,
        'recency': 0.25,
        'accuracy': 0.25,
        'relevance': 0.2
    }
)

# 计算适应度
score = calculator.calculate_fitness_score(memory)

# 更新适应度（基于使用反馈）
updated_memory = calculator.update_fitness(
    memory,
    used=True,
    accuracy_feedback=0.9
)
```

---

### 2. 进化式更新器 (`evolutionary_updater.py`)

#### EvolutionaryMemoryUpdater

核心进化引擎：

```python
updater = EvolutionaryMemoryUpdater(
    max_memory_size=100,           # 最大记忆容量
    elite_ratio=0.7,               # 精英保留比例
    similarity_threshold=0.85,     # 相似度合并阈值
    min_fitness_threshold=0.2,     # 最低适应度
    enable_decay=True              # 启用使用次数衰减
)

# 执行进化式更新
updated_cache = await updater.update(
    memory_cache,
    new_knowledge
)
```

#### 进化流程

```
┌─────────────────────────────────────────────────────┐
│ 1. 适应度评估                                      │
│    - 为所有现有记忆计算适应度分数                  │
│    - 考虑使用频率、新鲜度、准确性、相关性          │
└─────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────┐
│ 2. 精英选择                                        │
│    - 保留前70%高适应度记忆                         │
│    - 淘汰低价值记忆                                │
└─────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────┐
│ 3. 知识过滤                                        │
│    - 过滤低质量新知识                              │
│    - 应用置信度和内容质量阈值                      │
└─────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────┐
│ 4. 记忆合并（交叉）                                │
│    - 检测相似记忆（嵌入向量或文本相似度）          │
│    - 保留高置信度版本                              │
│    - 继承使用统计信息                              │
└─────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────┐
│ 5. 添加新记忆                                      │
│    - 加入高质量新知识                              │
│    - 初始化适应度信息                              │
└─────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────┐
│ 6. 容量控制                                        │
│    - 如果超过上限，按适应度排序                    │
│    - 淘汰低适应度记忆                              │
│    - 保持在 max_memory_size 以内                   │
└─────────────────────────────────────────────────────┘
```

---

## 使用指南

### 快速开始

```python
from contextmind.memory import EvolutionaryMemoryUpdater
from contextmind.core.data_models import ContextItem, Knowledge
from contextmind.core.types import KnowledgeType

# 创建进化式更新器
updater = EvolutionaryMemoryUpdater(
    max_memory_size=100,
    elite_ratio=0.7,
    similarity_threshold=0.85
)

# 现有记忆库
memory_cache = [
    ContextItem(content="我喜欢喝咖啡", source=ContextSource.MEMORY, score=0.9),
    ContextItem(content="我在北京工作", source=ContextSource.MEMORY, score=0.85),
]

# 新提取的知识
new_knowledge = [
    Knowledge(
        knowledge_type=KnowledgeType.PREFERENCE,
        content="我很喜欢喝拿铁咖啡",
        scores=ScoreInfo(confidence=0.92)
    )
]

# 执行进化式更新
updated_cache = await updater.update(memory_cache, new_knowledge)
```

### 与 MemoryBank 集成

```python
from contextmind.memory import MemoryBank, EvolutionaryMemoryUpdater

# 创建进化式更新器
evolutionary_updater = EvolutionaryMemoryUpdater(
    max_memory_size=200,
    elite_ratio=0.7
)

# 创建 MemoryBank（使用进化式更新器）
memory_bank = MemoryBank(
    updater=evolutionary_updater,  # 使用进化式更新器
    max_cache_size=200
)

# 正常使用 MemoryBank
await memory_bank.store(new_knowledge)
relevant_memories = await memory_bank.retrieve(query)
```

---

## 配置参数

### EvolutionaryMemoryUpdater 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_memory_size` | 100 | 记忆库最大容量 |
| `elite_ratio` | 0.7 | 精英保留比例（0-1） |
| `similarity_threshold` | 0.85 | 记忆合并的相似度阈值（0-1） |
| `min_fitness_threshold` | 0.2 | 最低适应度阈值（0-1） |
| `fitness_weights` | None | 适应度权重配置（Dict） |
| `enable_decay` | True | 是否启用使用次数衰减 |

### FitnessCalculator 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `weights` | 见下表 | 各维度权重配置 |
| `usage_decay_rate` | 0.95 | 使用次数衰减率 |

**默认权重**:
```python
{
    'usage': 0.3,      # 使用频率权重
    'recency': 0.25,   # 新鲜度权重
    'accuracy': 0.25,  # 准确性权重
    'relevance': 0.2   # 相关性权重
}
```

---

## 应用场景

### 1. 长期对话管理

```python
# 场景：聊天机器人需要长期记住用户偏好
updater = EvolutionaryMemoryUpdater(
    max_memory_size=500,      # 较大容量
    elite_ratio=0.8,          # 保留更多记忆
    similarity_threshold=0.90  # 更严格的合并
)
```

### 2. 客服系统

```python
# 场景：客服需要快速访问相关知识
updater = EvolutionaryMemoryUpdater(
    max_memory_size=100,      # 精简高效
    elite_ratio=0.6,          # 更激进的淘汰
    enable_decay=True         # 启用衰减，保持新鲜
)
```

### 3. 个人助理

```python
# 场景：个人助理需要平衡新旧信息
updater = EvolutionaryMemoryUpdater(
    max_memory_size=200,
    elite_ratio=0.7,
    fitness_weights={
        'usage': 0.35,        # 更重视使用频率
        'recency': 0.30,      # 重视新鲜度
        'accuracy': 0.20,
        'relevance': 0.15
    }
)
```

---

## 性能优化

### 1. 缓存优化

```python
# 使用嵌入向量加速相似度计算
knowledge = Knowledge(
    knowledge_type=KnowledgeType.FACT,
    content="我喜欢编程",
    embeddings={
        'default': EmbeddingInfo(
            model='text-embedding-3-small',
            vector=[0.1, 0.2, ...],
            dimension=1536
        )
    }
)
```

### 2. 批量处理

```python
# 一次性处理多条新知识
new_knowledge_batch = [
    knowledge1, knowledge2, knowledge3, ...
]
updated_cache = await updater.update(memory_cache, new_knowledge_batch)
```

### 3. 使用衰减

```python
# 启用衰减防止旧记忆永久占据位置
updater = EvolutionaryMemoryUpdater(
    enable_decay=True,
    fitness_calculator=FitnessCalculator(usage_decay_rate=0.95)
)
```

---

## 监控和调试

### 获取统计信息

```python
# 查看进化统计
stats = updater.get_stats()
print(f"总更新次数: {stats['updates']}")
print(f"记忆合并次数: {stats['merges']}")
print(f"记忆淘汰次数: {stats['evictions']}")
print(f"新增记忆次数: {stats['additions']}")
```

### 查看适应度分布

```python
# 计算记忆适应度分布
fitness_scores = [
    calculator.calculate_fitness_score(memory)
    for memory in memory_cache
]

print(f"平均适应度: {sum(fitness_scores) / len(fitness_scores):.3f}")
print(f"最高适应度: {max(fitness_scores):.3f}")
print(f"最低适应度: {min(fitness_scores):.3f}")
```

---

## 高级用法

### 1. 自定义适应度权重

```python
# 针对特定场景调整权重
updater = EvolutionaryMemoryUpdater(
    fitness_weights={
        'usage': 0.4,        # 更重视使用频率
        'recency': 0.1,      # 降低新鲜度权重
        'accuracy': 0.3,     # 提高准确性权重
        'relevance': 0.2
    }
)
```

### 2. 基于反馈更新适应度

```python
# 根据用户反馈调整记忆质量
calculator = FitnessCalculator()

# 用户反馈某条记忆不准确
updated_memory = calculator.update_fitness(
    memory,
    used=True,
    accuracy_feedback=0.3  # 低准确性反馈
)
```

### 3. 周期性维护

```python
# 定期执行记忆库维护
async def maintain_memory_bank(memory_bank):
    # 应用使用次数衰减
    memory_bank._cache = calculator.decay_usage_counts(
        memory_bank._cache
    )
    
    # 重新评估适应度
    memory_bank._cache = updater._evaluate_fitness(
        memory_bank._cache
    )
    
    # 淘汰低价值记忆
    memory_bank._cache = updater._capacity_control(
        memory_bank._cache
    )
```

---

## 与 SimpleUpdater 对比

| 特性 | SimpleUpdater | EvolutionaryMemoryUpdater |
|------|---------------|---------------------------|
| **更新策略** | 简单添加+去重 | 进化式优化 |
| **质量保证** | 基本过滤 | 多维度适应度评估 |
| **容量控制** | 被动截断 | 智能淘汰 |
| **记忆合并** | 相似度检测 | 交叉操作+继承统计 |
| **动态优化** | 无 | 持续进化 |
| **反馈学习** | 无 | 支持 |
| **适用场景** | 简单对话 | 长期对话、复杂场景 |
| **性能开销** | 低 | 中等 |

---

## 最佳实践

### 1. 合理设置容量

```python
# 根据对话场景设置合适的容量
# 短期任务：50-100
# 中期任务：100-300
# 长期任务：300-1000
```

### 2. 调整精英比例

```python
# 根据记忆更新频率调整
# 高频更新（如客服）：0.5-0.6（更激进）
# 中频更新（如助理）：0.7（平衡）
# 低频更新（如知识库）：0.8-0.9（保守）
```

### 3. 定期维护

```python
# 建议每100轮对话或每天执行一次维护
if turn_count % 100 == 0:
    await maintain_memory_bank(memory_bank)
```

### 4. 监控质量

```python
# 定期检查记忆质量
if stats['evictions'] > stats['additions'] * 2:
    # 淘汰过多，可能需要降低质量阈值
    pass
```

---

## 未来扩展

### Phase 2 - 高级特性

- **LLM驱动变异**: 使用 LLM 智能重写和优化记忆内容
- **自适应参数**: 动态调整精英比例和相似度阈值
- **并行评估**: 批量并行计算适应度
- **多目标优化**: 同时优化质量、新鲜度、多样性等多个目标

### Phase 3 - 强化学习

- **策略优化**: 基于长期效果学习最优更新策略
- **元学习**: 自动学习最优参数配置
- **测试时学习**: 借鉴 ThetaEvolve，在使用中持续优化

---

## 参考资料

### 相关论文

1. **AlphaEvolve** (Google DeepMind)
   - Evolution through Large Models
   - 使用 LLM 作为进化算子

2. **ThetaEvolve**
   - 测试时学习增强
   - 持续适应优化

3. **进化算法基础**
   - Genetic Algorithms in Search, Optimization and Machine Learning
   - An Introduction to Genetic Algorithms

### ContextMind 相关文档

- [记忆管理设计](./MEMORY_DESIGN.md)
- [知识存储设计](./KNOWLEDGE_STORAGE_DESIGN.md)
- [自动优化框架](./AUTO_OPTIMIZE.md)

---

## 常见问题

### Q1: 为什么要使用进化式更新器？

**A**: 传统的简单添加方式容易导致：
- 记忆库爆炸（无限增长）
- 质量参差不齐（好坏混杂）
- 冗余信息过多（相似重复）
- 旧信息难以淘汰（历史包袱）

进化式更新器通过适应度评估、精英选择、智能合并和淘汰机制，持续优化记忆库质量。

### Q2: 性能开销如何？

**A**: 性能开销主要来自：
- 适应度计算（O(n)，n为记忆数）
- 相似度检测（O(n*m)，m为新知识数）
- 排序操作（O(n log n)）

对于中等规模（<1000条记忆），性能开销可接受（<100ms）。

优化建议：
- 使用嵌入向量加速相似度计算
- 批量处理新知识
- 定期而非每次更新都执行完整进化

### Q3: 如何选择合适的参数？

**A**: 参数选择指南：

**max_memory_size**:
- 短期对话：50-100
- 中期对话：100-300
- 长期对话：300-1000

**elite_ratio**:
- 高质量要求：0.8-0.9（保守）
- 平衡：0.6-0.7
- 激进淘汰：0.4-0.5

**similarity_threshold**:
- 严格去重：0.90-0.95
- 平衡：0.80-0.85
- 宽松合并：0.70-0.75

### Q4: 与 SimpleUpdater 如何选择？

**A**: 选择建议：

使用 **SimpleUpdater** 当：
- 对话轮次较少（<20轮）
- 记忆数量较小（<50条）
- 追求性能最优
- 不需要长期维护

使用 **EvolutionaryMemoryUpdater** 当：
- 长期对话（>50轮）
- 记忆数量较大（>100条）
- 需要持续优化质量
- 有用户反馈机制

---

## 总结

进化式记忆管理系统成功将 AlphaEvolve/ThetaEvolve 的进化思想应用于对话任务，实现了：

✅ **自动质量提升**: 通过适应度评估持续优化  
✅ **智能容量控制**: 保持合理大小  
✅ **相似记忆去重**: 避免冗余  
✅ **适应性学习**: 基于使用反馈调整  
✅ **模块化设计**: 易于集成和扩展  

这为 ContextMind 提供了强大的记忆管理能力，使其能够在长期对话中保持高质量的记忆库。
