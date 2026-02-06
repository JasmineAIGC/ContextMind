# 意图分类系统 v2.0 设计文档

## 设计动机

### 原有设计的问题

**v1.0意图分类（6类）：**
- INFORM (提供信息)
- REQUEST (请求信息)
- CONFIRM (确认信息)
- NEGATE (否定/修改)
- CHITCHAT (闲聊)
- OTHER (其他)

**存在的问题：**
1. **混合维度**：同时包含对话行为(inform/request)和任务状态(chitchat)
2. **缺少层次**：所有意图平级，没有主次关系
3. **忽略转换**：只关注单轮意图，未考虑意图流转
4. **不够细化**：INFORM太宽泛，包含多种不同场景
5. **缺少任务阶段**：未体现任务导向对话的阶段性

### 重新设计的原则

基于用户反馈，从两个方向重新思考：
1. **本身的意图** - 意图的内在含义和清晰分类
2. **意图的转变** - 意图之间的转换关系和对话流程

---

## v2.0 设计方案

### 1. 两层意图架构

#### 第一层：任务相关性（Task Relevance）

```python
class TaskRelevance(Enum):
    TASK_RELATED = "task_related"           # 与任务相关
    TASK_INDEPENDENT = "task_independent"   # 与任务无关
```

**设计意图：**
- 明确区分任务相关和无关的对话
- 为不同类型的对话提供不同的处理策略

#### 第二层：对话行为（Dialogue Act）

**任务相关意图（5类）：**

| 意图 | 说明 | 示例 |
|------|------|------|
| `provide_info` | 用户主动提供槽位信息 | "我叫张三" |
| `request_info` | 用户询问槽位信息 | "价格多少？" |
| `confirm_info` | 用户确认系统提供的信息 | "是的，没错" |
| `correct_info` | 用户纠正之前的槽位值 | "不是张三，是李四" |
| `acknowledge` | 简单的应答确认 | "好的"、"嗯" |

**任务无关意图（4类）：**

| 意图 | 说明 | 示例 |
|------|------|------|
| `chitchat` | 日常闲聊 | "今天天气真好" |
| `greeting` | 开场问候 | "你好" |
| `farewell` | 告别 | "再见" |
| `thanking` | 感谢 | "谢谢" |

**元意图（2类）：**

| 意图 | 说明 | 示例 |
|------|------|------|
| `clarification` | 澄清/反问 | "你是说...吗？" |
| `unknown` | 未知/无法识别 | - |

### 2. 对话阶段（Dialogue Phase）

```python
class DialoguePhase(Enum):
    OPENING = "opening"                        # 开场阶段
    INFORMATION_GATHERING = "info_gathering"   # 信息收集阶段
    SLOT_FILLING = "slot_filling"             # 槽位填充阶段
    CONFIRMATION = "confirmation"              # 确认阶段
    COMPLETION = "completion"                  # 完成阶段
    CLOSING = "closing"                        # 结束阶段
```

**阶段转换规则：**
```
opening → information_gathering → slot_filling → confirmation → completion → closing
            ↓                          ↓              ↓
         slot_filling ←─────────────────┘              │
                                                       │
         confirmation ←─────────────────────────────────┘
```

### 3. 意图转换追踪

**核心思想：**
- 记录每轮的意图转换对 (previous_intent, current_intent)
- 分析常见的意图转换模式
- 检测异常的意图跳转
- 评估意图转换的合理性

**转换统计：**
```python
transition_stats = Counter([
    ('greeting', 'provide_info'),
    ('provide_info', 'provide_info'),
    ('provide_info', 'confirm_info'),
    ...
])
```

---

## 推断规则设计

### 意图推断流程

```
输入: 槽位变化 + 上下文
    ↓
1. 判断任务相关性
    ↓
2. 识别具体对话行为
    ↓
3. 推断对话阶段
    ↓
输出: (intent_type, task_relevance, dialogue_phase)
```

### 详细推断规则

#### 规则1：任务无关意图判断

```python
# 1.1 问候（通常在开场）
if turn_id == 0 and not slot_updates:
    return GREETING

# 1.2 告别
if has_farewell_keywords(user_utterance):
    return FAREWELL

# 1.3 感谢
if has_thanking_keywords(user_utterance):
    return THANKING

# 1.4 闲聊（无槽位变化且非特殊场景）
if not slot_updates and turn_id > 0:
    return CHITCHAT
```

#### 规则2：任务相关意图判断

```python
# 2.1 请求信息（槽位值为特殊标记）
if slot_value in ['?', 'UNKNOWN', 'null']:
    return REQUEST_INFO

# 2.2 更正信息（修改已存在的槽位值）
if slot in previous_state and previous_state[slot] != new_value:
    return CORRECT_INFO

# 2.3 确认信息（槽位值与之前相同）
if slot in previous_state and previous_state[slot] == new_value:
    return CONFIRM_INFO

# 2.4 应答确认（简单的槽位更新）
if len(slot_updates) == 1 and len(user_utterance) < 10:
    return ACKNOWLEDGE

# 2.5 提供信息（默认）
if slot_updates:
    return PROVIDE_INFO
```

#### 规则3：对话阶段推断

```python
# 开场阶段（前1-2轮）
if turn_id <= 1:
    return OPENING

# 结束阶段（最后1-2轮）
if turn_id >= total_turns - 2:
    return CLOSING

# 确认阶段（槽位值重复）
if is_confirmation(slot_updates, previous_state):
    return CONFIRMATION

# 槽位填充阶段（有槽位更新）
if slot_updates:
    if len(previous_state) >= 3:
        return CONFIRMATION  # 槽位较多，可能在确认
    else:
        return SLOT_FILLING

# 信息收集阶段（早期，槽位较少）
if len(previous_state) < 2:
    return INFORMATION_GATHERING
```

---

## 评测指标增强

### 新增指标

**1. 任务相关性统计**
```
task_related: 85% (425/500)
task_independent: 15% (75/500)
```

**2. 对话阶段分布**
```
opening: 10% (50/500)
slot_filling: 60% (300/500)
confirmation: 20% (100/500)
closing: 10% (50/500)
```

**3. 意图转换分析**
```
Top 意图转换:
provide_info → provide_info: 150次
provide_info → confirm_info: 80次
greeting → provide_info: 45次
```

**4. 按阶段的意图分布**
```
opening阶段:
  - greeting: 40次
  - provide_info: 10次

slot_filling阶段:
  - provide_info: 250次
  - correct_info: 50次
```

### 报告格式

```
======================================================================
意图评测报告 v2.0 (Intent Evaluation Report)
======================================================================

总轮次数: 500
正确轮次: 385
意图准确率: 77.00%

----------------------------------------------------------------------
任务相关性统计
----------------------------------------------------------------------
task_related         425        (85.0%)
task_independent     75         (15.0%)

----------------------------------------------------------------------
意图分布对比
----------------------------------------------------------------------
意图类型              预测数量      推断数量      差异      
----------------------------------------------------------------------
provide_info       320          300          +20       
request_info       70           75           -5        
correct_info       45           50           -5        
chitchat          65           75           -10       

----------------------------------------------------------------------
对话阶段分布
----------------------------------------------------------------------
opening                  50         (10.0%)
slot_filling             300        (60.0%)
confirmation             100        (20.0%)
closing                  50         (10.0%)

----------------------------------------------------------------------
意图转换模式 (Top 15) - 总转换数: 499
----------------------------------------------------------------------
前一意图              当前意图              出现次数   
----------------------------------------------------------------------
provide_info       provide_info       150       
provide_info       confirm_info       80        
greeting           provide_info       45        
...

----------------------------------------------------------------------
混淆矩阵 (行=Ground Truth, 列=Predicted)
----------------------------------------------------------------------
...

----------------------------------------------------------------------
常见错误模式 (Top 10) - 总错误数: 115
----------------------------------------------------------------------
...
```

---

## 优势分析

### v2.0 vs v1.0

| 方面 | v1.0 | v2.0 | 改进 |
|------|------|------|------|
| **分类层次** | 单层（6类平级） | 双层（任务相关性+对话行为） | ✅ 更清晰 |
| **意图数量** | 6类 | 11类 | ✅ 更细化 |
| **转换追踪** | ❌ 无 | ✅ 有 | ✅ 新增 |
| **阶段感知** | ❌ 无 | ✅ 有 | ✅ 新增 |
| **可扩展性** | ⚠️ 一般 | ✅ 好 | ✅ 提升 |

### 关键改进

1. **层次清晰**：
   - 第一层区分任务相关性
   - 第二层细化对话行为
   - 更符合对话系统的实际需求

2. **意图细化**：
   - INFORM分解为：provide_info, confirm_info, acknowledge
   - NEGATE改为：correct_info（更准确）
   - 新增：greeting, farewell, thanking（更完整）

3. **转换追踪**：
   - 记录意图转换对
   - 分析转换模式
   - 检测异常跳转

4. **阶段感知**：
   - 6个对话阶段
   - 按阶段分析意图
   - 更好理解对话流程

---

## 使用示例

### 基础使用

```python
from tests.intent_evaluator import IntentEvaluator

evaluator = IntentEvaluator()

# 添加评测
evaluator.add_turn_evaluation(
    turn_id=0,
    predicted_intent="greeting",
    turn_updates={},
    previous_state={},
    user_utterance="你好",
    dialogue_id="dialog_001",
    total_turns=10
)

# 获取报告
print(evaluator.get_detailed_report())
```

### 高级分析

```python
# 获取指标
metrics = evaluator.calculate_metrics()

# 任务相关性分析
task_stats = metrics['task_relevance_stats']
print(f"任务相关比例: {task_stats.get('task_related', 0) / metrics['total_turns']:.2%}")

# 意图转换分析
transitions = metrics['transition_stats']
for (prev, curr), count in transitions.items():
    print(f"{prev} → {curr}: {count}次")

# 阶段-意图分布
phase_intent = metrics['phase_intent_distribution']
for phase, intent_dist in phase_intent.items():
    print(f"\n{phase}阶段:")
    for intent, count in intent_dist.items():
        print(f"  {intent}: {count}次")
```

---

## 未来改进方向

### 短期（v2.1）

1. **意图置信度**：为推断的意图添加置信度评分
2. **多意图识别**：一轮可能包含多个意图
3. **上下文增强**：利用更多对话历史

### 中期（v2.5）

1. **学习型规则**：基于数据优化推断规则
2. **意图预测**：预测下一轮可能的意图
3. **异常检测**：识别不合理的意图转换

### 长期（v3.0）

1. **深度学习**：训练意图分类模型
2. **人工标注**：结合少量人工标注
3. **多模态**：考虑语音、图像等模态

---

## 总结

### 核心贡献

1. ✅ **两层架构**：任务相关性 + 对话行为
2. ✅ **意图细化**：6类 → 11类，更精确
3. ✅ **转换追踪**：记录和分析意图流转
4. ✅ **阶段感知**：6个对话阶段，全流程覆盖
5. ✅ **增强评测**：5+新增评测维度

### 适用场景

- ✅ 任务导向对话系统
- ✅ 多轮对话分析
- ✅ 意图转换研究
- ✅ 对话质量评估

### 关键理念

> **"意图不仅是单轮的行为，更是对话流程中的一环。"**
> 
> **"理解意图转换，才能真正理解对话。"**

---

**版本**: 2.0  
**日期**: 2026-02-06  
**状态**: ✅ 已实现
