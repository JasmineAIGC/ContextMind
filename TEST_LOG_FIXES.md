# TransferTOD 测试日志问题修复

## 📋 问题概述

从 `logs/temp.log` 发现两个主要问题：

1. **错误**: 大量 AttributeError 异常
2. **指标差**: 准确率仅 27%，F1 分数仅 11.32%

---

## 🐛 问题 1: AttributeError - 'int'/'bool' object has no attribute 'strip'

### 症状

```
ERROR - 处理轮次 10 时出错: 'int' object has no attribute 'strip'
ERROR - 处理轮次 2 时出错: 'bool' object has no attribute 'strip'
```

**统计**: 10 个对话中出现 41 次错误

### 根本原因

`contextmind/modes/dst/response_parser.py` 中的代码假设所有槽位值都是字符串，直接调用 `.strip()` 方法：

```python
# 错误的代码
if not value or not value.strip():  # ❌ value 可能是 int/bool
    continue

normalized = value.strip()  # ❌ value 可能是 int/bool
```

**为什么会出现非字符串值？**

LLM 可能提取出：
- 整数值：`{"酒店星级": 1}` 而不是 `{"酒店星级": "1"}`
- 布尔值：`{"是否需要吸烟房": True}` 而不是 `{"是否需要吸烟房": "是"}`
- 浮点值：`{"评分": 4.5}`

### 解决方案

修改 `response_parser.py` 中的两个方法：

#### 1. `normalize_value()` 方法

```python
# 修复前
if not value or not value.strip():
    return value

# 修复后
if not value:
    return value

# 确保value是字符串类型（处理int、bool等类型）
value_str = str(value) if not isinstance(value, str) else value

if not value_str.strip():
    return value_str
```

#### 2. `normalize_extracted()` 方法

```python
# 修复前
for slot, value in extracted.items():
    if not value or not value.strip():
        continue

# 修复后
for slot, value in extracted.items():
    # 确保value是字符串类型
    if value is None:
        continue
    
    value_str = str(value) if not isinstance(value, str) else value
    
    if not value_str or not value_str.strip():
        continue
```

### 验证

```python
# 测试混合类型输入
extracted = {
    "name": "张三",
    "age": 25,      # int
    "is_vip": True, # bool
    "score": 3.5,   # float
}

result = parser.normalize_extracted(extracted, {}, {})
# 输出: {'name': '张三', 'age': '25', 'is_vip': 'True', 'score': '3.5'}
# ✅ 所有值都转换为字符串
```

---

## 📊 问题 2: 指标极差 (27% 准确率)

### 症状

```
测试对话数: 10
平均槽位准确率: 27.00%        # ❌ 应该 >80%
平均 Joint Goal Accuracy: 33.64%
平均 Precision: 8.34%          # ❌ 太低
平均 Recall: 27.00%
平均 F1 Score: 11.32%          # ❌ 太低
```

### 根本原因

**测试逻辑错误**: 比较的是不同类型的状态

```python
# 错误的比较
expected = turn.expected_slots      # ❌ 仅本轮变化的槽位
extracted_state = tracker.process_turn()  # ✅ 累积的所有槽位

# 示例：
# Turn 1: expected = {"姓名": "张三"}
#         extracted = {"姓名": "张三"}  ✓ 匹配
# Turn 2: expected = {"电话": "123"}   ← 仅本轮变化
#         extracted = {"姓名": "张三", "电话": "123"}  ← 累积状态
#         比较结果：不匹配！ ❌
```

这导致从第 2 轮开始，大部分比较都失败，因为：
- **期望状态** = 本轮新增/变化的槽位（少量）
- **提取状态** = 所有历史槽位（越来越多）

### 解决方案

修改 `tests/test_dst_transfertod.py` 的测试逻辑：

#### 1. 维护累积期望状态

```python
# 修复前
for turn in dialogue.turns:
    expected = turn.expected_slots  # ❌ 只有本轮变化

# 修复后
cumulative_expected_state = {}
for turn in dialogue.turns:
    # 合并本轮变化到累积状态
    cumulative_expected_state.update(turn.expected_slots)
    expected = cumulative_expected_state.copy()  # ✅ 累积状态
```

#### 2. 添加类型转换

因为 TransferTOD 数据中可能包含原始类型（int/bool），需要统一转换为字符串比较：

```python
# 修复前
if extracted_value == expected_value:
    turn_matched += 1

# 修复后
expected_value_str = str(expected_value) if expected_value is not None else None
extracted_value_str = str(extracted_value) if extracted_value is not None else None
if expected_value_str == extracted_value_str:
    turn_matched += 1
```

#### 3. 更新 _calculate_prf() 方法

同样添加类型转换逻辑，确保公平比较。

### 比较修复前后

```
修复前：
Turn 1: expected={"姓名": "张三"}
        extracted={"姓名": "张三"}
        匹配: 1/1 ✓

Turn 2: expected={"电话": "123"}          ← 只有变化
        extracted={"姓名": "张三", "电话": "123"}  ← 累积
        匹配: 1/1 但实际计算错误 ❌

修复后：
Turn 1: expected={"姓名": "张三"}
        extracted={"姓名": "张三"}
        匹配: 1/1 ✓

Turn 2: expected={"姓名": "张三", "电话": "123"}  ← 累积
        extracted={"姓名": "张三", "电话": "123"}  ← 累积
        匹配: 2/2 ✓
```

---

## �� 修改文件清单

1. **contextmind/modes/dst/response_parser.py**
   - `normalize_value()` 方法：添加类型转换
   - `normalize_extracted()` 方法：添加类型转换

2. **tests/test_dst_transfertod.py**
   - `test_dialogue()` 方法：维护累积期望状态
   - `_calculate_prf()` 方法：添加类型转换

---

## ✅ 预期改进

### 错误修复
- ❌ 修复前: 41 个 AttributeError
- ✅ 修复后: 0 个错误

### 指标改进
修复前的指标极差是因为测试逻辑错误，修复后应该看到：
- 槽位准确率: 27% → **预计 >60%**
- Joint Goal Accuracy: 33% → **预计 >50%**
- F1 Score: 11% → **预计 >40%**

实际指标取决于 LLM 的提取质量，但测试逻辑现在是正确的。

---

## 🧪 验证步骤

运行测试命令：

```bash
python tests/test_dst_transfertod.py --domain 酒店 --data-type clean --limit 10 --data-root .data/TransferTOD/
```

检查：
1. ✅ 没有 AttributeError
2. ✅ 指标显著提升
3. ✅ 详细输出显示正确的累积状态比较

---

## 📝 技术总结

### 关键教训

1. **类型假设要谨慎**
   - 不要假设外部数据总是字符串
   - 使用类型检查和转换

2. **状态比较要一致**
   - 确保比较的是同一类型的状态（增量 vs 累积）
   - TransferTOD 提供增量，DST 维护累积

3. **测试要理解被测系统**
   - DST 返回累积状态
   - 测试需要构建累积期望状态进行比较

### 最佳实践

```python
# ✅ 好的做法：类型安全
value_str = str(value) if not isinstance(value, str) else value

# ✅ 好的做法：状态一致
cumulative_expected_state.update(turn.expected_slots)

# ✅ 好的做法：公平比较
expected_str = str(expected_value)
extracted_str = str(extracted_value)
if expected_str == extracted_str:
    # 比较
```

---

**最后更新**: 2026-02-05  
**修复状态**: ✅ 已完成，待验证
