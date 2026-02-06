# 意图分类系统 v2.0 - 完整总结

## 快速参考

### 问题

> "上面这个意图设计的不好。需要重新思考下，从两个方向考虑，一是本身的意图，二是意图的转变"

### 解决方案

✅ **重新设计为两层架构 + 转换追踪系统**

---

## 核心改进对比表

| 维度 | v1.0 旧设计 | v2.0 新设计 | 改进 |
|------|-----------|-----------|------|
| **意图层次** | 单层平级 | 两层架构 | ✅ 任务相关性+对话行为 |
| **意图数量** | 6类 | 11类 | ✅ 更细化 |
| **分类维度** | 混合 | 清晰分离 | ✅ 任务vs非任务 |
| **转换追踪** | ❌ 无 | ✅ 有 | ✅ 新增功能 |
| **对话阶段** | ❌ 无 | ✅ 6阶段 | ✅ 新增功能 |
| **评测维度** | 3个 | 8个 | ✅ 大幅扩展 |

---

## 新设计架构

### 两层意图分类

```
第一层：任务相关性
├── task_related (与任务相关)
└── task_independent (与任务无关)

第二层：对话行为
├── 任务相关意图 (5类)
│   ├── provide_info    - 提供信息
│   ├── request_info    - 请求信息
│   ├── confirm_info    - 确认信息
│   ├── correct_info    - 更正信息
│   └── acknowledge     - 应答确认
│
├── 任务无关意图 (4类)
│   ├── chitchat       - 闲聊
│   ├── greeting       - 问候
│   ├── farewell       - 告别
│   └── thanking       - 感谢
│
└── 元意图 (2类)
    ├── clarification  - 澄清
    └── unknown        - 未知
```

### 对话阶段

```
对话流程：
opening → info_gathering → slot_filling → confirmation → completion → closing
            ↓                    ↓              ↓
         slot_filling ←──────────┘              │
                                                │
         confirmation ←──────────────────────────┘
```

### 意图转换追踪

```
记录：(previous_intent, current_intent)
统计：转换频率、模式分析
检测：异常转换、不合理跳转
```

---

## 意图变化详解

### v1.0 → v2.0 映射

| v1.0 旧意图 | v2.0 新意图 | 变化说明 |
|-----------|-----------|---------|
| **INFORM** | → **provide_info** | 主动提供 |
| | → **confirm_info** | 确认信息 |
| | → **acknowledge** | 简单应答 |
| **REQUEST** | → **request_info** | 保持 |
| **CONFIRM** | → **confirm_info** | 改进 |
| **NEGATE** | → **correct_info** | 更准确 |
| **CHITCHAT** | → **chitchat** | 保持 |
| | → **greeting** | 细分 |
| | → **farewell** | 细分 |
| | → **thanking** | 细分 |
| **OTHER** | → **unknown** | 改名 |
| - | → **clarification** | 新增 |

### 为什么要细分INFORM？

**v1.0问题：**
```python
INFORM = "inform"  # 太宽泛，包含多种场景
```

**v2.0改进：**
```python
# 场景1：用户主动提供新信息
"我叫张三" → provide_info

# 场景2：用户确认系统询问
系统："您的名字是张三吗？"
用户："是的" → confirm_info

# 场景3：用户简单应答
系统："请告诉我您的名字"
用户："好的" → acknowledge
```

**好处：**
- ✅ 意图更明确
- ✅ 行为更清晰
- ✅ 评测更精准

---

## 转换追踪的价值

### 示例：意图转换分析

```
常见转换模式：
greeting → provide_info (45次)        # 开场后提供信息
provide_info → provide_info (150次)   # 持续提供
provide_info → confirm_info (80次)    # 提供后确认
confirm_info → farewell (30次)        # 确认后告别
```

### 发现问题

**异常转换：**
```
farewell → provide_info (5次)  # 说再见后又提供信息？
confirm_info → correct_info (20次)  # 刚确认又纠正？
```

**诊断价值：**
- 识别对话流程问题
- 发现用户困惑点
- 优化对话设计

---

## 对话阶段的意义

### 阶段-意图关联

```
opening阶段 (10%)：
  - greeting: 40次
  - provide_info: 10次

slot_filling阶段 (60%)：
  - provide_info: 250次
  - correct_info: 50次

confirmation阶段 (20%)：
  - confirm_info: 80次
  - correct_info: 20次

closing阶段 (10%)：
  - farewell: 40次
  - thanking: 10次
```

### 阶段分析价值

1. **理解对话进度**：当前在哪个阶段？
2. **预测下一步**：接下来可能的意图？
3. **检测异常**：阶段跳转是否合理？
4. **优化策略**：不同阶段不同处理

---

## 新增评测指标

### 1. 任务相关性统计

```
task_related: 85% (425/500)
task_independent: 15% (75/500)
```

**用途：** 判断对话是否聚焦任务

### 2. 对话阶段分布

```
opening: 10%
slot_filling: 60%
confirmation: 20%
closing: 10%
```

**用途：** 理解对话流程分布

### 3. 意图转换分析

```
Top 转换：
provide_info → provide_info: 150次
provide_info → confirm_info: 80次
```

**用途：** 发现常见和异常模式

### 4. 按阶段的意图分布

```
slot_filling阶段：
  provide_info: 250次 (83%)
  correct_info: 50次 (17%)
```

**用途：** 阶段-意图关联分析

---

## 推断规则优先级

```
优先级从高到低：

1. 任务无关判断
   ├── 问候（turn_id==0且无槽位）
   ├── 告别（关键词）
   ├── 感谢（关键词）
   └── 闲聊（无槽位变化）

2. 任务相关判断
   ├── 请求信息（槽位值='?'）
   ├── 更正信息（修改已有槽位）
   ├── 确认信息（重复槽位值）
   ├── 应答确认（单槽位+短话语）
   └── 提供信息（默认）

3. 未知意图
   └── 无法识别
```

**设计原则：**
- 高优先级规则更特殊
- 低优先级规则更通用
- 避免规则冲突

---

## 使用对比

### v1.0 用法

```python
# 简单推断
intent = evaluator.infer_intent_from_slots(
    turn_updates={},
    previous_state={},
    user_utterance="你好"
)
# 返回: "chitchat"
```

### v2.0 用法

```python
# 完整推断（返回更多信息）
intent, task_relevance = evaluator.infer_intent_from_slots(
    turn_updates={},
    previous_state={},
    user_utterance="你好",
    turn_id=0
)
# 返回: ("greeting", "task_independent")

# 阶段推断
phase = evaluator.infer_dialogue_phase(
    turn_id=0,
    slot_updates={},
    previous_state={},
    total_turns=10
)
# 返回: "opening"
```

---

## 报告对比

### v1.0 报告

```
======================================================================
意图评测报告 (Intent Evaluation Report)
======================================================================

总轮次数: 500
意图准确率: 77.00%

意图分布对比
----------------------------------------------------------------------
chitchat       65           75           -10       
inform         320          300          +20       

混淆矩阵
----------------------------------------------------------------------
...
```

### v2.0 报告（增强）

```
======================================================================
意图评测报告 v2.0 (Intent Evaluation Report)
======================================================================

总轮次数: 500
意图准确率: 77.00%

任务相关性统计 ← 新增
----------------------------------------------------------------------
task_related         425        (85.0%)
task_independent     75         (15.0%)

意图分布对比
----------------------------------------------------------------------
provide_info       250          240          +10       
request_info       70           75           -5        
greeting           40           45           -5        

对话阶段分布 ← 新增
----------------------------------------------------------------------
opening                  50         (10.0%)
slot_filling             300        (60.0%)
confirmation             100        (20.0%)

意图转换模式 (Top 15) ← 新增
----------------------------------------------------------------------
provide_info       provide_info       150       
provide_info       confirm_info       80        
```

---

## 技术实现要点

### 代码结构

```python
tests/intent_evaluator.py
├── TaskRelevance (Enum)        # 任务相关性枚举
├── IntentType (Enum)           # 11类意图枚举
├── DialoguePhase (Enum)        # 6个阶段枚举
└── IntentEvaluator (Class)
    ├── __init__()
    ├── infer_intent_from_slots()      # 意图推断
    ├── infer_dialogue_phase()         # 阶段推断
    ├── add_turn_evaluation()          # 添加评测
    ├── calculate_metrics()            # 计算指标
    ├── get_detailed_report()          # 生成报告
    └── reset()                        # 重置状态
```

### 关键数据结构

```python
# 意图转换序列
intent_transitions = [
    ('greeting', 'provide_info'),
    ('provide_info', 'provide_info'),
    ...
]

# 轮次详情
turn_details = [{
    'turn_id': 0,
    'predicted_intent': 'greeting',
    'inferred_intent': 'greeting',
    'task_relevance': 'task_independent',
    'dialogue_phase': 'opening',
    'correct': True,
    ...
}]
```

---

## 升级指南

### 最小修改（向后兼容）

```python
# 旧代码（仍然工作）
evaluator.add_turn_evaluation(
    turn_id=0,
    predicted_intent="inform",
    turn_updates={},
    previous_state={},
)
# ✅ 仍然工作，但缺少新功能
```

### 推荐用法（完整功能）

```python
# 新代码（推荐）
evaluator.add_turn_evaluation(
    turn_id=0,
    predicted_intent="provide_info",  # 使用新意图
    turn_updates={},
    previous_state={},
    user_utterance="你好",  # 添加话语
    dialogue_id="dialog_001",
    total_turns=10  # 添加总轮次（启用阶段推断）
)
# ✅ 完整功能，包括转换追踪和阶段分析
```

---

## 优势总结

### 1. 本身的意图（第一个方向）

✅ **层次清晰**：
- 第一层：任务相关性（是否与任务有关）
- 第二层：对话行为（具体做什么）

✅ **分类细化**：
- 6类 → 11类
- INFORM细分为3类（provide/confirm/acknowledge）
- 新增greeting/farewell/thanking

✅ **语义明确**：
- provide_info vs confirm_info vs acknowledge
- correct_info比negate更准确

### 2. 意图的转变（第二个方向）

✅ **转换追踪**：
- 记录意图转换序列
- 统计转换模式
- 发现异常跳转

✅ **阶段感知**：
- 6个对话阶段
- 阶段-意图关联
- 流程分析

✅ **动态分析**：
- 不仅看单轮意图
- 更看意图流转
- 理解对话进程

---

## 适用场景

| 场景 | v1.0 | v2.0 | 改进 |
|------|------|------|------|
| **单轮意图识别** | ✅ | ✅ | 一样 |
| **意图流程分析** | ❌ | ✅ | 新增 |
| **对话阶段识别** | ❌ | ✅ | 新增 |
| **任务导向对话** | ⚠️ | ✅ | 显著提升 |
| **多轮对话研究** | ⚠️ | ✅ | 显著提升 |

---

## 未来方向

### v2.1 (短期)
- 意图置信度评分
- 多意图识别
- 上下文增强

### v2.5 (中期)
- 学习型规则优化
- 意图预测
- 异常检测

### v3.0 (长期)
- 深度学习模型
- 人工标注结合
- 多模态支持

---

## 总结

### 关键成就

1. ✅ **两层架构** - 任务相关性 + 对话行为
2. ✅ **11类意图** - 从6类扩展，更精确
3. ✅ **转换追踪** - 记录和分析意图流转
4. ✅ **6个阶段** - 完整对话流程覆盖
5. ✅ **8个评测维度** - 从3个扩展，更全面

### 核心价值

> **"意图不是孤立的，而是对话流程中的一环。"**
> 
> **"理解意图的转变，才能真正理解对话。"**

### 影响

- ✅ 更准确的意图分类
- ✅ 更深入的对话分析
- ✅ 更有价值的评测指标
- ✅ 更好的对话系统设计

---

**版本**: 2.0  
**日期**: 2026-02-06  
**状态**: ✅ 已完成  
**作者**: ContextMind Team

**重新设计完成！意图分类系统现已升级为v2.0！** 🎉
