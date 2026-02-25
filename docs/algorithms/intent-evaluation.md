# 意图评测使用指南

## 概述

意图评测（Intent Evaluation）是对话系统评测的重要组成部分。本文档介绍如何使用 IntentEvaluator 进行意图识别评测。

## 什么是意图评测？

意图评测用于衡量对话系统识别用户意图的准确性。在任务型对话中，意图通常可以从用户输入和槽位信息中推断出来。

### 意图的定义

意图（Intent）表示用户希望完成的任务，例如：
- 查询景点信息
- 预订酒店
- 查询天气
- 订购外卖

### 意图与槽位的关系

- **槽位（Slot）**: 完成任务所需的具体参数（如：景点名称、入住日期）
- **意图（Intent）**: 用户想要完成的任务类型

示例：
```
用户: "我想预订明天希尔顿酒店的标准间"
意图: 预订酒店
槽位:
  - 酒店名称: 希尔顿
  - 入住日期: 明天
  - 房间类型: 标准间
```

## IntentEvaluator 简介

### 功能特点

1. **自动意图推断**: 从领域和槽位信息自动推断意图
2. **多种评测指标**: 支持准确率、混淆矩阵、宏/微平均等
3. **详细分析报告**: 提供分类报告和可视化支持
4. **易于集成**: 已集成到 DST 和 FnCTOD 评测脚本

### 支持的评测指标

1. **意图识别准确率** (Accuracy)
   - 正确识别的对话数 / 总对话数

2. **混淆矩阵** (Confusion Matrix)
   - 展示每种意图的识别情况
   - 识别错误的类型分布

3. **宏平均指标** (Macro Average)
   - Precision, Recall, F1
   - 每个意图类别权重相同

4. **微平均指标** (Micro Average)
   - Precision, Recall, F1
   - 按样本数量加权

## 使用方法

### 1. 在 DST 评测中使用（已自动集成）

DST 评测脚本（TransferTOD 和 RiSAWOZ）已自动集成意图评测：

```bash
# RiSAWOZ 评测（自动包含意图评测）
python benchmark/run_dst_risawoz.py --domain 景点 --limit 100

# TransferTOD 评测（自动包含意图评测）
python benchmark/run_dst_transfertod.py --domain 酒店 --limit 100
```

**输出示例：**
```
📊 意图识别评测报告
======================================================================

测试对话总数: 100

【整体意图识别指标】
----------------------------------------------------------------------
意图识别准确率: 85.00%
  - 正确识别: 85/100

【混淆矩阵】
              预订   查询   取消
预订          40     2      1
查询          3      45     0
取消          1      0      8

【宏平均指标】
  精确率 (Precision): 88.5%
  召回率 (Recall):    86.2%
  F1分数 (F1 Score):  87.3%

【微平均指标】
  精确率 (Precision): 85.0%
  召回率 (Recall):    85.0%
  F1分数 (F1 Score):  85.0%
```

### 2. 在 FnCTOD 评测中使用（已自动集成）

FnCTOD 评测脚本也已集成意图评测：

```bash
python benchmark/run_fnctod_transfertod.py --domain 酒店 --limit 100
```

### 3. 独立使用 IntentEvaluator

如果需要单独使用意图评测器：

```python
from benchmark.shared.intent_evaluator import IntentEvaluator

# 创建评测器
evaluator = IntentEvaluator()

# 添加对话评测
evaluator.add_dialogue_evaluation(
    dialogue_id="001",
    domain="景点",
    dialogue_slots={"景点-名称": "故宫", "景点-类型": "博物馆"},
    user_utterances=["我想了解故宫", "这是什么类型的景点"],
    predicted_state={"景点-名称": "故宫", "景点-类型": "博物馆"}
)

# 生成评测报告
summary = evaluator.generate_summary()
print(summary)

# 获取详细指标
metrics = evaluator.get_metrics()
print(f"准确率: {metrics['accuracy']:.2%}")
print(f"宏平均F1: {metrics['macro_f1']:.2%}")
```

## 意图推断规则

### 基于领域的意图推断

IntentEvaluator 使用以下规则从领域和槽位推断意图：

1. **有槽位值** → 查询/预订该领域的服务
   ```
   领域: 酒店
   槽位: {"酒店名称": "希尔顿", "入住日期": "明天"}
   推断意图: 预订酒店
   ```

2. **只有领域，无槽位** → 咨询该领域
   ```
   领域: 景点
   槽位: {}
   推断意图: 咨询景点
   ```

3. **多个领域** → 综合服务
   ```
   领域: 多个
   推断意图: 综合查询
   ```

### 自定义意图映射

如果需要自定义意图推断规则，可以修改 `IntentEvaluator` 的 `_infer_intent()` 方法：

```python
def _infer_intent(self, domain: str, slots: Dict) -> str:
    """自定义意图推断逻辑"""
    if domain == "酒店" and "入住日期" in slots:
        return "预订酒店"
    elif domain == "景点" and "名称" in slots:
        return "查询景点信息"
    # 更多自定义规则...
    return f"{domain}-通用查询"
```

## 评测指标详解

### 1. 意图识别准确率

**定义**: 正确识别意图的对话比例

**计算公式**:
```
Accuracy = 正确识别数 / 总对话数
```

**应用场景**: 总体性能评估

### 2. 混淆矩阵

**定义**: 展示每种意图的预测情况

**示例**:
```
              预测
              A    B    C
真实 A        40   2    1
     B        3    45   0
     C        1    0    8
```

**解读**:
- 对角线: 正确预测的数量
- 非对角线: 错误预测的数量
- 行: 真实意图的分布
- 列: 预测意图的分布

### 3. 宏平均 vs 微平均

#### 宏平均（Macro Average）

**计算方式**: 先计算每个类别的指标，再求平均

```python
macro_precision = sum(precision_per_class) / num_classes
```

**特点**:
- 每个类别权重相同
- 受少数类别性能影响大
- 适合评估模型对所有类别的整体表现

#### 微平均（Micro Average）

**计算方式**: 全局计算 TP/FP/FN

```python
micro_precision = total_tp / (total_tp + total_fp)
```

**特点**:
- 样本多的类别权重大
- 反映整体性能
- 在意图识别中，micro 指标通常等于准确率

## 意图评测最佳实践

### 1. 数据准备

确保对话数据包含：
- 领域信息
- 槽位信息
- 用户输入（可选，用于分析）

### 2. 选择合适的指标

- **准确率**: 快速了解整体性能
- **混淆矩阵**: 分析错误类型
- **宏平均**: 关注所有意图的平衡性能
- **微平均**: 关注整体性能

### 3. 分析评测结果

#### 如果准确率低

1. 检查意图推断规则是否合理
2. 分析混淆矩阵，找出常见错误
3. 检查槽位提取质量

#### 如果宏平均远低于微平均

说明少数类别（罕见意图）性能差：
- 增加少数类别的训练数据
- 调整意图推断规则
- 使用类别平衡策略

### 4. 结合槽位评测

意图评测应该结合槽位评测一起分析：

```
槽位准确率高 + 意图准确率高 → ✅ 系统性能好
槽位准确率高 + 意图准确率低 → ⚠️  意图推断规则有问题
槽位准确率低 + 意图准确率高 → ⚠️  可能是巧合
槽位准确率低 + 意图准确率低 → ❌ 系统需要改进
```

## 常见问题

### Q1: 为什么意图评测的微平均指标都相同？

**A**: 在单标签分类中（每个对话只有一个意图），微平均的 Precision、Recall 和 F1 必然相等，且等于准确率。这是正常现象。

参考文档：`docs/METRICS_ANALYSIS.md`

### Q2: 如何提高意图识别准确率？

**A**: 
1. 改进槽位提取质量
2. 优化意图推断规则
3. 增加训练数据
4. 使用更先进的意图分类模型

### Q3: 意图评测和槽位评测有什么区别？

**A**:
- **槽位评测**: 评估提取的参数是否正确
- **意图评测**: 评估识别的任务类型是否正确

两者互补，共同评估对话系统的理解能力。

### Q4: 可以关闭意图评测吗？

**A**: 目前意图评测已自动集成到评测脚本中。如果不需要，可以忽略输出中的意图评测部分。未来版本可能会添加开关选项。

### Q5: 如何导出意图评测结果？

**A**: 可以使用 IntentEvaluator 的 API 获取详细指标：

```python
evaluator = test.intent_evaluator
metrics = evaluator.get_metrics()

# 导出为 JSON
import json
with open("intent_metrics.json", "w") as f:
    json.dump(metrics, f, indent=2, ensure_ascii=False)
```

## 参考资料

### 相关文档

- `docs/METRICS_ANALYSIS.md`: 评测指标详细分析
- `benchmark/shared/intent_evaluator.py`: IntentEvaluator 源码
- `benchmark/run_dst_risawoz.py`: RiSAWOZ 评测示例
- `benchmark/run_dst_transfertod.py`: TransferTOD 评测示例

### 相关论文

- MultiWOZ: "MultiWOZ - A Large-Scale Multi-Domain Wizard-of-Oz Dataset"
- RiSAWOZ: "RiSAWOZ: A Large-Scale Multi-Domain Wizard-of-Oz Dataset"
- Intent Detection: "Joint Slot Filling and Intent Detection"

### 在线资源

- IntentEvaluator API 文档: 查看源码注释
- 对话系统评测标准: 参考 MultiWOZ 和 RiSAWOZ 官方评测

## 更新日志

- 2026-02-11: 创建意图评测使用指南
- 集成到 DST 和 FnCTOD 评测脚本
- 添加详细的使用示例和最佳实践

---

*最后更新: 2026-02-11*
