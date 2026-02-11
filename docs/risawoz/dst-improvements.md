# RiSAWOZ DST 评测改进总结

## 概述

本文档总结了对 RiSAWOZ 数据集 DST（对话状态追踪）评测代码的所有改进。

## 主要改进

### 1. 自定义 JSON 文件路径支持

#### 问题
之前必须将文件重命名为 `train.json`, `val.json`, `test.json`。

#### 解决方案
添加了 `--train-file`, `--val-file`, `--test-file` 参数，支持自定义文件名。

#### 使用方法
```bash
# 使用自定义文件名
python benchmark/run_dst_risawoz.py \
    --train-file train_data.json \
    --val-file val_data.json \
    --test-file test_data.json_all
```

### 2. 完整路径支持

#### 问题
用户需要手动设置 `data_root` 和文件名。

#### 解决方案
支持直接使用完整路径，自动分离目录和文件名。

#### 使用方法
```bash
# 直接使用完整路径
python benchmark/run_dst_risawoz.py \
    --test-file .data/RiSAWOZ/task1-data/test.json
```

### 3. Split 参数自动检测 ⭐

#### 问题
使用完整路径时，`split` 参数不匹配导致加载错误文件。

#### 解决方案
从文件路径自动检测并设置 `split` 参数。

#### 使用方法
```bash
# 自动设置 split=test
python benchmark/run_dst_risawoz.py \
    --test-file .data/RiSAWOZ/task1-data/test.json
    # split 自动设置为 "test"
```

### 4. 软匹配联合准确率

#### 问题
只有严格的联合准确率（所有槽位必须完全匹配）。

#### 解决方案
添加了软匹配模式（允许额外槽位）。

#### 指标
- **联合准确率-严格**: 不允许额外槽位
- **联合准确率-软匹配**: 允许额外槽位

### 5. 意图评测集成

#### 问题
没有意图识别评测。

#### 解决方案
集成了 IntentEvaluator，自动进行意图评测。

#### 输出
```
📊 意图识别评测报告
意图识别准确率: 85.00%
```

### 6. 数据格式验证

#### 问题
用户使用 NLU 格式数据（task1-data）导致评测失败，错误信息不清楚。

#### 解决方案
添加了数据格式验证，检测并拒绝 NLU 格式数据，给出清晰的错误提示。

#### 错误提示
```
======================================================================
❌ 错误：检测到 NLU 标注数据格式
======================================================================

此格式用于 NLU 任务（意图识别、实体提取），
不适用于 DST（对话状态追踪）评测。

请使用包含 'dialogue' 和 'belief_state' 字段的 DST 格式数据。
参考: https://github.com/terryqj0107/RiSAWOZ
======================================================================
```

### 7. 多种数据格式支持

#### 问题
只支持标准的字典格式。

#### 解决方案
支持多种数据格式：
- 标准字典格式：`{"dialogue": [...], "goal": {...}}`
- 简单列表格式：`[{turn1}, {turn2}]`
- 嵌套列表格式：`[[{turn1}], [{turn2}]]`

### 8. 动态领域初始化

#### 问题
使用不存在的"通用"领域导致警告。

#### 解决方案
- 指定领域时：使用指定的领域
- 不指定领域时：按每个对话的实际领域动态初始化

### 9. RiSAWOZ 标签解析器

#### 问题
RiSAWOZ 使用 `意图+领域+槽位+值` 格式，没有解析工具。

#### 解决方案
创建了 `RiSAWOZLabelParser` 工具类。

#### 使用方法
```python
from benchmark.datasets.risawoz.label_parser import RiSAWOZLabelParser

label = RiSAWOZLabelParser.parse_label("Inform+酒店+名称+希尔顿")
print(label.intent)  # "Inform"
print(label.domain)  # "酒店"
print(label.slot)    # "名称"
print(label.value)   # "希尔顿"
```

### 10. 完整文档

#### 新增文档
- `benchmark/datasets/risawoz/README.md`: 完整的使用文档
- `benchmark/datasets/risawoz/DATASET_SETUP.md`: 数据集设置指南
- `benchmark/datasets/risawoz/QUICK_START.md`: 快速开始指南
- `resources/data/RISAWOZ_TEST_README.md`: NLU 测试数据说明
- `docs/INTENT_EVALUATION_GUIDE.md`: 意图评测指南

## 使用示例

### 完整示例

```bash
# 使用 task1-data-NLU.zip 的原始文件名（推荐）
python benchmark/run_dst_risawoz.py \
    --test-file .data/RiSAWOZ/task1-data/test.json \
    --limit 10

# 输出：
# [INFO] 检测到完整路径，使用: data_root=.data/RiSAWOZ/task1-data, test_file=test.json
# [INFO] 根据文件路径自动设置 split=test
# [INFO] 找到 10 个对话实例
```

### 传统用法（仍然支持）

```bash
python benchmark/run_dst_risawoz.py \
    --data-root ./data/RiSAWOZ \
    --split val \
    --domain 景点 \
    --limit 10
```

## 向后兼容性

✅ 所有改进都完全向后兼容，不影响现有用法。

## 总结

这些改进大大提升了 RiSAWOZ DST 评测的易用性和功能性：

- ✅ 更灵活的文件路径支持
- ✅ 自动化的参数检测
- ✅ 更丰富的评测指标
- ✅ 清晰的错误提示
- ✅ 完整的文档支持
- ✅ 完全向后兼容

用户现在可以更轻松、更准确地进行 RiSAWOZ 数据集的 DST 评测！
