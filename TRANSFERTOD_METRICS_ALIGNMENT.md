# TransferTOD 指标对齐说明

## 📋 概述

本文档说明 ContextMind 的 TransferTOD 测试指标如何对齐 TransferTOD 论文（EMNLP 2024）的评估标准。

---

## 🎯 修改动机

TransferTOD 论文有其特定的评估方法，为了确保测试结果可与论文进行公平对比，我们需要对齐以下指标：

1. **Joint Accuracy**（联合准确率）
2. **F1 Score / Precision / Recall**

---

## 📊 指标对齐详情

### 1. Joint Accuracy（联合准确率）

**原实现（修改前）：**
- **级别**：轮次级别 (Turn-level)
- **定义**：所有槽位都正确提取的轮次占总轮次的比例
- **问题**：与 TransferTOD 论文的对话级别评估不一致

**新实现（对齐论文）：**
- **级别**：对话级别 (Dialogue-level)
- **定义**：最终状态完全匹配的对话占总对话数的比例
- **实现**：
  ```python
  def _calculate_joint_accuracy(self, expected: Dict, extracted: Dict) -> float:
      # 转换为 slot-value pairs 集合
      expected_pairs = set([(k, str(v)) for k, v in expected.items() if v is not None])
      extracted_pairs = set([(k, str(v)) for k, v in extracted.items() if v is not None])
      
      # 完全匹配才算正确
      return 1.0 if expected_pairs == extracted_pairs else 0.0
  ```

**参考：TransferTOD 论文 eval.py**
```python
actual = set([(k, v) for k, v in actual_slots.items()])
predict = set([(k, v) for k, v in predict_slots.items()])
if actual == predict:
    joint_acc += 1
```

---

### 2. F1 / Precision / Recall

**原实现（修改前）：**
- **比较单元**：槽位名称 (Slot names)
- **逻辑**：遍历所有轮次，比较每个槽位是否正确
- **问题**：未使用 slot-value pairs，导致不同值的同一槽位无法区分

**新实现（对齐论文）：**
- **比较单元**：Slot-value pairs `(slot_name, slot_value)`
- **逻辑**：基于集合运算计算 TP/FP/FN
- **实现**：
  ```python
  def _calculate_prf_pairs(self, expected: Dict, extracted: Dict) -> Tuple[float, float, float]:
      # 转换为 slot-value pairs 集合
      expected_pairs = set([(k, str(v)) for k, v in expected.items() if v is not None])
      extracted_pairs = set([(k, str(v)) for k, v in extracted.items() if v is not None])
      
      # 计算 TP, FP, FN
      TP = len(expected_pairs & extracted_pairs)  # 交集
      FP = len(extracted_pairs - expected_pairs)  # 预测但不在真实中
      FN = len(expected_pairs - extracted_pairs)  # 真实但未预测
      
      # 特殊情况：expected 为空
      if len(expected_pairs) == 0:
          return (1.0, 1.0, 1.0) if len(extracted_pairs) == 0 else (0.0, 0.0, 0.0)
      
      # 计算 P/R/F1
      precision = TP / (TP + FP) if (TP + FP) > 0 else 0.0
      recall = TP / (TP + FN) if (TP + FN) > 0 else 0.0
      f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
      
      return precision, recall, f1
  ```

**参考：TransferTOD 论文 eval.py**
```python
def f1_calculator(actual, predict):
    TP, FP, FN = 0, 0, 0
    if len(actual) != 0:
        for g in actual:
            if g in predict:
                TP += 1
            else:
                FN += 1
        for p in predict:
            if p not in actual:
                FP += 1
        precision = TP / float(TP + FP) if (TP + FP) != 0 else 0
        recall = TP / float(TP + FN) if (TP + FN) != 0 else 0
        F1 = 2 * precision * recall / float(precision + recall) if (precision + recall) != 0 else 0
    else:
        if len(predict) == 0:
            precision, recall, F1 = 1, 1, 1
        else:
            precision, recall, F1 = 0, 0, 0
    return F1, recall, precision
```

---

## 🔄 对比示例

### 示例对话

**最终状态：**
- **期望 (Ground Truth)**：`{"姓名": "张三", "电话": "123", "地址": "北京"}`
- **提取 (Predicted)**：`{"姓名": "张三", "电话": "456"}`

### 指标计算

**1. Joint Accuracy**

修改前（轮次级别，假设有 3 轮）：
```
Turn 1: 部分匹配 → 0
Turn 2: 部分匹配 → 0
Turn 3: 部分匹配 → 0
Joint Goal Accuracy = 0/3 = 0%
```

修改后（对话级别）：
```python
expected_pairs = {("姓名", "张三"), ("电话", "123"), ("地址", "北京")}
extracted_pairs = {("姓名", "张三"), ("电话", "456")}
expected_pairs != extracted_pairs
Joint Accuracy = 0.0  # 最终状态不完全匹配
```

**2. F1 / Precision / Recall**

修改前（槽位级别）：
```
TP: 姓名正确 = 1
FP: 电话错误值 = 1
FN: 电话值错误 + 地址缺失 = 2
Precision = 1/(1+1) = 50%
Recall = 1/(1+2) = 33.3%
F1 = 40%
```

修改后（slot-value pairs）：
```python
expected_pairs = {("姓名", "张三"), ("电话", "123"), ("地址", "北京")}
extracted_pairs = {("姓名", "张三"), ("电话", "456")}

TP = len({("姓名", "张三")}) = 1
FP = len({("电话", "456")}) = 1
FN = len({("电话", "123"), ("地址", "北京")}) = 2

Precision = 1/(1+1) = 50%
Recall = 1/(1+2) = 33.3%
F1 = 40%
```

*在这个例子中，两种方法结果相同，但在更复杂的情况下会有差异。*

---

## 📝 实现细节

### 关键改动

**1. 新增方法（test_dst_transfertod.py 和 test_fnctod_transfertod.py）**

```python
def _calculate_joint_accuracy(self, expected: Dict, extracted: Dict) -> float:
    """对话级别的Joint Accuracy"""
    ...

def _calculate_prf_pairs(self, expected: Dict, extracted: Dict) -> Tuple[float, float, float]:
    """基于slot-value pairs的P/R/F1"""
    ...
```

**2. 更新测试逻辑**

- 维护累积的期望状态（`cumulative_expected_state`）
- 在对话结束后，使用最终状态计算指标
- 使用新方法替代原有的轮次级别计算

**3. 输出格式更新**

```python
# 修改前
print(f"Joint Goal Accuracy: {joint_goal_accuracy * 100:.2f}%")

# 修改后
print(f"联合准确率 (Joint Accuracy): {joint_accuracy * 100:.2f}%")
print("注：指标计算方法已对齐TransferTOD论文")
print("  - Joint Accuracy: 对话级别（最终状态完全匹配）")
print("  - F1/Precision/Recall: 基于slot-value pairs计算")
```

---

## ✅ 验证测试

创建了 5 个测试用例验证指标计算正确性：

1. **完全匹配** - Joint Accuracy = 1.0, F1 = 1.0 ✓
2. **部分匹配** - Joint Accuracy = 0.0, F1 = 0.4 ✓
3. **空状态** - Joint Accuracy = 1.0, F1 = 1.0 ✓
4. **期望为空，提取不为空** - Joint Accuracy = 0.0, F1 = 0.0 ✓
5. **类型转换（int/bool）** - Joint Accuracy = 1.0, F1 = 1.0 ✓

所有测试均通过，确保实现正确。

---

## 🎯 使用指南

### 运行测试

```bash
# DST 模式
python tests/test_dst_transfertod.py --domain 酒店 --limit 10

# FnCTOD 模式
python tests/test_fnctod_transfertod.py --domain 酒店 --limit 10
```

### 理解输出

```
--- 测试结果（对齐TransferTOD论文指标）---
槽位准确率 (Slot Accuracy): 95.00%        # 槽位级别准确率（用于分析）
联合准确率 (Joint Accuracy): 1.00 (100%)  # 对话级别（论文主要指标）⭐
精确率 (Precision): 94.50%                 # 基于slot-value pairs ⭐
召回率 (Recall): 95.50%                    # 基于slot-value pairs ⭐
F1分数 (F1 Score): 95.00%                  # 基于slot-value pairs ⭐
```

---

## 📚 参考资料

### TransferTOD 论文

- **标题**: TransferTOD: A Generalizable Chinese Multi-Domain Task-Oriented Dialogue System with Transfer Capabilities
- **会议**: EMNLP 2024 (Main Conference)
- **作者**: Ming Zhang et al.
- **链接**: 
  - arXiv: https://arxiv.org/abs/2407.21693
  - ACL Anthology: https://aclanthology.org/2024.emnlp-main.710.pdf
  - GitHub: https://github.com/KongLongGeFDU/TransferTOD

### 官方评估代码

- 文件：`TransferTOD/inference/eval.py`
- 核心方法：
  - `f1_calculator(actual, predict)` - F1 计算
  - `evaluate(actual_file, predict_file)` - 主评估函数

---

## 📌 注意事项

1. **Slot Accuracy 保留**
   - 虽然不是论文主要指标，但对分析有用
   - 提供槽位级别的细粒度性能分析

2. **类型转换**
   - 所有值都转换为字符串进行比较
   - 处理 int、bool、float 等类型
   - 确保与论文的 JSON 序列化行为一致

3. **特殊情况**
   - 空状态：expected 和 extracted 都为空时，P/R/F1 = 1.0
   - None 值：自动过滤，不参与比较

4. **向后兼容**
   - Slot Accuracy 仍然可用
   - 新旧方法都保留在代码中（旧方法标记为 deprecated）

---

## 🔄 更新历史

- **2026-02-05**: 初始版本，对齐 TransferTOD 论文（EMNLP 2024）
  - 实现对话级别 Joint Accuracy
  - 实现基于 slot-value pairs 的 F1/P/R
  - 更新文档和示例

---

**维护者**: ContextMind Team  
**最后更新**: 2026-02-05
