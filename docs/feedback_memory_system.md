# 基于反馈信号的记忆管理系统

## 概述

本系统实现了基于反馈信号/奖励惩罚机制的智能记忆更新策略，取代传统的单向知识提取方式。通过收集和应用反馈信号，系统可以动态调整记忆的重要性和保留策略。

## 核心特性

### 1. 反馈信号类型

系统支持五种反馈信号：

- **POSITIVE (正向反馈)**: 记忆对生成高质量回复有帮助 (+0.15 奖励)
- **NEGATIVE (负向反馈)**: 记忆导致不准确或不相关的回复 (-0.25 惩罚)
- **NEUTRAL (中性反馈)**: 记忆影响不明确 (0 奖励)
- **IMPLICIT_POSITIVE (隐式正向)**: 记忆被频繁使用 (+0.05 奖励)
- **IMPLICIT_NEGATIVE (隐式负向)**: 记忆长时间未使用 (-0.05 惩罚)

### 2. 记忆更新机制

#### 2.1 反馈驱动的置信度调整

```python
new_score = old_score + learning_rate * reward
```

- `learning_rate`: 0.2 (反馈影响权重)
- `reward`: 根据反馈信号计算的奖励值

#### 2.2 时间衰减机制

基于Ebbinghaus遗忘曲线：

```python
decay_factor = exp(-decay_rate * days_since_access)
new_score = old_score * decay_factor
```

- 超过7天未访问的记忆开始衰减
- 衰减率: 0.1

#### 2.3 容量管理

当记忆库超过最大容量(100条)时，基于重要性评分保留最重要的记忆：

```python
importance = 0.5 * confidence + 0.3 * recency + 0.2 * feedback_quality
```

### 3. 智能记忆操作

- **增加**: 新知识初始置信度设为提取置信度的90%，留空间让反馈强化
- **删除**: 置信度低于0.3的记忆自动删除
- **合并**: 相似度80%+的知识合并，保留高置信度版本

## 使用方法

### 基本配置

```python
from contextmind.memory import FeedbackBasedUpdater
from contextmind import ContextEngine

# 创建引擎
engine = ContextEngine(
    app_name="my-app",
    user_id="user-123"
)

# 使用反馈更新器
feedback_updater = FeedbackBasedUpdater()
engine.memory_bank._updater = feedback_updater
```

### 提供反馈信号

#### 方式1: 显式反馈

```python
from contextmind.memory import FeedbackSignal

# 在对话过程中收集反馈
feedback_signals = {
    "[FACT] 用户喜欢红色": FeedbackSignal.POSITIVE,  # 这条记忆帮助生成好的回复
    "[FACT] 用户不喜欢蓝色": FeedbackSignal.NEGATIVE,  # 这条记忆导致错误回复
}

# 应用反馈（在下一次update时）
await engine.memory_bank.update(
    memory_cache=current_cache,
    new_knowledge=new_knowledge,
    feedback_signals=feedback_signals
)
```

#### 方式2: 隐式反馈（自动生成）

```python
# 记录记忆使用情况
feedback_updater.record_memory_usage(
    memory_content="[FACT] 用户喜欢红色",
    was_helpful=True  # 这条记忆是否有帮助
)

# 自动生成隐式反馈
implicit_feedback = feedback_updater.generate_implicit_feedback()
# 返回: {memory_content: FeedbackSignal}
```

### 在客服场景中使用

客服demo已集成反馈更新器，可以通过以下方式提供反馈：

```python
# 在CallCenterApplication中添加反馈收集逻辑
class CallCenterApplicationWithFeedback(CallCenterApplication):
    
    async def process_turn_with_feedback(self, user_input: str, user_satisfaction: str = None):
        """处理对话并收集反馈"""
        
        # 1. 获取当前使用的记忆
        context_result = await self.context_engine.optimize(user_input)
        used_memories = [
            item for item in context_result.items 
            if item.source == ContextSource.MEMORY
        ]
        
        # 2. 生成回复
        response = await self.process_turn(user_input)
        
        # 3. 根据用户满意度生成反馈信号
        if user_satisfaction == "satisfied":
            feedback_signals = {
                mem.content: FeedbackSignal.POSITIVE 
                for mem in used_memories
            }
        elif user_satisfaction == "unsatisfied":
            feedback_signals = {
                mem.content: FeedbackSignal.NEGATIVE 
                for mem in used_memories
            }
        else:
            feedback_signals = {}
        
        # 4. 应用反馈（在下次知识提取时生效）
        if feedback_signals:
            updater = self.context_engine.memory_bank._updater
            if isinstance(updater, FeedbackBasedUpdater):
                # 存储反馈，将在下次update时应用
                updater.pending_feedback = feedback_signals
        
        return response
```

## 参数调优

可以通过修改类变量调整反馈更新器的行为：

```python
updater = FeedbackBasedUpdater()

# 调整反馈学习率（影响反馈对置信度的影响程度）
updater.FEEDBACK_LEARNING_RATE = 0.3  # 默认: 0.2

# 调整奖励/惩罚值
updater.POSITIVE_REWARD = 0.2  # 默认: 0.15
updater.NEGATIVE_PENALTY = -0.3  # 默认: -0.25

# 调整时间衰减
updater.DECAY_RATE = 0.15  # 默认: 0.1
updater.DECAY_THRESHOLD_DAYS = 5  # 默认: 7

# 调整容量限制
updater.MAX_MEMORY_SIZE = 150  # 默认: 100
updater.MIN_CONFIDENCE_FOR_RETENTION = 0.4  # 默认: 0.3
```

## 设计参考文献

本实现参考了以下最新研究：

1. **Reflexion: Language Agents with Verbal Reinforcement Learning** (Shinn et al., 2023)
   - 核心思想: 通过反思和反馈进行自我改进
   - 应用: 反馈驱动的记忆置信度调整

2. **Generative Agents: Interactive Simulacra of Human Behavior** (Park et al., 2023)
   - 核心思想: 记忆的重要性、新近性和相关性评分
   - 应用: 多维度重要性评分和容量管理

3. **MemPrompt: Memory-assisted Prompt Editing with User Feedback** (Madaan et al., 2022)
   - 核心思想: 基于效用的记忆选择
   - 应用: 基于使用频率的隐式反馈

4. **Memory in Large Language Models** (Memetic Proxies, Park et al., 2023)
   - 核心思想: 记忆衰减和动态重要性
   - 应用: 时间衰减机制和重要性评分

## 监控和调试

查看反馈历史：

```python
# 查看特定记忆的反馈历史
updater = engine.memory_bank._updater
if isinstance(updater, FeedbackBasedUpdater):
    history = updater.feedback_history.get(memory_id, [])
    for record in history:
        print(f"时间: {record['timestamp']}")
        print(f"信号: {record['signal']}")
        print(f"置信度变化: {record['old_score']:.2f} → {record['new_score']:.2f}")
```

查看使用统计：

```python
# 查看记忆使用统计
stats = updater.usage_stats.get(memory_content, {})
print(f"使用次数: {stats.get('use_count', 0)}")
print(f"有用次数: {stats.get('helpful_count', 0)}")
print(f"最后使用: {stats.get('last_used')}")
```

## 性能优化

- 反馈信号批量应用，减少频繁更新
- 时间衰减采用指数函数，计算高效
- 容量管理仅在超过阈值时触发
- 相似度计算优先使用嵌入向量，提高准确性

## 与SimpleUpdater的对比

| 特性 | SimpleUpdater | FeedbackBasedUpdater |
|------|--------------|---------------------|
| 更新策略 | 基于置信度阈值 | 基于反馈信号 |
| 记忆删除 | 固定阈值 | 动态调整+时间衰减 |
| 学习能力 | 无 | 从反馈中学习 |
| 容量管理 | 无 | 智能重要性排序 |
| 时间感知 | 无 | Ebbinghaus遗忘曲线 |
| 适用场景 | 通用 | 需要持续优化的场景 |
