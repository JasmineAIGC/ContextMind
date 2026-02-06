# DST意图评测方法设计文档

## 问题背景

### 现状
- **DST模式**：在每轮对话中预测用户意图（intent字段）
- **TransferTOD数据集**：仅包含槽位标注，**没有显式的意图标签**
- **挑战**：如何在没有ground truth的情况下评测意图预测性能？

### 用户需求
> "现在dst 方法预测出来时有意图的，transferTOD 数据集里没有 意图。每轮对话 的意图 应该如何评测，设计一个最优的方法 对 意图 做一个评测。"

---

## 解决方案设计

### 核心思路：基于槽位变化的隐式意图推断

由于TransferTOD数据集没有显式意图标签，我们采用**槽位驱动的意图推断**方法：

1. **从槽位变化模式推断隐式意图** - 作为pseudo ground truth
2. **对比DST预测意图与推断意图** - 计算准确率
3. **提供多维度分析** - 理解意图预测行为

### 意图分类体系

基于对话状态追踪的常见意图类型：

| 意图类型 | 英文 | 说明 | 槽位特征 |
|---------|------|------|---------|
| 提供信息 | inform | 用户提供新信息 | 新增或更新槽位 |
| 请求信息 | request | 用户询问信息 | 槽位值为'?'或UNKNOWN |
| 确认信息 | confirm | 用户确认信息 | 重复已有槽位值 |
| 否定/修改 | negate | 用户否定或修改 | 改变已存在槽位的值 |
| 闲聊 | chitchat | 无关任务的对话 | 无槽位变化 |
| 其他 | other | 其他情况 | - |

---

## 意图推断规则

### 推断算法

```python
def infer_intent_from_slots(turn_updates, previous_state):
    """从槽位变化推断意图"""
    
    # 过滤掉'intent'槽位本身
    slot_updates = {k: v for k, v in turn_updates.items() if k != 'intent'}
    
    # 规则1: 无槽位变化 → chitchat
    if not slot_updates:
        return "chitchat"
    
    # 规则2: 槽位值为'?'或'UNKNOWN' → request
    for slot, value in slot_updates.items():
        if value in ['?', 'UNKNOWN', 'null', '未知']:
            return "request"
    
    # 规则3: 修改已存在的槽位 → negate
    for slot, value in slot_updates.items():
        if slot in previous_state and previous_state[slot] != value:
            return "negate"
    
    # 规则4: 新增槽位或首次赋值 → inform
    return "inform"
```

### 示例

**场景1: 提供信息 (inform)**
```
User: "我想订一个酒店，名字叫张三"
Slot Updates: {"姓名": "张三"}
Previous State: {}
Inferred Intent: inform  # 新增槽位
```

**场景2: 请求信息 (request)**
```
User: "酒店的价格是多少？"
Slot Updates: {"价格": "?"}
Previous State: {"姓名": "张三"}
Inferred Intent: request  # 槽位值为'?'
```

**场景3: 修改信息 (negate)**
```
User: "不对，我姓李"
Slot Updates: {"姓名": "李四"}
Previous State: {"姓名": "张三"}
Inferred Intent: negate  # 修改已有槽位
```

**场景4: 闲聊 (chitchat)**
```
User: "今天天气真好"
Slot Updates: {}
Previous State: {"姓名": "张三"}
Inferred Intent: chitchat  # 无槽位变化
```

---

## 评测框架实现

### IntentEvaluator类

核心功能：

1. **add_turn_evaluation()** - 添加每轮意图评测
2. **calculate_metrics()** - 计算评测指标
3. **get_detailed_report()** - 生成详细报告

### 评测指标

#### 1. Intent Accuracy（意图准确率）
```
Accuracy = 正确预测的轮次数 / 总轮次数
```

#### 2. Intent Distribution（意图分布）
对比预测意图和推断意图的分布差异

| 意图类型 | 预测数量 | 推断数量 | 差异 |
|---------|---------|---------|------|
| inform | 120 | 100 | +20 |
| request | 30 | 45 | -15 |
| chitchat | 50 | 55 | -5 |

#### 3. Confusion Matrix（混淆矩阵）
```
         Predicted
         inform  request  negate  chitchat
Ground
Truth
inform     85      5        2        8
request     5     35        0        5
negate      2      0       15        3
chitchat   10      5        3       37
```

#### 4. Error Pattern Analysis（错误模式分析）
识别最常见的错误模式：
- 将inform误判为chitchat（10次）
- 将request误判为inform（5次）
- ...

---

## 集成到测试流程

### 修改点

**1. 导入IntentEvaluator**
```python
from tests.intent_evaluator import IntentEvaluator
```

**2. 初始化评测器**
```python
def __init__(self, data_root):
    self.intent_evaluator = IntentEvaluator()
```

**3. 在每轮测试中添加评测**
```python
# 获取预测意图
predicted_intent = turn_updates.get('intent', '未识别')

# 添加意图评测
self.intent_evaluator.add_turn_evaluation(
    turn_id=turn.turn_id,
    predicted_intent=predicted_intent,
    turn_updates=turn.expected_slots,
    previous_state=previous_state,
    user_utterance=turn.user_utterance,
    dialogue_id=dialogue_id
)
```

**4. 输出意图评测报告**
```python
print(test.intent_evaluator.get_detailed_report())
```

---

## 输出示例

### 意图评测报告

```
======================================================================
意图评测报告 (Intent Evaluation Report)
======================================================================

总轮次数: 500
正确轮次: 385
意图准确率: 77.00%

----------------------------------------------------------------------
意图分布对比
----------------------------------------------------------------------
意图类型          预测数量      推断数量      差异      
----------------------------------------------------------------------
chitchat       65           75           -10       
inform         320          300          +20       
negate         45           50           -5        
request        70           75           -5        

----------------------------------------------------------------------
混淆矩阵 (行=Ground Truth, 列=Predicted)
----------------------------------------------------------------------
GT\Pred     chitchat    inform      negate      request     
----------------------------------------------------------------------
chitchat    55          15          2           3           
inform      10          275         8           7           
negate      5           10          28          7           
request     5           20          7           43          

----------------------------------------------------------------------
常见错误模式 (Top 10) - 总错误数: 115
----------------------------------------------------------------------
预测意图          实际意图          出现次数   
----------------------------------------------------------------------
inform          chitchat       15        
request         inform         20        
inform          request        7         
negate          inform         10        
chitchat        negate         5         
```

---

## 方法优势

### ✅ 优点

1. **零成本**：无需人工标注意图标签
2. **可解释**：基于明确的槽位变化规则
3. **实用性**：提供可操作的评测指标
4. **一致性**：推断规则稳定可重现
5. **全面性**：多维度分析意图预测行为

### ⚠️ 局限性

1. **非完美Ground Truth**：推断意图不是人工标注，可能存在误差
2. **规则简单**：无法捕捉复杂的意图模式
3. **依赖槽位**：对无槽位变化的轮次判断有限

### 💡 改进方向

1. **引入置信度**：为推断意图添加置信度评分
2. **规则优化**：基于实际数据优化推断规则
3. **人工验证**：抽样验证推断质量
4. **LLM辅助**：使用LLM为部分样本标注意图（可选）

---

## 使用指南

### 运行测试

```bash
# 基础测试
python tests/test_dst_transfertod.py --domain 酒店 --limit 10

# 详细输出（含每轮意图对比）
python tests/test_dst_transfertod.py --domain 酒店 --limit 10 --verbose
```

### 解读结果

**高准确率 (>70%)**
- ✅ DST的意图预测与槽位变化一致
- ✅ 模型理解用户意图良好

**低准确率 (<50%)**
- ⚠️ 检查混淆矩阵，找出主要错误模式
- ⚠️ 可能需要调整prompt或规则

**常见错误模式**
- inform → chitchat：模型过度预测为闲聊
- request → inform：未能识别询问意图

---

## 技术细节

### 数据流

```
TransferTOD Dataset
    ↓
Dialogue Turns (槽位变化)
    ↓
Intent Inferrer (推断隐式意图) → Inferred Intent
    ↓
DST Tracker (预测意图) → Predicted Intent
    ↓
Intent Evaluator (对比评测)
    ↓
Metrics & Report
```

### 关键代码

**tests/intent_evaluator.py**
- IntentType枚举
- IntentEvaluator类
- 推断算法
- 评测指标计算

**tests/test_dst_transfertod.py**
- 集成IntentEvaluator
- 在test_dialogue中调用评测
- 输出意图报告

---

## 总结

### 核心贡献

1. ✅ **解决了无标签问题**：通过槽位推断提供pseudo ground truth
2. ✅ **提供可操作指标**：准确率、分布、混淆矩阵等
3. ✅ **易于集成**：最小化修改，即插即用
4. ✅ **完整文档**：设计思路、实现细节、使用指南

### 适用场景

- ✅ TransferTOD及类似仅有槽位标注的数据集
- ✅ DST系统的意图预测能力评测
- ✅ 多意图场景的行为分析
- ✅ Prompt工程的效果验证

### 未来工作

- [ ] 规则优化和验证
- [ ] 支持更多意图类型
- [ ] 置信度评分机制
- [ ] 可视化分析工具
- [ ] 人工标注验证集

---

**文档版本**: 1.0  
**创建日期**: 2026-02-06  
**状态**: 已实现并测试  
