# DST 通用领域支持 - 修复说明

## 问题描述

在 TransferTOD 数据集上测试 DST 模式时，出现大量"跳过未定义的槽位"警告，导致许多有效槽位被过滤掉：

```
WARNING - 跳过未定义的槽位: 用户名 (值: 李永阳)
WARNING - 跳过未定义的槽位: 身份证号码 (值: 615245196302152958)
WARNING - 跳过未定义的槽位: intent (值: 预订酒店)
WARNING - 跳过未定义的槽位: 服务要求 (值: 有SPA)
WARNING - 跳过未定义的槽位: 房间类型 (值: 吸烟房)
WARNING - 跳过未定义的槽位: 入住时长 (值: 5天)
```

## 根本原因

DST 模式的 `response_parser.py` 中的 `normalize_extracted()` 方法存在缺陷：

1. 即使设置了 `enable_dynamic_slots=True`，该方法仍然会过滤掉所有未在 `allowed_slots` 中预定义的槽位
2. `enable_filtering` 参数仅影响 `_filter_if_needed()` 方法，不影响 `normalize_extracted()`
3. 这使得 DST 无法支持通用/动态领域，限制了其在新数据集上的应用

## 解决方案

修改 `contextmind/modes/dst/response_parser.py` 中的 `normalize_extracted()` 方法，使其尊重 `enable_filtering` 设置：

### 修改前（严格模式）：
```python
def normalize_extracted(self, extracted, allowed_slots, categorical_slots):
    normalized = {}
    for slot, value in extracted.items():
        if not value or not value.strip():
            continue
        
        # ❌ 总是过滤未定义的槽位
        if slot not in allowed_slots:
            logger.warning(f"跳过未定义的槽位: {slot} (值: {value})")
            continue
        
        # ... 其他处理
    return normalized
```

### 修改后（支持动态模式）：
```python
def normalize_extracted(self, extracted, allowed_slots, categorical_slots):
    normalized = {}
    for slot, value in extracted.items():
        if not value or not value.strip():
            continue
        
        # ✅ 动态槽位模式：接受所有槽位
        if not self.enable_filtering:
            # 对分类槽位尝试归一化（但不强制）
            if slot in categorical_slots:
                normalized_value = self.normalize_value(
                    slot, value, categorical_slots[slot], strict=False
                )
                normalized[slot] = normalized_value if normalized_value else value
            else:
                normalized[slot] = value
            continue
        
        # 严格模式：仅保留预定义槽位
        if slot not in allowed_slots:
            logger.warning(f"跳过未定义的槽位: {slot} (值: {value})")
            continue
        
        # ... 其他处理
    return normalized
```

## 效果验证

### 1. 通用领域模式（无预定义槽位）
```python
pm = PromptManager(domain="通用", enable_dynamic_slots=True)
# 不添加任何槽位定义

# 结果：LLM 提取的所有槽位都被接受 ✅
```

### 2. 混合模式（部分预定义 + 动态）
```python
pm = PromptManager(domain="酒店", enable_dynamic_slots=True)
pm.add_slot("姓名", "客户姓名")
pm.add_slot("入住日期", "入住日期")

# 结果：预定义槽位 + LLM新发现的槽位都被接受 ✅
```

### 3. 严格模式（仅预定义槽位）
```python
pm = PromptManager(domain="酒店", enable_dynamic_slots=False)
pm.add_slot("姓名", "客户姓名")
pm.add_slot("入住日期", "入住日期")

# 结果：只接受预定义的槽位，过滤未知槽位 ✅
```

## 配置说明

### DialogueStateTracker 初始化
```python
tracker = DialogueStateTracker(
    llm_client=llm_client,
    prompt_manager=pm,
    enable_dynamic_slots=True  # ← 关键参数
)
```

当 `enable_dynamic_slots=True` 时：
- 自动设置 `ResponseParser.enable_filtering=False`
- LLM 可以自由提取任何相关信息
- 不限于预定义的槽位
- 适用于：
  - 新数据集测试
  - 探索性对话
  - 通用领域应用
  - TransferTOD 等多领域数据集

当 `enable_dynamic_slots=False` 时：
- 设置 `ResponseParser.enable_filtering=True`
- 仅接受预定义的槽位
- 严格的分类值匹配
- 适用于：
  - 生产环境
  - 明确定义的领域
  - 需要严格控制的场景

## 其他改进

### TransferTOD 适配器
更新 `tests/adapters/transfertod_adapter.py` 的 `get_domain_schema()` 方法：

```python
# 修改前：仅从 final_state 收集槽位
slots.update(dialogue.final_state.keys())

# 修改后：从所有轮次收集槽位
for turn in dialogue.turns:
    slots.update(turn.expected_slots.keys())
slots.update(dialogue.final_state.keys())
```

这样可以收集到对话过程中出现的所有槽位，而不仅仅是最终状态的槽位。

### 测试脚本
更新 `tests/test_dst_transfertod.py`，添加说明性注释：

```python
# 动态槽位模式：LLM可以自由提取任何相关信息，不限于预定义槽位
pm = PromptManager(domain=domain, enable_dynamic_slots=True)

# 可选：添加槽位定义作为指导
# （在动态模式下，即使未预定义的槽位也会被接受）
for slot_name, slot_info in schema["slots"].items():
    pm.add_slot(slot_name, slot_info.get("description", slot_name))
```

## 向后兼容性

✅ 所有修改都是向后兼容的：
- 现有使用 `enable_dynamic_slots=False` 的代码不受影响
- Legacy 测试继续正常工作
- 默认行为保持不变

## 测试结果

```
✅ 通用域测试：8/8 槽位接受
✅ 混合域测试：4/4 槽位接受（2预定义 + 2动态）
✅ 严格域测试：2/3 槽位接受（2预定义，1未知被过滤）
✅ Legacy 测试：所有测试通过
```

## 总结

此修复使 DST 模式真正支持：
1. **通用领域** - 完全开放，无需预定义槽位
2. **动态领域** - 接受所有 LLM 提取的信息
3. **多领域数据集** - 适用于 TransferTOD 等包含多个领域的数据集
4. **向前兼容** - 保持对严格模式的支持

现在 DST 可以灵活应用于任何领域和数据集，无需事先定义完整的槽位本体。
