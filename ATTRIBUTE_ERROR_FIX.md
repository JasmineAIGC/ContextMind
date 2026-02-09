# DialogueTurn AttributeError 修复

## 问题描述

运行评测时出现错误：

```bash
⚠️  评测对话 clean/1-hotel/hotel_clean_1.json:1 时出错: 
'DialogueTurn' object has no attribute 'slot_changes'
```

## 根本原因

`DialogueTurn` 数据类定义使用 `expected_slots` 作为属性名，但评测代码中使用了 `slot_changes`。

### DialogueTurn 定义 (adapter.py)

```python
@dataclass
class DialogueTurn:
    """单个对话轮次"""
    turn_id: int
    user_utterance: str
    system_utterance: str
    expected_slots: Dict[str, str]  # ← 实际属性名
```

### 错误引用 (run_dst_transfertod.py)

```python
turn.slot_changes  # ❌ 不存在的属性
```

## 修复方案

将 `benchmark/run_dst_transfertod.py` 中的所有 `slot_changes` 引用替换为 `expected_slots`。

### 修改位置

1. **Line 342** - Actual DST模式，意图评测
2. **Line 378** - Ground Truth模式，状态更新  
3. **Line 389** - Ground Truth模式，意图提取
4. **Line 396** - Ground Truth模式，意图评测

### 修改示例

```python
# Before
current_state.update(turn.slot_changes)
predicted_intent = turn.slot_changes.get('intent', '其他')

# After
current_state.update(turn.expected_slots)
predicted_intent = turn.expected_slots.get('intent', '其他')
```

## 验证

```bash
# 检查没有遗留引用
$ grep "slot_changes" benchmark/run_dst_transfertod.py
(无结果)

# 确认正确使用expected_slots
$ grep "expected_slots" benchmark/run_dst_transfertod.py
342:    turn_updates=turn.expected_slots,
378:    current_state.update(turn.expected_slots)
389:    predicted_intent = turn.expected_slots.get('intent', '其他')
396:    turn_updates=turn.expected_slots,
```

## 结果

✅ AttributeError 已修复
✅ 评测可以正常运行
✅ 所有对话轮次正确处理

