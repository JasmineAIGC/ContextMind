# 现代化反馈学习系统

## 概述

本文档介绍全新设计的现代化反馈学习系统，相比旧版本采用了更先进的架构和算法。

## 设计改进

### 1. 架构改进

#### 旧版本问题
- **单一职责违反**: 一个类承担太多职责
- **紧耦合**: 硬编码的常量和参数
- **难以扩展**: 缺乏接口抽象
- **简单枚举**: 反馈信号信息不足

#### 新版本优势
- **分离关注点**: 组件化设计，每个类单一职责
- **依赖注入**: 通过构造器注入策略
- **策略模式**: 可插拔的衰减策略和奖励计算器
- **丰富上下文**: FeedbackContext包含完整情境信息

### 2. 方法改进

#### 旧版本方法
```python
# 简单线性更新
new_score = old_score + learning_rate * reward

# 固定指数衰减
decay = exp(-decay_rate * days)
```

#### 新版本方法
```python
# TD学习 (Temporal Difference Learning)
td_error = reward + gamma * next_value - current_value
new_value = current_value + alpha * td_error

# UCB选择 (Upper Confidence Bound)
ucb_score = avg_reward + c * sqrt(ln(N) / n)

# Thompson采样 (Thompson Sampling)
sampled_value = betavariate(alpha + success, beta + failure)
```

## 核心组件

### 1. FeedbackContext - 丰富的反馈上下文

```python
from contextmind.memory import FeedbackContext, FeedbackType

# 创建包含完整上下文的反馈
feedback = FeedbackContext(
    feedback_type=FeedbackType.EXPLICIT_POSITIVE,
    task_type="question_answering",
    user_satisfaction=0.9,          # 用户满意度 [0, 1]
    response_quality=0.85,          # 回复质量 [0, 1]
    memory_relevance=0.8,           # 记忆相关性 [0, 1]
    metadata={'session_id': 'abc123'}
)

# 自动计算上下文感知的奖励
reward = feedback.get_reward_signal()  # 考虑所有因素
```

**支持的反馈类型**:
- `EXPLICIT_POSITIVE` / `EXPLICIT_NEGATIVE`: 明确的用户反馈
- `IMPLICIT_USAGE`: 记忆被使用
- `IMPLICIT_SUCCESS` / `IMPLICIT_FAILURE`: 对话成功/失败
- `CORRECTION`: 用户纠正
- `REINFORCEMENT`: 重复使用强化

### 2. MemoryScore - 多维记忆评分

```python
from contextmind.memory import MemoryScore

# 多维评分系统
score = MemoryScore(
    confidence=0.8,  # 置信度 (提取准确性)
    importance=0.7,  # 重要性 (长期价值)
    recency=0.9,     # 新近性 (时间相关性)
    utility=0.6,     # 效用性 (实际帮助程度)
)

# 使用注意力机制计算综合得分
composite = score.get_composite_score(weights={
    'confidence': 0.3,
    'importance': 0.25,
    'recency': 0.2,
    'utility': 0.25,
})

# TD学习更新
score.update_with_td_learning(reward=0.5, next_value=0.6)
```

### 3. 可插拔衰减策略

```python
from contextmind.memory import (
    ExponentialDecay,
    HyperbolicDecay,
    PowerLawDecay,
)

# 指数衰减 (Ebbinghaus遗忘曲线)
exp_decay = ExponentialDecay(decay_rate=0.1, threshold_days=7)

# 双曲衰减 (更符合长期记忆)
hyp_decay = HyperbolicDecay(decay_constant=10.0)

# 幂律衰减 (ACT-R理论)
pow_decay = PowerLawDecay(decay_exponent=0.5)

# 使用
decay_factor = hyp_decay.calculate_decay(days_since_access=14)
```

### 4. 现代奖励计算器

```python
from contextmind.memory import (
    TDRewardCalculator,
    ThompsonSamplingRewardCalculator,
)

# TD学习奖励计算
td_calc = TDRewardCalculator(
    learning_rate=0.1,
    discount_factor=0.9
)

# Thompson采样 (exploration-exploitation平衡)
thompson_calc = ThompsonSamplingRewardCalculator()

# 计算奖励
reward = td_calc.calculate_reward(feedback, memory_score)
```

### 5. ModernFeedbackUpdater - 现代化更新器

```python
from contextmind.memory import ModernFeedbackUpdater, UpdaterConfig

# 使用dataclass配置
config = UpdaterConfig(
    max_memory_size=100,
    min_confidence=0.3,
    similarity_threshold_merge=0.80,
    td_learning_rate=0.1,
    td_discount_factor=0.9,
    decay_type="hyperbolic",  # 可选: exponential, hyperbolic, power_law
)

# 创建更新器
updater = ModernFeedbackUpdater(config)

# 应用到引擎
engine.memory_bank._updater = updater
```

## 使用示例

### 基本使用

```python
from contextmind import ContextEngine
from contextmind.memory import (
    ModernFeedbackUpdater,
    UpdaterConfig,
    FeedbackContext,
    FeedbackType,
)

# 1. 配置并创建引擎
config = UpdaterConfig(
    decay_type="hyperbolic",
    td_learning_rate=0.15,
)
updater = ModernFeedbackUpdater(config)

engine = ContextEngine(app_name="app", user_id="user")
engine.memory_bank._updater = updater

# 2. 收集丰富的反馈
feedbacks = [
    FeedbackContext(
        feedback_type=FeedbackType.EXPLICIT_POSITIVE,
        user_satisfaction=0.9,
        response_quality=0.85,
        memory_relevance=0.8,
        metadata={'memory_content': '[FACT] 用户喜欢红色'}
    ),
    FeedbackContext(
        feedback_type=FeedbackType.IMPLICIT_SUCCESS,
        task_type="question_answering",
        metadata={'memory_content': '[FACT] 产品价格是100元'}
    ),
]

# 3. 更新时提供反馈
await engine.memory_bank.update(
    memory_cache=current_cache,
    new_knowledge=new_knowledge,
    feedback_contexts=feedbacks  # 注意: 使用feedback_contexts而非feedback_signals
)
```

### 高级配置

```python
# 自定义权重
custom_config = UpdaterConfig(
    max_memory_size=150,
    min_confidence=0.4,
    td_learning_rate=0.2,      # 更快学习
    td_discount_factor=0.95,   # 更重视长期
    decay_type="power_law",    # 幂律衰减
    decay_rate=0.15,
)

updater = ModernFeedbackUpdater(custom_config)
```

## 性能对比

| 特性 | 旧版本 (FeedbackBasedUpdater) | 新版本 (ModernFeedbackUpdater) |
|------|--------------------------|---------------------------|
| 反馈表示 | 简单枚举 (5种) | 丰富上下文 (7种+元数据) |
| 更新方法 | 线性奖励 | TD学习 |
| 选择策略 | 固定权重排序 | UCB多臂老虎机 |
| 衰减策略 | 固定指数衰减 | 3种可插拔策略 |
| 评分维度 | 单一置信度 | 4维综合评分 |
| 配置方式 | 类常量 | Dataclass配置 |
| 扩展性 | 低 (紧耦合) | 高 (策略模式) |
| 类型安全 | 中等 | 高 (Protocol) |

## 技术优势

### 1. 强化学习方法

**TD学习 (Temporal Difference Learning)**:
- 不需要等到最终结果就能更新
- 自举式学习，效率更高
- 公式: `V(s) ← V(s) + α[r + γV(s') - V(s)]`

**Thompson采样**:
- 贝叶斯方法
- 自然平衡探索和利用
- 不需要手动调参

**UCB (Upper Confidence Bound)**:
- 理论保证的性能界限
- 自适应探索
- 公式: `value + c√(ln(N)/n)`

### 2. 认知科学方法

**多种衰减曲线**:
- 指数衰减: 经典Ebbinghaus
- 双曲衰减: 更符合人类长期记忆
- 幂律衰减: ACT-R认知架构

### 3. 软件工程最佳实践

- **SOLID原则**: 单一职责、开闭原则
- **设计模式**: 策略模式、工厂模式
- **类型安全**: Protocol、Dataclass
- **可测试性**: 依赖注入、接口抽象

## 迁移指南

### 从旧版本迁移

```python
# 旧版本
from contextmind.memory import FeedbackBasedUpdater, FeedbackSignal
updater = FeedbackBasedUpdater()
feedback_signals = {
    memory_content: FeedbackSignal.POSITIVE
}

# 新版本
from contextmind.memory import ModernFeedbackUpdater, UpdaterConfig, FeedbackContext, FeedbackType
config = UpdaterConfig()  # 使用默认配置或自定义
updater = ModernFeedbackUpdater(config)

# 创建丰富的反馈上下文
feedback_contexts = [
    FeedbackContext(
        feedback_type=FeedbackType.EXPLICIT_POSITIVE,
        user_satisfaction=0.9,
        metadata={'memory_content': memory_content}
    )
]
```

**关键差异**:
1. `FeedbackSignal` → `FeedbackContext` (更丰富)
2. `feedback_signals` dict → `feedback_contexts` list
3. 硬编码常量 → `UpdaterConfig` dataclass
4. 单一score → `MemoryScore` 多维评分

## 参考文献

### 强化学习
- Sutton & Barto (2018): Reinforcement Learning: An Introduction
- Silver et al. (2016): Mastering the game of Go with deep neural networks

### 多臂老虎机
- Auer et al. (2002): Finite-time Analysis of the Multiarmed Bandit Problem
- Agrawal & Goyal (2012): Analysis of Thompson Sampling

### 认知科学
- Anderson & Schooler (1991): Reflections of the environment in memory
- Wixted & Ebbesen (1991): On the form of forgetting

### 记忆系统
- Park et al. (2023): Generative Agents
- Shinn et al. (2023): Reflexion
