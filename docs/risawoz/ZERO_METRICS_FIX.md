# RiSAWOZ零指标问题修复报告

## 问题描述

从 `logs/temp.log` 发现所有评测指标都是 0%：

```
平均槽位准确率 (Slot Accuracy): 0.00%
平均联合准确率-严格 (Joint Accuracy Strict): 0.00%
平均联合准确率-软匹配 (Joint Accuracy Soft): 0.00%
平均精确率 (Precision): 0.00%
平均召回率 (Recall): 0.00%
平均F1分数 (F1 Score): 0.00%
```

同时日志格式不够清晰，没有像 TransferTOD 那样的详细比较信息。

## 根本原因分析

### 1. 槽位键格式不匹配

**Ground Truth（期望）**:
```python
{'旅游景点-名称': '周庄 古镇', '旅游景点-消费': '偏贵', '旅游景点-区域': '昆山'}
```

**LLM提取**:
```python
{'名称': '周庄古镇', '消费水平': '贵点', '地点': '昆山'}
```

**问题**:
- Ground truth 有领域前缀（`旅游景点-`）
- LLM 提取没有领域前缀
- 槽位名称不完全一致（`消费` vs `消费水平`）

### 2. 槽位值格式不匹配

**空格差异**:
- Ground truth: `'周庄 古镇'` (带空格)
- LLM: `'周庄古镇'` (无空格)

**语义差异**:
- Ground truth: `'偏贵'`
- LLM: `'贵点'`

**大小写差异**:
- 可能存在大小写不一致

### 3. 直接字符串比较导致全部不匹配

原代码使用简单字符串比较：
```python
if expected_str == extracted_str:
    turn_correct_slots += 1
```

由于上述格式差异，几乎所有槽位都不匹配，导致 0% 准确率。

## 解决方案

### 1. 槽位标准化系统

实现了三个标准化方法：

#### `_normalize_slot_key(slot_key, domain)`
```python
def _normalize_slot_key(self, slot_key: str, domain: str) -> str:
    # 如果已经有领域前缀，直接返回
    if '-' in slot_key:
        return slot_key
    # 否则添加领域前缀
    return f"{domain}-{slot_key}"
```

**效果**:
- `'名称'` + `'旅游景点'` → `'旅游景点-名称'`
- `'旅游景点-名称'` + `'旅游景点'` → `'旅游景点-名称'`

#### `_normalize_value(value)`
```python
def _normalize_value(self, value: str) -> str:
    if value is None:
        return ""
    # 去除所有空格（中英文）
    normalized = str(value).replace(" ", "").replace(" ", "")
    # 转小写
    return normalized.lower()
```

**效果**:
- `'周庄 古镇'` → `'周庄古镇'`
- `'Zhou Zhuang'` → `'zhouzhuang'`

#### `_normalize_state_dict(state, domain)`
```python
def _normalize_state_dict(self, state: Dict, domain: str) -> Dict:
    normalized = {}
    for key, value in state.items():
        norm_key = self._normalize_slot_key(key, domain)
        norm_value = self._normalize_value(value)
        if norm_value:  # 只保留非空值
            normalized[norm_key] = norm_value
    return normalized
```

**效果**:
```python
# 输入
{'名称': '周庄 古镇', '消费水平': '偏贵'}

# 输出（domain='旅游景点'）
{'旅游景点-名称': '周庄古镇', '旅游景点-消费水平': '偏贵'}
```

### 2. 更新比较逻辑

#### Joint Accuracy 计算
```python
def _calculate_joint_accuracy(self, expected, extracted, domain="", mode='strict'):
    # 标准化状态字典
    if domain:
        expected = self._normalize_state_dict(expected, domain)
        extracted = self._normalize_state_dict(extracted, domain)
    
    # 转换为集合比较
    expected_pairs = set([(k, v) for k, v in expected.items() if v])
    extracted_pairs = set([(k, v) for k, v in extracted.items() if v])
    
    # 比较
    if mode == 'strict':
        return 1.0 if expected_pairs == extracted_pairs else 0.0
    else:  # soft
        return 1.0 if expected_pairs.issubset(extracted_pairs) else 0.0
```

#### Precision/Recall/F1 计算
```python
def _calculate_prf_pairs(self, expected, extracted, domain=""):
    # 标准化
    if domain:
        expected = self._normalize_state_dict(expected, domain)
        extracted = self._normalize_state_dict(extracted, domain)
    
    # 转换为槽位-值对集合
    expected_pairs = set([(k, v) for k, v in expected.items() if v])
    extracted_pairs = set([(k, v) for k, v in extracted.items() if v])
    
    # 计算TP/FP/FN
    tp = len(expected_pairs & extracted_pairs)
    fp = len(extracted_pairs - expected_pairs)
    fn = len(expected_pairs - extracted_pairs)
    
    # 返回P/R/F1
    ...
```

### 3. 改进日志格式

#### 添加详细状态比较
```python
print(f"\n【最终状态比较】")
print(f"期望状态: {final_expected}")
print(f"提取状态: {final_extracted}")

print(f"\n【标准化后状态】（用于比较）")
print(f"标准化期望: {norm_expected}")
print(f"标准化提取: {norm_extracted}")
```

#### 显示匹配分析
```python
matched = set(norm_expected.items()) & set(norm_extracted.items())
missing = set(norm_expected.items()) - set(norm_extracted.items())
extra = set(norm_extracted.items()) - set(norm_expected.items())

if matched:
    print(f"\n✅ 匹配槽位 ({len(matched)}): {dict(matched)}")
if missing:
    print(f"❌ 缺失槽位 ({len(missing)}): {dict(missing)}")
if extra:
    print(f"⚠️  额外槽位 ({len(extra)}): {dict(extra)}")
```

## 测试结果

### 标准化效果

**测试案例**:
```python
expected = {'旅游景点-名称': '周庄 古镇', '旅游景点-消费': '偏贵'}
extracted = {'名称': '周庄古镇', '消费水平': '贵点'}
```

**标准化后**:
```python
norm_expected = {'旅游景点-名称': '周庄古镇', '旅游景点-消费': '偏贵'}
norm_extracted = {'旅游景点-名称': '周庄古镇', '旅游景点-消费水平': '贵点'}
```

**匹配结果**:
```
匹配: {('旅游景点-名称', '周庄古镇')}  ✅ 1个槽位匹配
```

### 预期改进

**之前**:
- 0% 准确率（由于格式不匹配）
- 无法调试，不知道哪里出错

**之后**:
- > 0% 准确率（至少部分槽位能匹配）
- 清晰看到哪些匹配、哪些缺失
- 方便调试和分析

## 注意事项

### 仍然存在的挑战

1. **槽位名称语义差异**
   - Ground truth: `消费`
   - LLM: `消费水平`
   - 标准化无法解决语义不同的问题

2. **值的语义差异**
   - Ground truth: `偏贵`
   - LLM: `贵点`
   - 需要更高级的语义匹配或映射表

3. **LLM的自由提取**
   - 动态槽位模式下，LLM可能使用不同的槽位名
   - 这是动态槽位的trade-off

### 未来改进方向

1. **槽位映射表**
   - 创建常见槽位的同义词映射
   - 例如：`{消费: [消费水平, 价格, 花费]}`

2. **语义相似度匹配**
   - 使用embedding计算值的相似度
   - 对于相似的值（如"偏贵"和"贵点"）给予部分分数

3. **领域特定规则**
   - 针对不同领域定制匹配规则
   - 考虑领域知识

## 总结

通过实现槽位标准化系统和改进日志格式，解决了RiSAWOZ评测中所有指标为0%的问题。

**核心改进**:
1. ✅ 槽位键标准化（添加领域前缀）
2. ✅ 槽位值标准化（去空格、统一大小写）
3. ✅ 详细的日志输出（匹配/缺失/额外槽位）
4. ✅ 更清晰的评测报告（对齐TransferTOD）

**预期结果**:
- 指标从 0% 提升到合理水平（取决于LLM性能）
- 更容易发现和调试问题
- 更好的可视化和分析能力

**局限性**:
- 无法完全解决语义差异（槽位名、值的不同表达）
- 需要进一步优化以达到更高准确率
